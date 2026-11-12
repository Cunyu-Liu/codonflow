"""Persist the official GEMORNA model across sequential model.gen calls."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import pickle
import platform

import torch

if platform.system() == "Darwin":
    from shared.libg2m import *
elif platform.system() == "Linux":
    from shared.mod_xzr01 import *
else:
    raise RuntimeError("Unsupported OS")
from config import *
from models.gemorna_cds import *
from models.gemorna_utr import *


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt_path", required=True)
    parser.add_argument("--protein_seq", required=True)
    parser.add_argument("--n", type=int, required=True)
    args = parser.parse_args()
    if args.n < 1:
        raise ValueError("n must be positive")
    if any(residue not in set("ACDEFGHIKLMNPQRSTVWY*") for residue in args.protein_seq.upper()):
        raise ValueError("non-canonical protein sequence")
    device = torch.device("cuda")
    if not torch.cuda.is_available():
        raise RuntimeError("GEMORNA requires CUDA; CPU fallback forbidden")
    with open("./vocab/prot_vocab.pkl", "rb") as handle:
        prot_vocab = pickle.load(handle)
    with open("./vocab/cds_vocab.pkl", "rb") as handle:
        cds_vocab = pickle.load(handle)
    model_config = GEMORNA_CDS_Config()
    enc = Encoder(
        input_dim=model_config.input_dim, hid_dim=model_config.hidden_dim,
        n_layers=model_config.num_layers, n_heads=model_config.num_heads,
        pf_dim=model_config.ff_dim, dropout=model_config.dropout,
        cnn_kernel_size=model_config.cnn_kernel_size,
        cnn_padding=model_config.cnn_padding, device=device,
    )
    dec = Decoder(
        output_dim=model_config.output_dim, hid_dim=model_config.hidden_dim,
        n_layers=model_config.num_layers, n_heads=model_config.num_heads,
        pf_dim=model_config.ff_dim, dropout=model_config.dropout, device=device,
    )
    model = CDS(enc, dec, model_config.prot_pad_idx, model_config.cds_pad_idx, device)
    model.load_state_dict(torch.load(args.ckpt_path, map_location=device))
    model.to(device).eval()
    for _ in range(args.n):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            model.gen(args.protein_seq, prot_vocab, cds_vocab, device)
        lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("official model.gen returned no sequence")
        body = lines[-1].split()
        print(json.dumps({"sequence": body[0],
                          "naturalness": float(body[1]) if len(body) > 1 else None}), flush=True)


if __name__ == "__main__":
    main()
