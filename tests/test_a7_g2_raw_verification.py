import copy
import hashlib
import json

import pytest
import numpy as np

from codonflow.eval.anytime import FrozenReference, anytime_curve
from codonflow.eval.metrics import pairwise_ned
from codonflow.models.guided_sampler import synonymous_x0
from scripts.a7_g2_gate import recompute_raw_metrics
from tests.test_a7_g2_gate import paired_payload


def valid_result(tmp_path):
    source = "ATG" + "GCT" * 20 + "TAA"
    payload = paired_payload("g1", 0, "learned")
    payload["source_sha256"] = hashlib.sha256(source.encode()).hexdigest()
    initial = synonymous_x0(source, np.random.default_rng(0))
    payload["initial_sha256"] = hashlib.sha256(initial.encode()).hexdigest()
    sequences = []
    for index in range(500):
        codons = ["ATG"] + ["GCT"] * 20 + ["TAA"]
        alternatives = ["GCA", "GCC", "GCG", "GCT"]
        for position in range(1, 6):
            codons[position] = alternatives[(index // (4 ** (position - 1))) % 4]
        sequences.append("".join(codons))
    assert len(set(sequences)) == 500
    for point, sequence in zip(payload["points"], sequences):
        point["sequence"] = sequence
        point["objectives"] = [1.2, 1.2, 1.2, 1.2]
    calibration = tmp_path / "g1.json"
    calibration.write_text(json.dumps({"source_sha256": payload["source_sha256"],
                                       "source_role": "independent_calibration_not_test",
                                       "rscu_sha256": payload["rscu_sha256"],
                                       "reference": [0, 0, 0, 0], "scale": [1, 1, 1, 1]}))
    payload["calibration_sha256"] = hashlib.sha256(calibration.read_bytes()).hexdigest()
    payload["anytime"] = anytime_curve(payload["points"], FrozenReference.from_dict(json.loads(calibration.read_text())))
    payload["ned"] = pairwise_ned(sequences)
    return payload, source, tmp_path


def test_raw_gate_recomputes_valid_identity_initialization_auc_and_ned(tmp_path):
    payload, source, calibration = valid_result(tmp_path)
    recompute_raw_metrics(payload, source, calibration)
    assert payload["identity_rate"] == 1.0


@pytest.mark.parametrize("kind", ["initial", "identity", "auc", "ned"])
def test_raw_gate_rejects_tampered_evidence(tmp_path, kind):
    payload, source, calibration = valid_result(tmp_path)
    if kind == "initial":
        payload["initial_sha256"] = "0" * 64
    elif kind == "identity":
        codons = list(payload["points"][0]["sequence"])
        codons[3:6] = list("AAA")
        payload["points"][0]["sequence"] = "".join(codons)
    elif kind == "auc":
        payload["anytime"]["curve"][0]["hv"] += 0.01
    else:
        payload["ned"] += 0.01
    with pytest.raises(ValueError):
        recompute_raw_metrics(payload, source, calibration)
