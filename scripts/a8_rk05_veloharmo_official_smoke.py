#!/usr/bin/env python3
"""Bounded VeloGRU inference and compatibility-wrapped VeloHARMO GA execution."""
import argparse
import contextlib
import difflib
import hashlib
import json
import os
import platform
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASES = "TCAG"
AAS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
TABLE = dict(zip([a + b + c for a in BASES for b in BASES for c in BASES], AAS))
COMMIT = "38b48079856aeb9d33a1b10844d77aa8f6640032"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_text_new(path, text):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".part.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def write_json_new(path, value):
    write_text_new(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def artifact(path):
    path = Path(path)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def translate(dna):
    dna = dna.upper()
    if not dna or len(dna) % 3:
        raise ValueError("DNA length must be a nonzero multiple of three")
    try:
        return "".join(TABLE[dna[i:i + 3]] for i in range(0, len(dna), 3))
    except KeyError as error:
        raise ValueError(f"invalid DNA codon: {error}") from error


def synonymous_qc(candidate, native):
    candidate = candidate.upper()
    native = native.upper()
    alphabet_valid = bool(candidate) and set(candidate) <= set("ACGT")
    same_length = len(candidate) == len(native) and len(candidate) % 3 == 0
    candidate_translation = translate(candidate) if alphabet_valid and same_length else ""
    native_translation = translate(native)
    terminal_stop = candidate_translation.endswith("*")
    internal_stop = "*" in candidate_translation[:-1]
    native_terminal_stop = native_translation.endswith("*")
    return {
        "alphabet_valid": alphabet_valid,
        "same_length": same_length,
        "translation_exact": candidate_translation == native_translation,
        "terminal_stop": terminal_stop,
        "native_terminal_stop": native_terminal_stop,
        "stop_contract_matches_native": terminal_stop == native_terminal_stop,
        "internal_stop": internal_stop,
        "legal_synonymous_cds": bool(alphabet_valid and same_length
                                     and terminal_stop == native_terminal_stop
                                     and not internal_stop
                                     and candidate_translation == native_translation),
        "dna_nt": len(candidate),
        "codons": len(candidate) // 3,
        "changed_from_native": candidate != native,
        "synonymous_substitutions": sum(a != b for a, b in zip(candidate, native)),
    }


def read_matrix_records(path):
    lines = Path(path).read_text().splitlines(keepends=True)
    if len(lines) % 4:
        raise ValueError("matrix must contain four lines per record")
    records = []
    for index in range(len(lines) // 4):
        block = lines[4 * index:4 * index + 4]
        name = block[0].split(">")[1].split()[0]
        codons = block[1].split()
        count = [float(x) for x in block[2].split()]
        features = block[3].split()
        records.append({"source_index": index, "name": name, "codons": codons,
                        "count": count, "features": features,
                        "block": "".join(block)})
    return records


def select_bounded_records(records, count=7, minimum_codons=30):
    import numpy as np
    eligible = []
    for record in records:
        values = np.asarray(record["count"], dtype=np.float64)
        length = len(record["codons"])
        if length < minimum_codons or length != len(record["count"]) or length != len(record["features"]):
            continue
        if not np.isfinite(values).all() or np.std(values) == 0 or not np.any(values > 0.5):
            continue
        eligible.append(record)
    eligible.sort(key=lambda x: (len(x["codons"]), x["name"], x["source_index"]))
    if len(eligible) < count:
        raise ValueError("insufficient eligible records")
    return eligible[:count]


def build_ga_runtime(source, subset, ecoli_weight, yeast_weight, plot_path,
                     population_size, generations):
    replacements = [
        ("from Mimo_data import load_data", "from VeloGRU_data import load_data", "missing_import"),
        ('datafile,index="/Your/work/path/E.coli.summary.add.pro.SS.txt",0',
         f"datafile,index={str(subset)!r},0", "matrix_path"),
        ("'/Your/work/path/E.coli.fold_0_best_network.pth'",
         repr(str(ecoli_weight)), "ecoli_weight_path"),
        ("'/Your/work/path/yeast.fold_0_best_network.pth'",
         repr(str(yeast_weight)), "yeast_weight_path"),
        ("POPULATION_SIZE = 100", f"POPULATION_SIZE = {population_size}", "bounded_population"),
        ("MAX_GENERATIONS = 1000", f"MAX_GENERATIONS = {generations}", "bounded_generations"),
        ("'P60595.velocity_pattern_mutation_rate0.01_300generation.1000size.ss.pearson.jpg'",
         repr(str(plot_path)), "plot_path"),
    ]
    patched = source
    metadata = []
    for old, new, label in replacements:
        occurrences = patched.count(old)
        if occurrences != 1:
            raise ValueError(f"unexpected source drift for {label}: {occurrences} occurrences")
        patched = patched.replace(old, new)
        metadata.append({"label": label, "old": old, "new": new, "occurrences": occurrences})
    if "/Your/work/path" in patched or "Mimo_data" in patched:
        raise ValueError("unresolved GA placeholder")
    return patched, metadata


def parse_official_test_log(text):
    feature = re.search(r"feature dimension:(\d+)", text)
    pearson = re.search(r"average pearson of [^:]+:([-+0-9.eE]+)±([-+0-9.eE]+)", text)
    if not feature or not pearson:
        raise ValueError("official test log missing expected fields")
    return {"feature_dimension": int(feature.group(1)),
            "mean_pearson": float(pearson.group(1)),
            "std_pearson": float(pearson.group(2))}


def normalized_density(count):
    import numpy as np
    values = np.asarray(count, dtype=np.float64)
    average = values[values > 0.5].mean()
    return ((values > 0.5) * values / average).tolist()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--materialization", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--population-size", type=int, default=8)
    parser.add_argument("--generations", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20261118)
    args = parser.parse_args()
    if args.population_size < 4 or args.population_size % 2 or args.generations < 1:
        raise ValueError("population must be even and >=4; generations must be >=1")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise RuntimeError("output directory must be new or empty")
    if args.report.exists():
        raise RuntimeError(f"refusing to overwrite {args.report}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    materialization = json.loads(args.materialization.read_text())
    if materialization["commit"] != COMMIT or materialization["status"] != "PASS_MATERIALIZATION_ONLY":
        raise ValueError("unexpected VeloHARMO materialization")
    source_hashes = {}
    for item in materialization["files"]:
        path = args.source_dir / item["path"]
        observed = sha256(path)
        if observed != item["sha256"] or path.stat().st_size != item["bytes"]:
            raise ValueError(f"source payload mismatch: {item['path']}")
        source_hashes[item["path"]] = observed
    matrix = args.source_dir / "VeloGRU/E.coli.summary.add.pro.SS.txt"
    if sha256(matrix) != materialization["matrix"]["sha256"]:
        raise ValueError("E. coli matrix hash mismatch")

    records = read_matrix_records(matrix)
    selected = select_bounded_records(records)
    subset = args.output_dir / "input_subset.txt"
    write_text_new(subset, "".join(x["block"] for x in selected))
    target = selected[6]
    native_sequence = "".join(target["codons"])
    if not synonymous_qc(native_sequence, native_sequence)["legal_synonymous_cds"]:
        raise ValueError("selected native target is not a legal CDS under the native stop contract")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(args.source_dir / "VeloGRU") + os.pathsep + str(args.source_dir / "Genetic_algorithm")
    env["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"
    env["MPLBACKEND"] = "Agg"
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    env["CUDA_VISIBLE_DEVICES"] = "0"
    os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"
    os.environ["MPLBACKEND"] = "Agg"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    ecoli_weight = args.source_dir / "Genetic_algorithm/E.coli.fold_0_best_network.pth"
    yeast_weight = args.source_dir / "Genetic_algorithm/yeast.fold_0_best_network.pth"

    test_log = args.output_dir / "official_velogru_test.log"
    test_command = [sys.executable, str(args.source_dir / "VeloGRU/run.py"), "test",
                    str(ecoli_weight), str(subset), "--nt", "--aa", "--ss",
                    "--gene_filter", "0.6", "--name", "bounded_ecoli"]
    test_started = time.perf_counter()
    test_result = subprocess.run(test_command, cwd=args.output_dir, env=env,
                                 text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    test_seconds = time.perf_counter() - test_started
    write_text_new(test_log, test_result.stdout)
    write_text_new(args.output_dir / "official_velogru_test.command.json",
                   json.dumps({"command": test_command, "returncode": test_result.returncode,
                               "wall_seconds": test_seconds}, indent=2) + "\n")
    if test_result.returncode:
        raise RuntimeError("official VeloGRU test failed; see retained log")
    test_metrics = parse_official_test_log(test_result.stdout)

    original_ga = args.source_dir / "Genetic_algorithm/ga_velocity_pattern.add.time.pearson.ss.py"
    unmodified_log = args.output_dir / "official_ga_unmodified_attempt1.log"
    unmodified = subprocess.run([sys.executable, str(original_ga)], cwd=args.output_dir, env=env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    write_text_new(unmodified_log, unmodified.stdout)
    write_text_new(args.output_dir / "official_ga_unmodified_attempt1.returncode.txt",
                   str(unmodified.returncode) + "\n")
    unmodified_failure_preserved = (unmodified.returncode != 0
                                    and "ModuleNotFoundError: No module named 'Mimo_data'" in unmodified.stdout)

    import numpy as np
    import scipy
    import sklearn
    import matplotlib
    import torch
    from scipy.stats import pearsonr
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    sys.path.insert(0, str(args.source_dir / "Genetic_algorithm"))
    sys.path.insert(0, str(args.source_dir / "VeloGRU"))

    runtime_path = args.output_dir / "ga_velocity_pattern.bounded_runtime.py"
    plot_path = args.output_dir / "bounded_ga_velocity_pattern.jpg"
    patched, replacements = build_ga_runtime(original_ga.read_text(), subset, ecoli_weight,
                                             yeast_weight, plot_path, args.population_size,
                                             args.generations)
    write_text_new(runtime_path, patched)
    diff = "".join(difflib.unified_diff(original_ga.read_text().splitlines(keepends=True),
                                        patched.splitlines(keepends=True),
                                        fromfile=str(original_ga), tofile=str(runtime_path)))
    write_text_new(args.output_dir / "ga_bounded_runtime.diff", diff)

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    namespace = {"__name__": "__main__", "__file__": str(runtime_path), "__package__": None}
    ga_log = args.output_dir / "bounded_ga_execution.log"
    ga_started = time.perf_counter()
    with ga_log.open("x", encoding="utf-8") as handle:
        with contextlib.redirect_stdout(handle), contextlib.redirect_stderr(handle):
            exec(compile(patched, str(runtime_path), "exec"), namespace)
    ga_seconds = time.perf_counter() - ga_started
    cache_info = namespace["evaluate_fitness"].cache_info()._asdict()
    start_sequence = namespace["start_seq"]
    best_sequence = namespace["best_rna_sequence"]
    if namespace["seqs"] != native_sequence or namespace["target_sequence"] != translate(native_sequence):
        raise RuntimeError("GA target is not the selected seventh record")

    seq2feature = namespace["seq2feature"]

    def predict(model, sequence):
        features = seq2feature(sequence).to(torch.float32)
        with torch.no_grad():
            output = model(features, torch.tensor([[features.shape[1]]]))
        return output.reshape(-1)[:features.shape[1]].detach().cpu().numpy().astype(float).tolist()

    ecoli_model = namespace["velo_model1"]
    yeast_model = namespace["velo_model"]
    ecoli_model.eval()
    yeast_model.eval()
    from VeloGRU_data import load_data
    data_x, data_y, data_len = load_data(str(subset), True, True, False, True)
    if not torch.cuda.is_available():
        raise RuntimeError("official run.py test requires CUDA for its serialized checkpoint")
    official_device = torch.device("cuda:0")
    torch.use_deterministic_algorithms(False)
    official_gpu_model = torch.load(str(ecoli_weight))
    official_gpu_model.eval()
    native_predictions = []
    per_gene_pearson = []
    for index, record in enumerate(selected):
        sequence = "".join(record["codons"])
        length = int(data_len[index].item())
        if length != len(record["codons"]):
            raise RuntimeError("official loader length mismatch")
        with torch.no_grad():
            prediction = official_gpu_model(data_x[index:index + 1].to(official_device),
                                            data_len[index:index + 1])
        values_array = prediction.reshape(-1)[:length].detach().cpu().numpy()
        density_array = data_y[index, :length, 0].detach().cpu().numpy()
        if not np.allclose(density_array.astype(float), normalized_density(record["count"]), rtol=0, atol=5e-7):
            raise RuntimeError("official loader density mismatch beyond float32 round-off")
        correlation_value = pearsonr(density_array, values_array)[0]
        per_gene_pearson.append(correlation_value)
        correlation = float(correlation_value)
        values = values_array.astype(float).tolist()
        density = density_array.astype(float).tolist()
        native_predictions.append({"record_id": record["name"], "source_index": record["source_index"],
                                   "native_sequence": sequence, "observed_count": record["count"],
                                   "normalized_density": density, "ecoli_prediction": values,
                                   "pearson_density_vs_prediction_diagnostic": correlation})
    native_prediction_path = args.output_dir / "velogru_native_predictions.json"
    write_json_new(native_prediction_path, {"records": native_predictions})
    recomputed_mean = float(np.mean(per_gene_pearson))
    recomputed_std = float(np.std(per_gene_pearson))
    metric_delta = max(abs(recomputed_mean - test_metrics["mean_pearson"]),
                       abs(recomputed_std - test_metrics["std_pearson"]))
    if metric_delta > 1e-7:
        raise RuntimeError(f"official test/native prediction reconciliation failed: {metric_delta}")
    torch.use_deterministic_algorithms(True)

    sequences = {"native": native_sequence, "start": start_sequence, "best": best_sequence}
    fitness = {name: float(namespace["evaluate_fitness"](sequence))
               for name, sequence in sequences.items()}
    ga_predictions = {}
    for name, sequence in sequences.items():
        ga_predictions[name] = {
            "sequence": sequence,
            "qc": synonymous_qc(sequence, native_sequence),
            "ecoli_prediction": predict(ecoli_model, sequence),
            "yeast_prediction": predict(yeast_model, sequence),
            "fitness": fitness[name],
        }
    ga_predictions["native"]["normalized_density"] = normalized_density(target["count"])
    ga_predictions["native"]["observed_count"] = target["count"]
    ga_prediction_path = args.output_dir / "ga_native_start_best_predictions.json"
    write_json_new(ga_prediction_path, ga_predictions)
    trace = {"seed": args.seed, "population_size": args.population_size,
             "generations": args.generations, "mutation_rate": namespace["MUTATION_RATE"],
             "target_record": target["name"], "target_source_index": target["source_index"],
             "target_record_index_in_subset": 6, "native_sequence": native_sequence,
             "target_protein": namespace["target_sequence"],
             "start_sequence": start_sequence, "best_sequence": best_sequence,
             "end_sequence": namespace["end_seq"], "end_equals_best": namespace["end_seq"] == best_sequence,
             "fitness": fitness, "final_population_returned_by_official_implementation": False,
             "cache_info_after_ga": cache_info, "wall_seconds": ga_seconds}
    trace_path = args.output_dir / "ga_trace.json"
    write_json_new(trace_path, trace)
    fasta_path = args.output_dir / "ga_native_start_best.fasta"
    write_text_new(fasta_path, "".join(f">{name}|{target['name']}\n{sequence}\n"
                                      for name, sequence in sequences.items()))

    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], text=True,
                            stdout=subprocess.PIPE, check=True).stdout
    write_text_new(args.output_dir / "pip_freeze.txt", freeze)
    environment = {"python_executable": sys.executable, "python": platform.python_version(),
                   "torch": torch.__version__, "numpy": np.__version__, "scipy": scipy.__version__,
                   "sklearn": sklearn.__version__, "matplotlib": matplotlib.__version__,
                   "ga_device": "cpu", "official_test_device": str(official_device),
                   "gpu_name": torch.cuda.get_device_name(0), "cuda_visible_devices": "0",
                   "torch_threads": 1, "ga_deterministic_algorithms": True,
                   "official_test_deterministic_algorithms": False,
                   "weights_only_load": False, "weights_only_mechanism": "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1",
                   "source_commit": COMMIT}
    write_json_new(args.output_dir / "environment.json", environment)

    legal_count = sum(ga_predictions[name]["qc"]["legal_synonymous_cds"] for name in ("start", "best"))
    official_test_pass = (test_metrics["feature_dimension"] == 105 and len(native_predictions) == 7
                          and all(np.isfinite(x["ecoli_prediction"]).all() for x in native_predictions))
    status = ("BOUNDED_OFFICIAL_ALGORITHM_EXECUTION_COMPLETE"
              if official_test_pass and unmodified_failure_preserved and legal_count == 2 else "FAILED")
    artifact_paths = [subset, test_log, args.output_dir / "official_velogru_test.command.json",
                      args.output_dir / "bounded_ecoli_0.6_test_relationship_result.jpg",
                      unmodified_log, args.output_dir / "official_ga_unmodified_attempt1.returncode.txt",
                      runtime_path, args.output_dir / "ga_bounded_runtime.diff", ga_log, plot_path,
                      native_prediction_path, ga_prediction_path, trace_path, fasta_path,
                      args.output_dir / "environment.json", args.output_dir / "pip_freeze.txt"]
    report = {
        "schema_version": "a8-rk05-veloharmo-official-smoke-v1",
        "created_at": datetime.now(timezone.utc).isoformat(), "status": status,
        "source_commit": COMMIT, "materialization": str(args.materialization),
        "materialization_sha256": sha256(args.materialization), "source_file_sha256": source_hashes,
        "matrix": str(matrix), "matrix_sha256": sha256(matrix),
        "environment": environment, "selected_records": [
            {"record_id": x["name"], "source_index": x["source_index"], "codons": len(x["codons"]),
             "coverage_fraction": float(np.mean(np.asarray(x["count"]) > 0.5))} for x in selected],
        "selection_rule": "Seven shortest records with >=30 codons, aligned finite features/counts, nonconstant counts and >=1 count >0.5; ties by record ID/source index; GA uses original hardcoded subset index 6.",
        "official_velogru_test": {
            "unmodified_entrypoint": "VeloGRU/run.py test", "command": test_command,
            "returncode": test_result.returncode, "wall_seconds": test_seconds,
            "device": str(official_device), "feature_dimension": test_metrics["feature_dimension"],
            "mean_pearson": test_metrics["mean_pearson"], "std_pearson": test_metrics["std_pearson"],
            "recomputed_mean_pearson": recomputed_mean, "recomputed_std_pearson": recomputed_std,
            "metric_delta": metric_delta, "records": len(native_predictions),
            "model_parameter_count": sum(x.numel() for x in ecoli_model.parameters()),
            "diagnostic_only_not_held_out": True,
        },
        "official_ga_unmodified": {"returncode": unmodified.returncode,
                                    "expected_missing_module_failure": unmodified_failure_preserved,
                                    "executed_successfully": False},
        "bounded_ga": {
            "compatibility_patch_required": True, "patch": replacements,
            "algorithm_source": str(original_ga), "algorithm_source_sha256": sha256(original_ga),
            "population_size": args.population_size, "generations": args.generations,
            "seed": args.seed, "wall_seconds": ga_seconds, "device": "cpu", "target_record": target["name"],
            "target_codons": len(target["codons"]), "native_sequence": native_sequence,
            "native_terminal_stop": translate(native_sequence).endswith("*"),
            "start_sequence": start_sequence, "best_sequence": best_sequence,
            "fitness": fitness, "best_minus_start": fitness["best"] - fitness["start"],
            "best_minus_native": fitness["best"] - fitness["native"],
            "start_to_best_improved": fitness["best"] > fitness["start"],
            "legal_synonymous_count": legal_count, "candidate_count": 2,
            "unique_sequence_count": len(set(sequences.values())),
            "cache_info_after_ga": cache_info,
            "objective": "Pearson similarity between native E. coli-model reference pattern and yeast-model candidate pattern; predicted patterns, not experimental function.",
        },
        "artifacts": {path.name: artifact(path) for path in artifact_paths},
        "official_test_unmodified": True, "ga_compatibility_patch": True,
        "model_training": False, "publication_metrics_reproduced": False,
        "held_out_performance": False, "main_baseline_comparison": False,
        "dense_budget_complete": False, "matched_cost_comparison": False,
        "five_species_processed_matrices_complete": False, "functional_ood": False,
        "sota_claim": False,
        "scope": "Unmodified official VeloGRU test on seven length-selected records plus a seeded CPU execution of the official GA algorithm after only import/path/plot and population/generation compatibility edits; not held-out performance, a full harmonization benchmark, functional OOD, or SOTA.",
    }
    write_json_new(args.report, report)
    print(json.dumps({"status": status, "official_test": official_test_pass,
                      "unmodified_ga_failure_preserved": unmodified_failure_preserved,
                      "ga_legal": f"{legal_count}/2", "fitness": fitness,
                      "report": str(args.report)}), flush=True)
    if status != "BOUNDED_OFFICIAL_ALGORITHM_EXECUTION_COMPLETE":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
