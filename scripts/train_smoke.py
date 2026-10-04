"""Training smoke test: edit-flow forward/backward on real CDS mini-batch."""
import sys

import torch
from torch.utils.data import DataLoader

sys.path.insert(0, "src")
from codonflow.data.dataset import CDSDataset, collate_batch, fixed_length_noise_like
from codonflow.models.edit_flow import EditFlowConfig, EditFlowTransformer, edit_flow_loss

torch.manual_seed(0)
dev = "cuda:0"
model = EditFlowTransformer(EditFlowConfig(d_model=256, n_layers=4, n_heads=8)).to(dev)
opt = torch.optim.AdamW(model.parameters(), lr=1e-5)
seqs = ["ATG" * 50 + "TAA", "ATG" * 80 + "TGA", "ATG" * 30 + "TAG"]
ds = CDSDataset(seqs)
dl = DataLoader(ds, batch_size=3, collate_fn=collate_batch)
loss = None
for epoch in range(3):
    for batch in dl:
        ids = batch["ids"].to(dev)
        pad = batch["pad_mask"].to(dev)
        x0 = fixed_length_noise_like(ids)
        blank, tok = model(x0, pad)
        loss, b, t = edit_flow_loss(blank, tok, ids, edit_mask=(x0 != ids), pad_mask=pad)
        opt.zero_grad()
        loss.backward()
        opt.step()
    assert loss is not None
    print(f"epoch {epoch} loss {loss.item():.4f}", flush=True)
print("SMOKE_OK")
