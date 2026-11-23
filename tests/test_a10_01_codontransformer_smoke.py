import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from scripts import a10_01_codontransformer_smoke as smoke


AA_TO_CODON = {
    "A": "GCT", "R": "CGT", "N": "AAT", "D": "GAT", "C": "TGT",
    "Q": "CAA", "E": "GAA", "G": "GGT", "H": "CAT", "I": "ATT",
    "L": "CTG", "K": "AAA", "M": "ATG", "F": "TTT", "P": "CCT",
    "S": "TCT", "T": "ACT", "W": "TGG", "Y": "TAT", "V": "GTT",
}


def dna_for(protein):
    return "".join(AA_TO_CODON[amino_acid] for amino_acid in protein)


class FakeCuda:
    def __init__(self, available=True):
        self.available = available

    def is_available(self):
        return self.available

    def device_count(self):
        return 1 if self.available else 0

    def get_device_name(self, index):
        assert index == 0
        return "Fake CUDA GPU"

    def get_device_properties(self, index):
        assert index == 0
        return SimpleNamespace(total_memory=8_000_000_000)

    def synchronize(self):
        return None

    def reset_peak_memory_stats(self):
        return None

    def max_memory_allocated(self):
        return 123_456


class FakeModel:
    load_calls = []

    def __init__(self):
        self.config = SimpleNamespace(_commit_hash="model-revision")
        self.device = None
        self.eval_called = False

    @classmethod
    def from_pretrained(cls, model_id, **kwargs):
        cls.load_calls.append((model_id, kwargs))
        return cls()

    def to(self, device):
        self.device = device
        return self

    def eval(self):
        self.eval_called = True
        return self


class FakeTokenizer:
    load_calls = []

    def __init__(self):
        self.init_kwargs = {"_commit_hash": "tokenizer-revision"}

    @classmethod
    def from_pretrained(cls, model_id):
        cls.load_calls.append(model_id)
        return cls()


def install_fake_runtime(monkeypatch, tmp_path, cuda_available=True, mismatch=False):
    source = tmp_path / "CodonTransformer-source"
    prediction_path = source / "CodonTransformer" / "CodonPrediction.py"
    prediction_path.parent.mkdir(parents=True)
    prediction_path.write_text("")

    torch = ModuleType("torch")
    torch.__version__ = "2.5.1+fake"
    torch.version = SimpleNamespace(cuda="12.4")
    torch.cuda = FakeCuda(cuda_available)
    torch.device = lambda name: name
    torch.seed_calls = []
    torch.manual_seed = lambda seed: torch.seed_calls.append(("torch", seed))
    torch.cuda.manual_seed_all = lambda seed: torch.seed_calls.append(("cuda", seed))

    transformers = ModuleType("transformers")
    transformers.AutoTokenizer = FakeTokenizer
    transformers.BigBirdForMaskedLM = FakeModel

    package = ModuleType("CodonTransformer")
    package.__path__ = [str(prediction_path.parent)]
    prediction = ModuleType("CodonTransformer.CodonPrediction")
    prediction_calls = []

    def predict_dna_sequence(**kwargs):
        prediction_calls.append(kwargs)
        dna = dna_for(kwargs["protein"])
        if mismatch:
            dna = "GCT" + dna[3:]
        if kwargs["deterministic"]:
            return SimpleNamespace(predicted_dna=dna)
        return [SimpleNamespace(predicted_dna=dna), SimpleNamespace(predicted_dna=dna)]

    prediction.predict_dna_sequence = predict_dna_sequence
    package.CodonPrediction = prediction
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    monkeypatch.setitem(sys.modules, "CodonTransformer", package)
    monkeypatch.setitem(sys.modules, "CodonTransformer.CodonPrediction", prediction)
    monkeypatch.setattr(
        smoke, "git_revision",
        lambda path: "source-revision" if path == source else "codonflow-revision",
    )
    FakeModel.load_calls = []
    FakeTokenizer.load_calls = []
    return source, prediction_calls


def arguments(source, output):
    return ["--source-dir", str(source), "--output", str(output)]


def test_parameter_validation_rejects_missing_source_and_existing_output(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="source directory not found"):
        smoke.main(arguments(missing, tmp_path / "result.json"))

    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "result.json"
    output.write_text("keep")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        smoke.main(arguments(source, output))
    assert output.read_text() == "keep"

    with pytest.raises(ValueError, match="model id must not be empty"):
        smoke.main([*arguments(source, tmp_path / "other.json"), "--model-id", ""])

    for invalid_revision in ("0" * 39, "g" * 40):
        with pytest.raises(ValueError, match="40 hexadecimal characters"):
            smoke.main([
                *arguments(source, tmp_path / "invalid-revision.json"),
                "--model-revision", invalid_revision,
            ])


def test_cuda_unavailable_fails_before_official_imports(monkeypatch, tmp_path):
    source, _ = install_fake_runtime(monkeypatch, tmp_path, cuda_available=False)
    monkeypatch.delitem(sys.modules, "transformers")
    monkeypatch.delitem(sys.modules, "CodonTransformer.CodonPrediction")
    output = tmp_path / "result.json"

    with pytest.raises(RuntimeError, match="CUDA unavailable.*forbids CPU fallback"):
        smoke.main(arguments(source, output))
    assert not output.exists()


def test_fake_official_runtime_writes_complete_schema(monkeypatch, tmp_path):
    source, prediction_calls = install_fake_runtime(monkeypatch, tmp_path)
    output = tmp_path / "nested" / "result.json"
    argv = arguments(source, output)

    assert smoke.main(argv) == 0
    payload = json.loads(output.read_text())
    assert payload["protocol"] == smoke.PROTOCOL
    assert payload["status"] == "ok"
    assert payload["scope"] == "execution_smoke_only_no_scientific_or_performance_claim"
    assert payload["commit"] == {
        "codonflow": "codonflow-revision",
        "codontransformer": "source-revision",
        "codontransformer_revision_source": "git",
    }
    assert payload["model"] == {
        "id": smoke.DEFAULT_MODEL_ID,
        "revision": "model-revision",
        "tokenizer_revision": "tokenizer-revision",
        "attention_type": "original_full",
    }
    assert payload["environment"]["device"] == "cuda:0"
    assert payload["environment"]["gpu"]["name"] == "Fake CUDA GPU"
    assert payload["environment"]["cpu_fallback"] is False
    assert payload["command"]["args"] == argv
    assert payload["input"]["protein"] == smoke.README_PROTEIN
    assert payload["input"]["protein_length_aa"] == len(smoke.README_PROTEIN)
    assert payload["cost"]["monetary_usd"] is None
    assert payload["cost"]["inference_peak_cuda_memory_bytes"] == 123_456
    assert payload["cost"]["total_wall_time_seconds"] >= 0

    assert [run["name"] for run in payload["runs"]] == [
        "deterministic", "stochastic_seed0",
    ]
    deterministic, stochastic = payload["runs"]
    assert deterministic["configuration"] == {
        "attention_type": "original_full", "deterministic": True,
    }
    assert stochastic["configuration"] == {
        "attention_type": "original_full",
        "deterministic": False,
        "seed": 0,
        "num_sequences": 2,
        "match_protein": True,
    }
    assert len(deterministic["outputs"]) == 1
    assert len(stochastic["outputs"]) == 2
    for run in payload["runs"]:
        assert run["wall_time_seconds"] >= 0
        for record in run["outputs"]:
            assert record["dna"] == dna_for(smoke.README_PROTEIN)
            assert record["length_nt"] == 3 * len(smoke.README_PROTEIN)
            assert record["length_codons"] == len(smoke.README_PROTEIN)
            assert record["translated_protein"] == smoke.README_PROTEIN
            assert record["translation_matches_protein"] is True

    assert FakeTokenizer.load_calls == [smoke.DEFAULT_MODEL_ID]
    assert FakeModel.load_calls == [
        (smoke.DEFAULT_MODEL_ID, {"attention_type": "original_full"}),
    ]
    for call in prediction_calls:
        assert call["organism"] == "Escherichia coli general"
        assert call["device"] == "cuda:0"
        assert call["attention_type"] == "original_full"
    assert all("seed" not in call for call in prediction_calls)
    assert prediction_calls[1]["num_sequences"] == 2
    assert prediction_calls[1]["match_protein"] is True
    assert sys.modules["torch"].seed_calls == [("torch", 0), ("cuda", 0)]
    assert deterministic["return_type"] == "SimpleNamespace"
    assert stochastic["return_type"] == "list"

    original = output.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        smoke.main(argv)
    assert output.read_bytes() == original


def test_explicit_model_revision_overrides_detected_commit_hash(monkeypatch, tmp_path):
    source, _ = install_fake_runtime(monkeypatch, tmp_path)
    model_path = tmp_path / "official_model_9744dcc"
    revision = "9744dcc920d813066391fc828d7a590207f148e8"
    output = tmp_path / "explicit-revision.json"

    assert smoke.main([
        *arguments(source, output),
        "--model-id", str(model_path),
        "--model-revision", revision,
    ]) == 0
    payload = json.loads(output.read_text())
    assert payload["model"]["id"] == str(model_path)
    assert payload["model"]["revision"] == revision
    assert payload["model"]["tokenizer_revision"] == "tokenizer-revision"
    assert FakeTokenizer.load_calls == [str(model_path)]
    assert FakeModel.load_calls == [
        (str(model_path), {"attention_type": "original_full"}),
    ]


def test_fake_official_runtime_rejects_translation_mismatch(monkeypatch, tmp_path):
    source, _ = install_fake_runtime(monkeypatch, tmp_path, mismatch=True)
    output = tmp_path / "result.json"

    with pytest.raises(ValueError, match="translation mismatch"):
        smoke.main(arguments(source, output))
    assert not output.exists()


def test_normalize_outputs_extracts_predicted_dna():
    first = SimpleNamespace(predicted_dna="ATGGCT")
    second = SimpleNamespace(predicted_dna="ATGGCC")
    assert smoke.normalize_outputs(first, 1) == ["ATGGCT"]
    assert smoke.normalize_outputs([first, second], 2) == ["ATGGCT", "ATGGCC"]


@pytest.mark.parametrize(
    "value",
    ["ATGGCT", object(), SimpleNamespace(predicted_dna=123)],
)
def test_normalize_outputs_rejects_invalid_predictions(value):
    with pytest.raises(TypeError, match="DNASequencePrediction"):
        smoke.normalize_outputs(value, 1)


@pytest.mark.parametrize(
    "dna, message",
    [
        ("ATGA", "not divisible by three"),
        ("ATGN", "not divisible by three"),
        ("ATGNNN", "invalid bases"),
        ("ATGTAACTG", "internal stop"),
    ],
)
def test_translation_rejects_malformed_dna(dna, message):
    with pytest.raises(ValueError, match=message):
        smoke.output_record(dna, "M")
