import torch

from codonflow.data.dataset import corrupt_x_t
from codonflow.models.edit_flow import EditFlowConfig, EditFlowTransformer
from codonflow.train.run_pretrain import validate_packed


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
