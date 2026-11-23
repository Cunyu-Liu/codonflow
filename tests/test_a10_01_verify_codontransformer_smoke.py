import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "scripts" / "a10_01_verify_codontransformer_smoke.py"
MODEL_REVISION = "9744dcc920d813066391fc828d7a590207f148e8"
SOURCE_REVISION = "4a447b01dab860feb81b647ff1ff88ad598517f4"
AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"
CODONS = (
    "GCT", "TGT", "GAT", "GAA", "TTT",
    "GGT", "CAT", "ATT", "AAA", "CTG",
    "ATG", "AAT", "CCT", "CAA", "CGT",
    "TCT", "ACT", "GTT", "TGG", "TAT",
)
CODON_FOR_AMINO_ACID = dict(zip(AMINO_ACIDS, CODONS))
PROTEIN = (AMINO_ACIDS * 6)[:110]
DNA = "".join(CODON_FOR_AMINO_ACID[amino_acid] for amino_acid in PROTEIN) + "TAA"


def synthetic_output():
    return {
        "dna": DNA,
        "length_nt": len(DNA),
        "length_codons": len(DNA) // 3,
        "has_terminal_stop": True,
        "translated_protein": PROTEIN,
        "translation_matches_protein": True,
    }


def synthetic_report():
    return {
        "protocol": "a10_01_codontransformer_official_gpu_smoke_v1",
        "status": "ok",
        "scope": "execution_smoke_only_no_scientific_or_performance_claim",
        "started_utc": "2026-01-01T00:00:00+00:00",
        "finished_utc": "2026-01-01T00:00:01.5+00:00",
        "commit": {
            "codonflow": "1" * 40,
            "codontransformer": SOURCE_REVISION,
            "codontransformer_revision_source": "git",
        },
        "source_dir": "/synthetic/CodonTransformer",
        "model": {
            "id": "adibvafa/CodonTransformer",
            "revision": MODEL_REVISION,
            "tokenizer_revision": "2" * 40,
            "attention_type": "original_full",
        },
        "environment": {
            "python_version": "3.11.0",
            "platform": "Synthetic Linux",
            "torch_version": "2.5.1+synthetic",
            "torch_cuda_version": "12.4",
            "device": "cuda:0",
            "cuda_device_count": 1,
            "gpu": {
                "index": 0,
                "name": "Synthetic RTX 5090 GPU",
                "total_memory_bytes": 32_000_000_000,
            },
            "cpu_fallback": False,
        },
        "command": {
            "executable": "/synthetic/python",
            "script": "/synthetic/a10_01_codontransformer_smoke.py",
            "args": [],
            "shell": "/synthetic/python /synthetic/a10_01_codontransformer_smoke.py",
        },
        "input": {
            "protein": PROTEIN,
            "protein_length_aa": len(PROTEIN),
            "organism": "Escherichia coli general",
        },
        "runs": [
            {
                "name": "deterministic",
                "configuration": {
                    "attention_type": "original_full",
                    "deterministic": True,
                },
                "wall_time_seconds": 0.25,
                "return_type": "DNASequencePrediction",
                "outputs": [synthetic_output()],
            },
            {
                "name": "stochastic_seed0",
                "configuration": {
                    "attention_type": "original_full",
                    "deterministic": False,
                    "seed": 0,
                    "num_sequences": 2,
                    "match_protein": True,
                },
                "wall_time_seconds": 0.5,
                "return_type": "list",
                "outputs": [synthetic_output() for _ in range(2)],
            },
        ],
        "cost": {
            "total_wall_time_seconds": 1.5,
            "model_load_wall_time_seconds": 0.5,
            "inference_wall_time_seconds": 0.75,
            "inference_peak_cuda_memory_bytes": 123_456,
            "monetary_usd": None,
            "monetary_cost_status": "not_measured",
        },
    }


def write_json(path, payload):
    Path(path).write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def invoke_verifier(report_path, output_path):
    return subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--report-json",
            str(report_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def assert_rejected(report_path, output_path, failed_check):
    completed = invoke_verifier(report_path, output_path)
    assert completed.returncode == 1, completed.stderr
    result = read_json(output_path)
    assert result["passed"] is False
    assert result["checks"][failed_check] is False
    return result


@pytest.fixture
def report_path(tmp_path):
    path = tmp_path / "synthetic_codontransformer_smoke.json"
    write_json(path, synthetic_report())
    return path


def test_verifier_does_not_import_production_or_model_modules():
    tree = ast.parse(VERIFIER.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    forbidden = {
        "scripts", "codonflow", "torch", "transformers", "CodonTransformer", "importlib",
    }
    assert not any(
        module == name or module.startswith(f"{name}.")
        for module in imported
        for name in forbidden
    )


def test_synthetic_report_passes_through_cli(report_path, tmp_path):
    output_path = tmp_path / "verification.json"

    completed = invoke_verifier(report_path, output_path)

    assert completed.returncode == 0, completed.stderr
    result = read_json(output_path)
    assert result["passed"] is True
    assert all(result["checks"].values())
    assert result["checks"]["outputs.independent_translation"] is True
    assert result["checks"]["scope.execution_smoke_only"] is True


def test_dna_tampering_fails_independent_translation(report_path, tmp_path):
    report = read_json(report_path)
    report["runs"][0]["outputs"][0]["dna"] = "TGT" + report["runs"][0]["outputs"][0]["dna"][3:]
    write_json(report_path, report)

    result = assert_rejected(
        report_path,
        tmp_path / "dna_tampering.json",
        "outputs.independent_translation",
    )
    assert result["checks"]["outputs.translated_protein"] is True


def test_model_revision_tampering_fails(report_path, tmp_path):
    report = read_json(report_path)
    report["model"]["revision"] = "0" * 40
    write_json(report_path, report)

    assert_rejected(
        report_path,
        tmp_path / "model_revision_tampering.json",
        "model.revision",
    )


def test_cpu_fallback_tampering_fails(report_path, tmp_path):
    report = read_json(report_path)
    report["environment"]["device"] = "cpu"
    report["environment"]["cpu_fallback"] = True
    write_json(report_path, report)

    result = assert_rejected(
        report_path,
        tmp_path / "cpu_fallback_tampering.json",
        "environment.cpu_fallback_false",
    )
    assert result["checks"]["environment.cuda_0"] is False


@pytest.mark.parametrize("tamper", ["declared_count", "missing_output"])
def test_run_count_tampering_fails(report_path, tmp_path, tamper):
    report = read_json(report_path)
    if tamper == "declared_count":
        report["runs"][1]["configuration"]["num_sequences"] = 1
        failed_check = "runs.stochastic_seed0_two"
    else:
        report["runs"][1]["outputs"].pop()
        failed_check = "runs.stochastic_seed0_two"
    write_json(report_path, report)

    assert_rejected(report_path, tmp_path / f"{tamper}.json", failed_check)


def test_cost_tampering_fails(report_path, tmp_path):
    report = read_json(report_path)
    report["cost"]["total_wall_time_seconds"] = -0.01
    write_json(report_path, report)

    assert_rejected(
        report_path,
        tmp_path / "cost_tampering.json",
        "cost.nonnegative_time_and_memory",
    )


def test_non_execution_scope_fails(report_path, tmp_path):
    report = read_json(report_path)
    report["scope"] = "scientific_performance_claim"
    write_json(report_path, report)

    assert_rejected(
        report_path,
        tmp_path / "scope_tampering.json",
        "scope.execution_smoke_only",
    )


def test_cli_refuses_to_overwrite_existing_output(report_path, tmp_path):
    output_path = tmp_path / "verification.json"
    original = b"do not overwrite this synthetic sentinel\n"
    output_path.write_bytes(original)

    completed = invoke_verifier(report_path, output_path)

    assert completed.returncode == 2
    assert "Refusing to overwrite" in completed.stderr
    assert output_path.read_bytes() == original
