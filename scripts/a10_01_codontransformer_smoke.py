"""Run the official CodonTransformer README example as a CUDA-only smoke test."""
from __future__ import annotations

import argparse
import importlib
import json
import platform
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


PROTOCOL = "a10_01_codontransformer_official_gpu_smoke_v1"
DEFAULT_MODEL_ID = "adibvafa/CodonTransformer"
README_PROTEIN = (
    "MALWMRLLPLLALLALWGPDPAAAFVNQHLCGSHLVEALYLVCGERGFFYTPKTRREAEDLQVGQVEL"
    "GGGPGAGSLQPLALEGSLQKRGIVEQCCTSICSLYQLENYCN"
)
ORGANISM = "Escherichia coli general"
ATTENTION_TYPE = "original_full"
BASES = "TCAG"
AMINO_ACIDS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
CODON_TABLE = {
    first + second + third: AMINO_ACIDS[index]
    for index, (first, second, third) in enumerate(
        (first, second, third)
        for first in BASES
        for second in BASES
        for third in BASES
    )
}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--source-dir", required=True,
        help="Path to the official CodonTransformer source checkout",
    )
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument(
        "--model-revision", default=None,
        help="Explicit 40-character hexadecimal model revision for provenance",
    )
    parser.add_argument("--output", "--out", dest="output", required=True)
    return parser.parse_args(argv)


def validate_args(args):
    source_dir = Path(args.source_dir).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if not source_dir.is_dir():
        raise ValueError(f"official CodonTransformer source directory not found: {source_dir}")
    if not args.model_id or not args.model_id.strip():
        raise ValueError("model id must not be empty")
    if args.model_revision is not None and not re.fullmatch(
            r"[0-9a-fA-F]{40}", args.model_revision):
        raise ValueError("model revision must be exactly 40 hexadecimal characters")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    return source_dir, output


def require_cuda(torch):
    try:
        available = torch.cuda.is_available()
    except Exception as exc:
        raise RuntimeError(
            "CUDA availability check failed; CPU fallback is forbidden for this smoke test",
        ) from exc
    if not available:
        raise RuntimeError(
            "CUDA unavailable; official CodonTransformer smoke requires CUDA and forbids CPU fallback",
        )
    if torch.cuda.device_count() < 1:
        raise RuntimeError("CUDA reports no devices; CPU fallback is forbidden")
    return torch.device("cuda:0")


def git_revision(path):
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=path, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def source_revision(source_dir):
    revision = git_revision(source_dir)
    if revision is not None:
        return revision, "git"
    match = re.search(r"(?<![0-9a-f])([0-9a-f]{40})(?![0-9a-f])", source_dir.name)
    if match:
        return match.group(1), "source_directory_name"
    return None, "unavailable"


def commit_hash(value):
    direct = getattr(value, "_commit_hash", None)
    if direct:
        return direct
    config_hash = getattr(getattr(value, "config", None), "_commit_hash", None)
    if config_hash:
        return config_hash
    init_kwargs = getattr(value, "init_kwargs", None)
    if isinstance(init_kwargs, dict):
        return init_kwargs.get("_commit_hash")
    return None


def translate_dna(dna):
    if not isinstance(dna, str) or not dna:
        raise ValueError("predicted DNA must be a nonempty string")
    normalized = dna.upper()
    if len(normalized) % 3:
        raise ValueError(f"predicted DNA length is not divisible by three: {len(normalized)}")
    invalid = sorted(set(normalized) - set("ACGT"))
    if invalid:
        raise ValueError(f"predicted DNA contains invalid bases: {invalid}")
    return "".join(
        CODON_TABLE[normalized[index:index + 3]]
        for index in range(0, len(normalized), 3)
    )


def output_record(dna, protein):
    translation = translate_dna(dna)
    if "*" in translation[:-1]:
        raise ValueError("predicted DNA contains an internal stop codon")
    translated_protein = translation[:-1] if translation.endswith("*") else translation
    if translated_protein != protein:
        raise ValueError(
            "predicted DNA translation mismatch: "
            f"expected {protein}, observed {translated_protein}",
        )
    return {
        "dna": dna,
        "length_nt": len(dna),
        "length_codons": len(dna) // 3,
        "has_terminal_stop": translation.endswith("*"),
        "translated_protein": translated_protein,
        "translation_matches_protein": True,
    }


def normalize_outputs(value, expected_count):
    predictions = list(value) if isinstance(value, (list, tuple)) else [value]
    if len(predictions) != expected_count:
        raise ValueError(f"expected {expected_count} DNA sequences, received {len(predictions)}")
    sequences = []
    for prediction in predictions:
        dna = getattr(prediction, "predicted_dna", None)
        if not isinstance(dna, str):
            raise TypeError(
                "predict_dna_sequence must return DNASequencePrediction objects "
                "with string predicted_dna attributes",
            )
        sequences.append(dna)
    return sequences


def cuda_environment(torch, device):
    properties = torch.cuda.get_device_properties(0)
    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "device": str(device),
        "cuda_device_count": torch.cuda.device_count(),
        "gpu": {
            "index": 0,
            "name": torch.cuda.get_device_name(0),
            "total_memory_bytes": int(properties.total_memory),
        },
        "cpu_fallback": False,
    }


def run_smoke(args, command_args):
    source_dir, output = validate_args(args)
    total_started = time.perf_counter()
    started_utc = datetime.now(timezone.utc).isoformat()

    torch = importlib.import_module("torch")
    device = require_cuda(torch)
    environment = cuda_environment(torch, device)

    sys.path.insert(0, str(source_dir))
    transformers = importlib.import_module("transformers")
    prediction_module = importlib.import_module("CodonTransformer.CodonPrediction")
    predict_dna_sequence = prediction_module.predict_dna_sequence

    load_started = time.perf_counter()
    tokenizer = transformers.AutoTokenizer.from_pretrained(args.model_id)
    model = transformers.BigBirdForMaskedLM.from_pretrained(
        args.model_id, attention_type=ATTENTION_TYPE,
    )
    model.to(device)
    model.eval()
    torch.cuda.synchronize()
    model_load_seconds = time.perf_counter() - load_started
    torch.cuda.reset_peak_memory_stats()

    revision, revision_source = source_revision(source_dir)
    common = {
        "protein": README_PROTEIN,
        "organism": ORGANISM,
        "model": model,
        "tokenizer": tokenizer,
        "device": device,
        "attention_type": ATTENTION_TYPE,
    }
    specifications = [
        ("deterministic", {"deterministic": True}, 1, None),
        (
            "stochastic_seed0",
            {
                "deterministic": False,
                "num_sequences": 2,
                "match_protein": True,
            },
            2,
            0,
        ),
    ]
    runs = []
    for name, configuration, expected_count, seed in specifications:
        recorded_configuration = {
            "attention_type": ATTENTION_TYPE,
            **configuration,
        }
        if seed is not None:
            torch.manual_seed(seed)
            if hasattr(torch.cuda, "manual_seed_all"):
                torch.cuda.manual_seed_all(seed)
            recorded_configuration["seed"] = seed
        torch.cuda.synchronize()
        call_started = time.perf_counter()
        returned = predict_dna_sequence(**common, **configuration)
        torch.cuda.synchronize()
        wall_seconds = time.perf_counter() - call_started
        sequences = normalize_outputs(returned, expected_count)
        runs.append({
            "name": name,
            "configuration": recorded_configuration,
            "wall_time_seconds": wall_seconds,
            "return_type": type(returned).__name__,
            "outputs": [output_record(dna, README_PROTEIN) for dna in sequences],
        })

    script = Path(__file__).resolve()
    executable_command = [sys.executable, str(script), *command_args]
    result = {
        "protocol": PROTOCOL,
        "status": "ok",
        "scope": "execution_smoke_only_no_scientific_or_performance_claim",
        "started_utc": started_utc,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "commit": {
            "codonflow": git_revision(script.parents[1]),
            "codontransformer": revision,
            "codontransformer_revision_source": revision_source,
        },
        "source_dir": str(source_dir),
        "model": {
            "id": args.model_id,
            "revision": args.model_revision or commit_hash(model),
            "tokenizer_revision": commit_hash(tokenizer),
            "attention_type": ATTENTION_TYPE,
        },
        "environment": environment,
        "command": {
            "executable": sys.executable,
            "script": str(script),
            "args": list(command_args),
            "shell": shlex.join(executable_command),
        },
        "input": {
            "protein": README_PROTEIN,
            "protein_length_aa": len(README_PROTEIN),
            "organism": ORGANISM,
        },
        "runs": runs,
        "cost": {
            "total_wall_time_seconds": time.perf_counter() - total_started,
            "model_load_wall_time_seconds": model_load_seconds,
            "inference_wall_time_seconds": sum(run["wall_time_seconds"] for run in runs),
            "inference_peak_cuda_memory_bytes": int(torch.cuda.max_memory_allocated()),
            "monetary_usd": None,
            "monetary_cost_status": "not_measured",
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    print(json.dumps({
        "status": "ok",
        "output": str(output),
        "run_names": [run["name"] for run in runs],
        "total_wall_time_seconds": result["cost"]["total_wall_time_seconds"],
    }))
    return result


def main(argv=None):
    command_args = sys.argv[1:] if argv is None else list(argv)
    args = parse_args(command_args)
    run_smoke(args, command_args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
