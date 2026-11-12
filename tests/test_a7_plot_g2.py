import json

from scripts.a7_g2_gate import evaluate_g2
from scripts.a7_plot_g2 import generate_figure
from tests.test_a7_g2_gate import make_arm


def test_g2_figure_rebuilds_from_frozen_gate_and_raw_inputs(tmp_path):
    full = make_arm(tmp_path)
    edit = make_arm(tmp_path)
    edit["name"] = "EDIT"
    gate = evaluate_g2([full, edit], {f"g{i}" for i in range(18)})
    gate_path = tmp_path / "g2_gate.json"
    gate_path.write_text(json.dumps(gate))
    manifest_path = generate_figure(gate_path, tmp_path / "g2_figure")
    manifest = json.loads(manifest_path.read_text())
    assert manifest["gate_passed"] is True
    assert len(manifest["outputs"]) == 3
    assert (tmp_path / "g2_figure.png").read_bytes().startswith(b"\x89PNG")
    assert (tmp_path / "g2_figure.pdf").read_bytes().startswith(b"%PDF")
    rows = (tmp_path / "g2_figure.csv").read_text().splitlines()
    assert len(rows) == 36 + 1
    assert rows[0].startswith("arm,gene,learned_auc,strongest_simple_method")
