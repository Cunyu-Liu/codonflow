import torch
from unittest.mock import patch

from codonflow.data.dataset import corrupt_x_t, corrupt_x_t_synonymous
from codonflow.models.edit_flow import EditFlowConfig, EditFlowTransformer
from codonflow.train.run_pretrain import conditionality_probe, validate_packed


def test_validation_is_reproducible_across_calls():
    model = EditFlowTransformer(EditFlowConfig(d_model=32, n_layers=1, n_heads=4, dropout=0.0))
    device = torch.device("cpu")
    batches = [[list(range(8))]]
    first = validate_packed(model, batches, device, seed=1729, token_only_at_edits=True)
    second = validate_packed(model, batches, device, seed=1729, token_only_at_edits=True)
    assert first == second


def test_corruption_preserves_special_tokens_with_cpu_generator():
    ids = torch.tensor([[65, 0, 1, 66, 64]])
    generator = torch.Generator(device="cpu").manual_seed(7)
    corrupted = corrupt_x_t(ids, generator=generator)
    assert corrupted[0, 0].item() == 65
    assert corrupted[0, -2].item() == 66
    assert corrupted[0, -1].item() == 64


def test_validation_generator_uses_model_device():
    model = EditFlowTransformer(EditFlowConfig(d_model=32, n_layers=1, n_heads=4, dropout=0.0))
    device = torch.device("cpu")
    with patch("codonflow.train.run_pretrain.torch.Generator", wraps=torch.Generator) as constructor:
        validate_packed(model, [[list(range(8))]], device, seed=1729, token_only_at_edits=True)
    constructor.assert_called_once_with(device=device)


def test_conditionality_probe_uses_device_and_matching_corruption():
    model = EditFlowTransformer(EditFlowConfig(d_model=32, n_layers=1, n_heads=4, dropout=0.0))
    with patch("codonflow.data.dataset.read_fasta", return_value=[("x", "ATGGCTTAA")]), \
            patch("codonflow.train.run_pretrain.torch.Generator", wraps=torch.Generator) as constructor, \
            patch("codonflow.data.dataset.corrupt_x_t_synonymous", wraps=corrupt_x_t_synonymous) as corrupt:
        gap = conditionality_probe(model, torch.device("cpu"), corruption="synonymous")
    assert gap >= 0
    assert constructor.call_count == 2
    assert all(call.kwargs["device"] == torch.device("cpu") for call in constructor.call_args_list)
    assert corrupt.call_count == 2
