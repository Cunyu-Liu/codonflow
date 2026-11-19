import math

import pytest
import torch

from codonflow.core.tokenizer import PAD_ID, encode_cds
from codonflow.data.ribokinetic import (
    TargetNormalizer,
    VariantRecord,
    collate_ribokinetic,
    fit_host_vocabulary,
    read_functional_csv,
    read_velocity_long_csv,
)
from codonflow.models.ribokinetic import (
    RiboKineticConfig,
    RiboKineticModel,
    build_pair_channel,
    codon_pair_score,
    codon_pair_table,
    ribokinetic_loss,
    utr_cds_pair_scores,
)


def _record(record_id="r1", split="train", host="ecoli", function=1.0, utr=None):
    return VariantRecord(
        record_id=record_id,
        cds="ATGGCTGCTTAA",
        split=split,
        cluster_id="c1",
        host=host,
        function_target=function,
        initiation_target=(0.1, 0.2, 0.3, 0.0),
        velocity_target=(1.0, float("nan"), 3.0, 0.0),
        decay_target=(0.0, 0.1, 0.2, 0.0),
        utr=utr,
    )


def _tiny_model(**kwargs):
    return RiboKineticModel(
        RiboKineticConfig(
            d_model=16,
            n_layers=2,
            n_heads=4,
            dropout=0.0,
            max_len=32,
            initiation_window=3,
            long_range_stride=4,
            **kwargs,
        )
    )


def test_pair_scores_are_antiparallel_and_special_tokens_are_zero():
    assert codon_pair_score("ATG", "CAT", allow_wobble=False) == 3
    assert codon_pair_score("ATG", "ATG", allow_wobble=False) == 0
    table = codon_pair_table()
    assert table[PAD_ID].sum().item() == 0
    with pytest.raises(ValueError):
        codon_pair_score("ATN", "CAT")


def test_pair_channel_has_initiation_axial_local_and_finite_diagonal():
    ids = torch.tensor([encode_cds("ATG" * 40, add_special=False)])
    pad = torch.zeros_like(ids, dtype=torch.bool)
    bias, summary = build_pair_channel(ids, pad, initiation_window=3, long_range_stride=8)
    assert bias.shape == (1, 40, 40)
    assert bias[0, 0, 39] > -10000  # high-resolution initiation interactions
    assert bias[0, 8, 16] > -10000  # axial long-range interaction
    assert bias[0, 20, 21] > -10000  # local interaction
    assert bias[0, 20, 25] == -10000
    assert torch.all(torch.diagonal(bias, dim1=1, dim2=2) > -10000)
    assert torch.isfinite(summary).all()


def test_utr_cds_pair_scores_and_padding():
    ids = torch.tensor([encode_cds("ATG", add_special=False)])
    utr = torch.tensor([[0, 1, 2, 3, 4]])  # A C G T pad
    scores = utr_cds_pair_scores(ids, utr, allow_wobble=False)
    assert scores.shape == (1, 1, 5)
    assert scores[0, 0].tolist() == [1, 1, 0, 1, 0]


def test_forward_heads_utr_and_padding_are_finite():
    model = _tiny_model().eval()
    records = [_record(utr="AACCGG"), _record("r2", utr="TT")]
    batch = collate_ribokinetic(records)
    # Add artificial right padding and verify it is excluded from outputs.
    ids = torch.cat([batch["codon_ids"], torch.full((2, 2), PAD_ID)], dim=1)
    pad = torch.cat([batch["pad_mask"], torch.ones((2, 2), dtype=torch.bool)], dim=1)
    with torch.no_grad():
        out = model(
            ids,
            pad,
            host_ids=batch["host_ids"],
            utr_ids=batch["utr_ids"],
            budget=torch.tensor([0.2, 0.4]),
        )
    assert out["function"].shape == (2,)
    assert out["function_log_scale"].shape == (2,)
    assert out["initiation"].shape == ids.shape
    assert out["velocity"].shape == ids.shape
    assert out["decay"].shape == ids.shape
    assert out["utr_pair"].shape[:2] == ids.shape
    assert torch.isfinite(out["function"]).all()
    assert torch.isfinite(out["velocity"]).all()
    assert out["velocity"][:, -2:].abs().sum().item() == 0


def test_constant_parameter_ablation_changes_information_path_not_architecture():
    model = _tiny_model().eval()
    batch = collate_ribokinetic([_record(), _record("r2")])
    parameter_count = sum(p.numel() for p in model.parameters())
    assert parameter_count == sum(p.numel() for p in _tiny_model().parameters())
    with torch.no_grad():
        none = model(
            batch["codon_ids"], batch["pad_mask"],
            active_mechanisms={name: False for name in ("initiation", "velocity", "decay", "pair")},
        )
        full = model(batch["codon_ids"], batch["pad_mask"])
    assert not torch.allclose(none["function"], full["function"])
    for name in ("initiation", "velocity", "decay", "pair_summary"):
        assert name in none and name in full
    with pytest.raises(ValueError):
        model(batch["codon_ids"], batch["pad_mask"], active_mechanisms={"unknown": True})


def test_multitask_loss_backpropagates_to_every_supervised_head():
    model = _tiny_model()
    batch = collate_ribokinetic([_record(), _record("r2", function=2.0)])
    out = model(batch["codon_ids"], batch["pad_mask"], host_ids=batch["host_ids"])
    loss, terms = ribokinetic_loss(out, batch)
    assert torch.isfinite(loss)
    assert all(name in terms for name in ("function", "initiation", "velocity", "decay", "total"))
    loss.backward()
    for name in ("initiation_head", "velocity_head", "decay_head", "function_head"):
        parameters = dict(model.named_parameters())
        matching = [p.grad for key, p in parameters.items() if key.startswith(name) and p.grad is not None]
        assert matching and all(torch.isfinite(g).all() for g in matching)


def test_loss_requires_a_real_target():
    model = _tiny_model()
    record = VariantRecord("unlabeled", "ATGTAA", "train")
    batch = collate_ribokinetic([record])
    out = model(batch["codon_ids"], batch["pad_mask"])
    with pytest.raises(ValueError, match="no supervised"):
        ribokinetic_loss(out, batch)


def test_functional_csv_strict_validation_and_train_only_host_vocab(tmp_path):
    path = tmp_path / "functional.csv"
    path.write_text(
        "construct_id,cds,expression_value,split_assignment,operational_protein_cluster,host\n"
        "a,ATGGCTGCTTAA,1,train,c1,ecoli\n"
        "b,ATGGCCTAA,2,dev,c2,yeast\n"
        "c,ATGGCTTAA,3,test,c3,human\n"
    )
    records = read_functional_csv(str(path))
    assert len(records) == 3
    vocab = fit_host_vocabulary(records)
    assert vocab == {"ecoli": 1}
    batch = collate_ribokinetic(records, vocab)
    assert batch["host_ids"].tolist() == [1, 0, 0]
    bad = tmp_path / "bad.csv"
    bad.write_text(
        "construct_id,cds,expression_value,split_assignment\n"
        "bad,ATGNNNTAA,1,train\n"
    )
    with pytest.raises(ValueError, match="invalid functional row"):
        read_functional_csv(str(bad))


def test_functional_untouched_requires_explicit_exclusion(tmp_path):
    path = tmp_path / "with_untouched.csv"
    path.write_text(
        "construct_id,cds,expression_value,split_assignment\n"
        "a,ATGTAA,1,train\n"
        "u,,2,functional_untouched\n"
    )
    records = read_functional_csv(str(path), include_splits={"train"})
    assert [r.record_id for r in records] == ["a"]
    with pytest.raises(ValueError, match="invalid functional row"):
        read_functional_csv(str(path), include_splits={"train", "functional_untouched"})


def test_velocity_long_loader_preserves_missing_positions_and_rejects_duplicates(tmp_path):
    path = tmp_path / "velocity.csv"
    path.write_text(
        "gene,cds,pos,count,split\n"
        "g1,ATGGCTGCTTAA,0,10,train\n"
        "g1,ATGGCTGCTTAA,2,30,train\n"
    )
    record = read_velocity_long_csv(
        str(path), "gene", "cds", "pos", "count", "split"
    )[0]
    assert len(record.velocity_target) == 4
    assert record.velocity_target[0] == 10
    assert math.isnan(record.velocity_target[1])
    batch = collate_ribokinetic([record])
    assert batch["velocity_mask"].tolist() == [[True, False, True, False]]
    path.write_text(path.read_text() + "g1,ATGGCTGCTTAA,2,31,train\n")
    with pytest.raises(ValueError, match="duplicate codon position"):
        read_velocity_long_csv(str(path), "gene", "cds", "pos", "count", "split")


def test_target_normalizer_is_fitted_on_train_only():
    train = VariantRecord("a", "ATGTAA", "train", velocity_target=(1.0, 3.0))
    dev = VariantRecord("b", "ATGTAA", "dev", velocity_target=(100.0, 1000.0))
    normalizer = TargetNormalizer.fit([train, dev], "velocity", log1p=False)
    assert normalizer.mean == 2.0
    assert normalizer.scale == 1.0
    assert normalizer.train_value_count == 2
    transformed = normalizer.apply([train, dev])
    assert transformed[0].velocity_target == (-1.0, 1.0)
    assert transformed[1].velocity_target == (98.0, 998.0)
    assert normalizer.to_dict()["fit_split"] == "train_only"


def test_model_rejects_length_beyond_config():
    model = _tiny_model()
    ids = torch.zeros((1, 33), dtype=torch.long)
    with pytest.raises(ValueError, match="max_len"):
        model(ids, torch.zeros_like(ids, dtype=torch.bool))
