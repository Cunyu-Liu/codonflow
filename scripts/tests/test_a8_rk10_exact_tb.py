#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import a8_rk10_train_exact_tb as production
import a8_rk10_verify_exact_tb as independent

PROTOCOL_PATH = Path(__file__).resolve().parents[2] / "configs/a8_rk10_exact_tb_protocol_v1.json"


def protocol() -> dict:
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def test_01_sense_codon_table_excludes_stops() -> None:
    codons = production.sense_codons()
    assert len(codons) == 61
    assert codons == sorted(codons)
    assert not {"TAA", "TAG", "TGA"}.intersection(codons)


def test_02_geometry_has_only_noop_or_single_sense_edit() -> None:
    edges, _, _ = production.build_geometry()
    assert edges.shape == (3721, 121)
    for state in (0, 1, 60, 61, 123, 3720):
        c0, c1 = divmod(state, 61)
        for target in edges[state]:
            d0, d1 = divmod(int(target), 61)
            changes = int(d0 != c0) + int(d1 != c1)
            assert changes <= 1
            assert 0 <= d0 < 61 and 0 <= d1 < 61
        assert len(set(edges[state].tolist())) == 121


def test_03_reverse_edges_return_to_exact_parents() -> None:
    edges, reverse = independent.reference_geometry()
    paths = independent.reference_paths(edges, reverse)
    assert np.array_equal(edges[paths["mid"], paths["rev0"]], paths["start"])
    assert np.array_equal(edges[paths["end"], paths["rev1"]], paths["mid"])


def test_04_path_enumeration_covers_every_endpoint() -> None:
    edges, _, reverse = production.build_geometry()
    paths = production.build_paths(edges, reverse)
    assert len(paths["end"]) == 14641
    counts = np.bincount(paths["end"], minlength=3721)
    assert counts.min() > 0
    assert counts.sum() == 14641
    assert np.array_equal(np.isin(edges, edges[0]).sum(axis=1), counts)


def test_05_features_and_target_are_finite_and_normalized() -> None:
    features = production.build_features()[0]
    edges, _, reverse = production.build_geometry()
    paths = production.build_paths(edges, reverse)
    target = production.target_logprob(features, edges, paths, protocol())
    assert features.shape == (3721, 4)
    assert np.isfinite(features).all()
    assert math.isclose(float(np.exp(target).sum()), 1.0, abs_tol=1e-12)


def test_06_uniform_initialization_has_expected_residual_identity() -> None:
    features = production.build_features()[0]
    edges, _, reverse = production.build_geometry()
    paths = production.build_paths(edges, reverse)
    target = production.target_logprob(features, edges, paths, protocol())
    metrics, residual, _, _ = independent.evaluate(
        np.zeros(4), np.zeros((3721, 121)), features, edges, paths, target, 0.75,
    )
    degree = np.isin(edges, edges[0]).sum(axis=1)
    expected = target[paths["end"]] - np.log(degree[paths["end"]]) + 2 * math.log(121)
    assert np.allclose(residual, expected, atol=1e-12, rtol=0)
    assert math.isclose(metrics["loss"], float(np.mean(expected ** 2)), abs_tol=1e-12)


def test_07_analytic_oracle_has_zero_path_residual() -> None:
    cfg = protocol()
    features = independent.reference_features()
    edges, reverse = independent.reference_geometry()
    paths = independent.reference_paths(edges, reverse)
    target = independent.reference_target(features, edges, paths, cfg)
    energy = features @ np.asarray(cfg["features"]["target_weights"])
    logq = independent.log_softmax_rows(0.75 * (energy[edges] - energy[:, None]))
    forward = logq[paths["start"], paths["a0"]] + logq[paths["mid"], paths["a1"]]
    backward = forward - target[paths["end"]]
    residual = target[paths["end"]] + backward - forward
    assert np.max(np.abs(residual)) <= 1e-12


def test_08_true_energy_forward_endpoint_equals_target() -> None:
    cfg = protocol()
    features = independent.reference_features()
    edges, reverse = independent.reference_geometry()
    paths = independent.reference_paths(edges, reverse)
    weights = np.asarray(cfg["features"]["target_weights"])
    target = independent.reference_target(features, edges, paths, cfg)
    energy = features @ weights
    logq = independent.log_softmax_rows(0.75 * (energy[edges] - energy[:, None]))
    forward = logq[paths["start"], paths["a0"]] + logq[paths["mid"], paths["a1"]]
    endpoint = np.bincount(paths["end"], weights=np.exp(forward), minlength=3721)
    assert np.max(np.abs(endpoint - np.exp(target))) <= 1e-12


def test_09_analytic_backward_normalizes_for_every_endpoint() -> None:
    cfg = protocol()
    features = independent.reference_features()
    edges, reverse = independent.reference_geometry()
    paths = independent.reference_paths(edges, reverse)
    weights = np.asarray(cfg["features"]["target_weights"])
    target = independent.reference_target(features, edges, paths, cfg)
    energy = features @ weights
    logq = independent.log_softmax_rows(0.75 * (energy[edges] - energy[:, None]))
    forward = logq[paths["start"], paths["a0"]] + logq[paths["mid"], paths["a1"]]
    backward = forward - target[paths["end"]]
    mass = np.bincount(paths["end"], weights=np.exp(backward), minlength=3721)
    assert np.max(np.abs(mass - 1)) <= 1e-12


def test_10_one_exact_cpu_optimization_step_is_finite_and_improves() -> None:
    cfg = protocol()
    torch.use_deterministic_algorithms(True)
    edges_np, _, reverse_np = production.build_geometry()
    features_np = production.build_features()[0]
    paths_np = production.build_paths(edges_np, reverse_np)
    target_np = production.target_logprob(features_np, edges_np, paths_np, cfg)
    edges = torch.as_tensor(edges_np)
    features = torch.as_tensor(features_np)
    target = torch.as_tensor(target_np)
    paths = {key: torch.as_tensor(value) for key, value in paths_np.items()}
    theta = torch.nn.Parameter(torch.zeros(4, dtype=torch.float64))
    backward = torch.nn.Parameter(torch.zeros((3721, 121), dtype=torch.float64))
    optimizer = torch.optim.Adam([theta, backward], lr=0.05)
    residual, _, _, _ = production.torch_residual(theta, backward, features, edges, paths, target, 0.75)
    initial = residual.pow(2).mean()
    optimizer.zero_grad(set_to_none=True)
    initial.backward()
    optimizer.step()
    updated, _, _, _ = production.torch_residual(theta, backward, features, edges, paths, target, 0.75)
    final = updated.pow(2).mean()
    assert torch.isfinite(final)
    assert float(final.detach()) < float(initial.detach())
