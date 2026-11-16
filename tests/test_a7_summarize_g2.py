import csv
import json

from scripts.a7_g2_gate import evaluate_g2
from scripts.a7_summarize_g2 import dominated_fraction, generate_summary, pareto_indices
from tests.test_a7_g2_gate import make_arm


def test_pareto_and_coverage_use_maximization_with_strict_dominance():
    points = [{"objectives": values} for values in ([2, 0], [0, 2], [1, 1], [0, 0])]
    assert pareto_indices(points) == [0, 1, 2]
    assert dominated_fraction(points[:3], [points[3]]) == 1.0
    assert dominated_fraction([points[3]], points[:3]) == 0.0


def test_g2_secondary_summary_rebuilds_raw_fronts_best_and_costs(tmp_path):
    full = make_arm(tmp_path, n_genes=1)
    edit = make_arm(tmp_path, n_genes=1)
    edit["name"] = "EDIT"
    for path in full["paths"]:
        payload = json.loads(open(path).read())
        payload["costs"]["generator_calls"] = 500
        open(path, "w").write(json.dumps(payload))
    gate = evaluate_g2([full, edit], {"g0"}, min_genes=1)
    gate_path = tmp_path / "g2_gate.json"
    gate_path.write_text(json.dumps(gate))
    manifest_path = generate_summary(gate_path, tmp_path / "analysis" / "g2")
    manifest = json.loads(manifest_path.read_text())
    assert manifest["gate_passed"] == gate["passed"]
    assert manifest["n_runs_including_shared_baselines_per_arm"] == 30
    assert len(manifest["outputs"]) == 4
    raw = json.loads((tmp_path / "analysis" / "g2.secondary.json").read_text())
    assert len(raw["runs"]) == 30
    assert set(raw["runs"][0]["budgets"]) == {"50", "100", "500"}
    assert len(raw["runs"][0]["budgets"]["500"]["best_by_objective"]) == 4
    assert len((tmp_path / "analysis" / "g2.comparison.csv").read_text().splitlines()) == 7
    assert len((tmp_path / "analysis" / "g2.best_at_budget.csv").read_text().splitlines()) == 361
    with (tmp_path / "analysis" / "g2.costs.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 30
    assert rows[0]["generator_calls"] == "500"
