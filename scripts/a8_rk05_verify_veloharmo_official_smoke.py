#!/usr/bin/env python3
"""Independent VeloHARMO raw-output, deterministic re-execution and scope audit."""
import argparse
import contextlib
import hashlib
import json
import os
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BASES = "TCAG"
AAS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
TABLE = dict(zip([a + b + c for a in BASES for b in BASES for c in BASES], AAS))
COMMIT = "38b48079856aeb9d33a1b10844d77aa8f6640032"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_text(path, text):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".part.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def write_json(path, value):
    write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def translate(dna):
    if not dna or len(dna) % 3 or set(dna) - set("ACGT"):
        return None
    return "".join(TABLE[dna[i:i + 3]] for i in range(0, len(dna), 3))


def legal_synonymous(candidate, native):
    first = translate(candidate)
    reference = translate(native)
    return bool(first is not None and reference is not None and len(candidate) == len(native)
                and first == reference and "*" not in first[:-1]
                and first.endswith("*") == reference.endswith("*"))


def parse_matrix(path):
    lines = Path(path).read_text().splitlines(keepends=True)
    assert len(lines) % 4 == 0
    result = []
    for index in range(len(lines) // 4):
        block = lines[4 * index:4 * index + 4]
        result.append({"source_index": index, "name": block[0].split(">")[1].split()[0],
                       "codons": block[1].split(), "count": [float(x) for x in block[2].split()],
                       "features": block[3].split(), "block": "".join(block)})
    return result


def select(records):
    import numpy as np
    eligible = []
    for record in records:
        values = np.asarray(record["count"], dtype=np.float64)
        if len(record["codons"]) < 30 or len(record["codons"]) != len(record["count"]):
            continue
        if len(record["codons"]) != len(record["features"]):
            continue
        if not np.isfinite(values).all() or np.std(values) == 0 or not np.any(values > 0.5):
            continue
        eligible.append(record)
    return sorted(eligible, key=lambda x: (len(x["codons"]), x["name"], x["source_index"]))[:7]


def parse_test_log(text):
    feature = re.search(r"feature dimension:(\d+)", text)
    metric = re.search(r"average pearson of [^:]+:([-+0-9.eE]+)±([-+0-9.eE]+)", text)
    assert feature and metric
    return int(feature.group(1)), float(metric.group(1)), float(metric.group(2))


def array_delta(first, second):
    import numpy as np
    a = np.asarray(first, dtype=np.float64)
    b = np.asarray(second, dtype=np.float64)
    if a.shape != b.shape:
        return float("inf")
    return float(np.max(np.abs(a - b))) if a.size else 0.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--materialization", type=Path, required=True)
    parser.add_argument("--production-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise RuntimeError("output directory must be new or empty")
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    production = json.loads(args.production_report.read_text())
    materialization = json.loads(args.materialization.read_text())
    checks = []
    numeric_deltas = []

    def check(name, passed, detail):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    source_details = []
    source_ok = production["source_commit"] == materialization["commit"] == COMMIT
    source_ok &= production["materialization_sha256"] == sha(args.materialization)
    for item in materialization["files"]:
        path = args.source_dir / item["path"]
        observed = sha(path)
        match = observed == item["sha256"] == production["source_file_sha256"][item["path"]]
        match &= path.stat().st_size == item["bytes"]
        source_details.append({"file": item["path"], "match": match})
        source_ok &= match
    matrix = args.source_dir / "VeloGRU/E.coli.summary.add.pro.SS.txt"
    source_ok &= sha(matrix) == production["matrix_sha256"] == materialization["matrix"]["sha256"]
    original_ga_for_hash = args.source_dir / "Genetic_algorithm/ga_velocity_pattern.add.time.pearson.ss.py"
    source_ok &= sha(original_ga_for_hash) == production["bounded_ga"]["algorithm_source_sha256"]
    check("fixed_source_weights_matrix_identity", source_ok, source_details)

    subset_path = Path(production["artifacts"]["input_subset.txt"]["path"])
    subset_text = subset_path.read_text()
    expected_selected = select(parse_matrix(matrix))
    observed_selected = parse_matrix(subset_path)
    subset_ok = "".join(x["block"] for x in expected_selected) == subset_text
    subset_ok &= [x["name"] for x in observed_selected] == [x["record_id"] for x in production["selected_records"]]
    subset_ok &= sha(subset_path) == production["artifacts"]["input_subset.txt"]["sha256"]
    check("seven_record_selection_and_subset_identity", subset_ok,
          {"records": [x["name"] for x in observed_selected], "sha256": sha(subset_path)})

    test_log_path = Path(production["artifacts"]["official_velogru_test.log"]["path"])
    test_log = test_log_path.read_text()
    feature, mean, std = parse_test_log(test_log)
    command = json.loads(Path(production["artifacts"]["official_velogru_test.command.json"]["path"]).read_text())
    test = production["official_velogru_test"]
    test_ok = (command["returncode"] == test["returncode"] == 0 and feature == test["feature_dimension"] == 105
               and mean == test["mean_pearson"] and std == test["std_pearson"]
               and test["device"] == "cuda:0" and test["records"] == 7)
    check("unmodified_official_velogru_test_success", test_ok,
          {"feature_dimension": feature, "mean": mean, "std": std, "device": test["device"]})

    original_ga = args.source_dir / "Genetic_algorithm/ga_velocity_pattern.add.time.pearson.ss.py"
    original_log = Path(production["artifacts"]["official_ga_unmodified_attempt1.log"]["path"]).read_text()
    original_rc = int(Path(production["artifacts"]["official_ga_unmodified_attempt1.returncode.txt"]["path"]).read_text())
    unmodified_ok = (original_rc != 0 and "ModuleNotFoundError: No module named 'Mimo_data'" in original_log
                     and production["official_ga_unmodified"]["expected_missing_module_failure"] is True
                     and production["official_ga_unmodified"]["executed_successfully"] is False)
    check("unmodified_ga_entrypoint_failure_retained", unmodified_ok, {"returncode": original_rc})

    runtime_path = Path(production["artifacts"]["ga_velocity_pattern.bounded_runtime.py"]["path"])
    runtime_text = runtime_path.read_text()
    reconstructed = original_ga.read_text()
    for item in production["bounded_ga"]["patch"]:
        if reconstructed.count(item["old"]) != 1:
            raise AssertionError(f"patch source mismatch: {item['label']}")
        reconstructed = reconstructed.replace(item["old"], item["new"])
    patch_ok = reconstructed == runtime_text and sha(runtime_path) == production["artifacts"]["ga_velocity_pattern.bounded_runtime.py"]["sha256"]
    patch_ok &= "POPULATION_SIZE = 8" in runtime_text and "MAX_GENERATIONS = 2" in runtime_text
    patch_ok &= "/Your/work/path" not in runtime_text and "Mimo_data" not in runtime_text
    check("ga_runtime_patch_exact_and_no_hidden_edits", patch_ok,
          {"patch_items": len(production["bounded_ga"]["patch"]), "runtime_sha256": sha(runtime_path)})

    os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"
    os.environ["MPLBACKEND"] = "Agg"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    sys.path.insert(0, str(args.source_dir / "Genetic_algorithm"))
    sys.path.insert(0, str(args.source_dir / "VeloGRU"))
    import numpy as np
    import torch
    from scipy.stats import pearsonr
    from VeloGRU_data import load_data
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    independent_plot = args.output_dir / "independent_ga_velocity_pattern.jpg"
    production_plot = production["artifacts"]["bounded_ga_velocity_pattern.jpg"]["path"]
    independent_runtime_text = runtime_text.replace(repr(production_plot), repr(str(independent_plot)))
    if independent_runtime_text == runtime_text:
        raise AssertionError("independent plot redirection failed")
    independent_runtime = args.output_dir / "ga_velocity_pattern.independent_runtime.py"
    write_text(independent_runtime, independent_runtime_text)
    seed = production["bounded_ga"]["seed"]
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    namespace = {"__name__": "__main__", "__file__": str(independent_runtime), "__package__": None}
    independent_log = args.output_dir / "independent_ga_execution.log"
    with independent_log.open("x", encoding="utf-8") as handle:
        with contextlib.redirect_stdout(handle), contextlib.redirect_stderr(handle):
            exec(compile(independent_runtime_text, str(independent_runtime), "exec"), namespace)
    trace_path = Path(production["artifacts"]["ga_trace.json"]["path"])
    trace = json.loads(trace_path.read_text())
    sequence_ok = (namespace["start_seq"] == trace["start_sequence"] == production["bounded_ga"]["start_sequence"]
                   and namespace["best_rna_sequence"] == trace["best_sequence"] == production["bounded_ga"]["best_sequence"]
                   and namespace["end_seq"] == trace["end_sequence"]
                   and namespace["seqs"] == trace["native_sequence"]
                   and namespace["target_sequence"] == trace["target_protein"])
    check("independent_ga_sequence_reexecution_exact", sequence_ok,
          {"start_sha256": hashlib.sha256(namespace["start_seq"].encode()).hexdigest(),
           "best_sha256": hashlib.sha256(namespace["best_rna_sequence"].encode()).hexdigest()})

    cache = namespace["evaluate_fitness"].cache_info()._asdict()
    ga = production["bounded_ga"]
    negative_ok = (cache == trace["cache_info_after_ga"] == ga["cache_info_after_ga"]
                   and namespace["best_rna_sequence"] == namespace["start_seq"]
                   and ga["best_minus_start"] == 0 and ga["start_to_best_improved"] is False
                   and trace["final_population_returned_by_official_implementation"] is False)
    check("ga_cache_and_zero_iteration_improvement_preserved", negative_ok, cache)

    sequences = {"native": trace["native_sequence"], "start": namespace["start_seq"],
                 "best": namespace["best_rna_sequence"]}
    fitness = {name: float(namespace["evaluate_fitness"](sequence)) for name, sequence in sequences.items()}
    fitness_ok = True
    for name in sequences:
        delta = abs(fitness[name] - trace["fitness"][name])
        numeric_deltas.append(delta)
        fitness_ok &= delta == 0
    check("ga_fitness_recomputation_exact", fitness_ok, fitness)

    legal_details = {name: legal_synonymous(sequence, trace["native_sequence"]) for name, sequence in sequences.items()}
    legal_ok = all(legal_details.values()) and ga["legal_synonymous_count"] == ga["candidate_count"] == 2
    legal_ok &= ga["unique_sequence_count"] == len(set(sequences.values())) == 2
    check("native_start_best_synonymous_stop_contract", legal_ok, legal_details)

    seq2feature = namespace["seq2feature"]
    ecoli_cpu = namespace["velo_model1"]
    yeast_cpu = namespace["velo_model"]
    ecoli_cpu.eval()
    yeast_cpu.eval()
    production_ga_predictions = json.loads(Path(production["artifacts"]["ga_native_start_best_predictions.json"]["path"]).read_text())
    ga_prediction_deltas = {}

    def cpu_predict(model, sequence):
        features = seq2feature(sequence).to(torch.float32)
        with torch.no_grad():
            output = model(features, torch.tensor([[features.shape[1]]]))
        return output.reshape(-1)[:features.shape[1]].detach().cpu().numpy().astype(float).tolist()

    for name, sequence in sequences.items():
        for model_name, model in [("ecoli_prediction", ecoli_cpu), ("yeast_prediction", yeast_cpu)]:
            observed = cpu_predict(model, sequence)
            delta = array_delta(observed, production_ga_predictions[name][model_name])
            ga_prediction_deltas[f"{name}:{model_name}"] = delta
            numeric_deltas.append(delta)
    check("ga_dual_model_velocity_arrays_exact", all(x == 0 for x in ga_prediction_deltas.values()),
          ga_prediction_deltas)

    data_x, data_y, data_len = load_data(str(subset_path), True, True, False, True)
    official_device = torch.device("cuda:0")
    torch.use_deterministic_algorithms(False)
    gpu_model = torch.load(str(args.source_dir / "Genetic_algorithm/E.coli.fold_0_best_network.pth"))
    gpu_model.eval()
    production_native = json.loads(Path(production["artifacts"]["velogru_native_predictions.json"]["path"]).read_text())["records"]
    native_deltas = {}
    scores = []
    for index, record in enumerate(production_native):
        length = int(data_len[index].item())
        with torch.no_grad():
            prediction = gpu_model(data_x[index:index + 1].to(official_device), data_len[index:index + 1])
        values = prediction.reshape(-1)[:length].detach().cpu().numpy()
        density = data_y[index, :length, 0].detach().cpu().numpy()
        delta = array_delta(values, record["ecoli_prediction"])
        native_deltas[record["record_id"]] = delta
        numeric_deltas.append(delta)
        scores.append(pearsonr(density, values)[0])
    check("official_gpu_native_prediction_arrays_exact", all(x == 0 for x in native_deltas.values()), native_deltas)

    recomputed_mean = float(np.mean(scores))
    recomputed_std = float(np.std(scores))
    metric_delta = max(abs(recomputed_mean - mean), abs(recomputed_std - std))
    metric_ok = (metric_delta == test["metric_delta"] <= 1e-7
                 and recomputed_mean == test["recomputed_mean_pearson"]
                 and recomputed_std == test["recomputed_std_pearson"])
    check("official_float32_metric_reconciliation", metric_ok,
          {"mean": recomputed_mean, "std": recomputed_std, "delta_to_official_log": metric_delta})

    environment = production["environment"]
    environment_ok = (sum(x.numel() for x in gpu_model.parameters()) == test["model_parameter_count"] == 477185
                      and sum(x.numel() for x in yeast_cpu.parameters()) == 477185
                      and environment["official_test_device"] == "cuda:0" and environment["ga_device"] == "cpu"
                      and environment["torch"] == torch.__version__ and environment["ga_deterministic_algorithms"] is True
                      and environment["official_test_deterministic_algorithms"] is False)
    check("dual_device_environment_and_parameter_reconciliation", environment_ok,
          {"torch": torch.__version__, "gpu": torch.cuda.get_device_name(0),
           "parameters_per_model": sum(x.numel() for x in gpu_model.parameters())})

    fasta_path = Path(production["artifacts"]["ga_native_start_best.fasta"]["path"])
    fasta = {}
    key = None
    for line in fasta_path.read_text().splitlines():
        if line.startswith(">"):
            key = line[1:].split("|")[0]
            fasta[key] = []
        elif key:
            fasta[key].append(line.strip())
    fasta_ok = all("".join(fasta.get(name, [])) == sequence for name, sequence in sequences.items())
    check("native_start_best_fasta_identity", fasta_ok, {"records": sorted(fasta)})

    artifact_details = []
    artifacts_ok = True
    for name, item in production["artifacts"].items():
        path = Path(item["path"])
        match = path.exists() and path.stat().st_size == item["bytes"] and sha(path) == item["sha256"]
        artifacts_ok &= match
        artifact_details.append({"name": name, "match": match})
    check("all_production_artifacts_immutable_after_reexecution", artifacts_ok, artifact_details)

    scope_names = ["model_training", "publication_metrics_reproduced", "held_out_performance",
                   "main_baseline_comparison", "dense_budget_complete", "matched_cost_comparison",
                   "five_species_processed_matrices_complete", "functional_ood", "sota_claim"]
    scope_ok = all(production[name] is False for name in scope_names)
    scope_ok &= production["official_test_unmodified"] is True and production["ga_compatibility_patch"] is True
    scope_ok &= test["diagnostic_only_not_held_out"] is True
    check("bounded_scope_and_negative_flags", scope_ok, {name: production[name] for name in scope_names})
    check("production_status_reconciled", production["status"] == "BOUNDED_OFFICIAL_ALGORITHM_EXECUTION_COMPLETE",
          production["status"])

    passed = sum(item["pass"] for item in checks)
    max_delta = max(numeric_deltas) if numeric_deltas else 0.0
    report = {
        "schema_version": "a8-rk05-veloharmo-independent-verification-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if passed == len(checks) and max_delta == 0 else "FAIL",
        "check_count": len(checks), "passed_checks": passed, "checks": checks,
        "production_report": str(args.production_report), "production_report_sha256": sha(args.production_report),
        "max_numeric_delta": max_delta, "official_metric_delta": metric_delta,
        "ga_start_to_best_improved": False, "ga_best_equals_start": True,
        "official_test_device": "cuda:0", "ga_device": "cpu",
        "independent_artifacts": {"runtime": str(independent_runtime), "log": str(independent_log),
                                  "plot": str(independent_plot)},
        "main_baseline_comparison": False, "functional_ood": False, "sota_claim": False,
    }
    write_json(args.output, report)
    print(json.dumps({"status": report["status"], "checks": f"{passed}/{len(checks)}",
                      "max_numeric_delta": max_delta, "output": str(args.output)}))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
