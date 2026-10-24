"""Patch run_exp5_ood.py / run_exp3.py to auto-infer model arch from checkpoint.

The 355M checkpoint is d_model=1280, n_layers=12, n_heads=16; the 56M is
768/8/12. Scripts previously hardcoded the 56M arch, so loading converged.pt
of 355M failed with size mismatch. Inference is done from actual tensor
shapes so both checkpoints load unchanged.
"""
import re

OLD5 = (
    '    model = EditFlowTransformer(EditFlowConfig(d_model=768, n_layers=8, n_heads=12, dropout=0.0))\n'
    '    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)\n'
    '    model.load_state_dict(state)'
)
NEW5 = (
    '    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)\n'
    '    _k = [k for k in state if k.endswith("self_attn.in_proj_weight")][0]\n'
    '    _d = state[_k].shape[0] // 3\n'
    '    _n_layers = max(int(k.split(".")[2]) for k in state\n'
    '                    if re.match(r"encoder.layers.\\d+.self_attn.in_proj_weight", k)) + 1\n'
    '    _n_heads = {768: 12, 1280: 16}.get(_d, 12)\n'
    '    print(f"[arch] d_model={_d} n_layers={_n_layers} n_heads={_n_heads} from {args.checkpoint}", flush=True)\n'
    '    model = EditFlowTransformer(EditFlowConfig(d_model=_d, n_layers=_n_layers, n_heads=_n_heads, dropout=0.0))\n'
    '    model.load_state_dict(state)'
)

OLD3 = (
    '    model = EditFlowTransformer(\n'
    '        EditFlowConfig(d_model=768, n_layers=8, n_heads=12, dropout=0.0)\n'
    '    )\n'
    '    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)\n'
    '    model.load_state_dict(state)'
)
NEW3 = (
    '    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)\n'
    '    _k = [k for k in state if k.endswith("self_attn.in_proj_weight")][0]\n'
    '    _d = state[_k].shape[0] // 3\n'
    '    _n_layers = max(int(k.split(".")[2]) for k in state\n'
    '                    if re.match(r"encoder.layers.\\d+.self_attn.in_proj_weight", k)) + 1\n'
    '    _n_heads = {768: 12, 1280: 16}.get(_d, 12)\n'
    '    print(f"[arch] d_model={_d} n_layers={_n_layers} n_heads={_n_heads} from {args.checkpoint}", flush=True)\n'
    '    model = EditFlowTransformer(\n'
    '        EditFlowConfig(d_model=_d, n_layers=_n_layers, n_heads=_n_heads, dropout=0.0)\n'
    '    )\n'
    '    model.load_state_dict(state)'
)


def patch(path, old, new):
    src = open(path).read()
    if new in src:
        print(f"{path}: already patched")
        return
    assert old in src, f"pattern not found in {path}"
    open(path, "w").write(src.replace(old, new))
    print(f"patched {path}")


for p in ("/home/codonflow/scripts/run_exp5_ood.py",):
    patch(p, OLD5, NEW5)
for p in ("/home/codonflow/scripts/run_exp3.py",):
    patch(p, OLD3, NEW3)

# exp3 lacks re import? check
src3 = open("/home/codonflow/scripts/run_exp3.py").read()
if "import re" not in src3.split("def ")[0]:
    src3 = src3.replace("import argparse", "import argparse\nimport re", 1)
    open("/home/codonflow/scripts/run_exp3.py", "w").write(src3)
    print("added 'import re' to run_exp3.py")
src5 = open("/home/codonflow/scripts/run_exp5_ood.py").read()
assert "import re" in src5.split("def ")[0], "run_exp5_ood.py needs re import"
print("done")
