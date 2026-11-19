import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser()
parser.add_argument("--work-dir", default=str(Path(__file__).resolve().parent))
args = parser.parse_args()
ROOT = Path(args.work_dir).resolve()
production = json.loads((ROOT / "evidence/production.json").read_text())
independent = json.loads((ROOT / "evidence/independent.json").read_text())
finalization = json.loads((ROOT / "evidence/finalization.json").read_text())
paper = json.loads((ROOT / "evidence/paper-verification.json").read_text())
text = " ".join(t.strip() for t in ET.parse(ROOT / "candidate-v1.xml").getroot().itertext() if t.strip())
checks = []

def check(name, condition, detail):
    checks.append({"name": name, "pass": bool(condition), "detail": detail})

for model, token in (("simple", "+0.413234"), ("simple_plus_structure", "+0.408983")):
    m = production["model_metrics"][model]
    check(f"{model}_spearman", f"{m['spearman']:+.6f}" == token and token in text, token)
    rmse = f"RMSE {m['rmse']:.6f}"
    mse = f"MSE {m['mse']:.6f}"
    check(f"{model}_rmse_mse", rmse in text and mse in text, f"{rmse}; {mse}")

for endpoint, estimate, ci in (
    ("delta_spearman", "−0.004251", "[−0.055205, +0.046336]"),
    ("delta_mse", "−0.005429", "[−0.089604, +0.076766]"),
):
    effect = production["primary_effects"][endpoint]
    expected_estimate = f"{effect['observed']:+.6f}".replace("-", "−")
    expected_ci = "[" + ", ".join(f"{x:+.6f}" for x in effect["ci95_percentile"]) + "]"
    expected_ci = expected_ci.replace("-", "−")
    check(f"{endpoint}_estimate", estimate == expected_estimate and estimate in text, estimate)
    check(f"{endpoint}_ci", ci == expected_ci and ci in text, ci)
    check(f"{endpoint}_holm", effect["holm_p"] == 1.0 and not effect["direction_pass"], "Holm p=1.0; direction_pass=false")
    check(f"{endpoint}_resamples", effect["bootstrap_resamples"] == 20000 and effect["permutation_resamples"] == 20000, "20,000 + 20,000")

check("independent_status", independent["status"] == "PASS" and independent["checks_passed"] == independent["checks_total"] == 12, "12/12 PASS")
check("finalization_status", finalization["status"] == "PASS_RK02_MORDSTEIN_STRUCTURE_INCREMENT_DEV" and finalization["checks_passed"] == finalization["checks_total"] == 21, "21/21 PASS")
check("paper_status", paper["status"] == "PASS_RK02_STRUCTURE_PAPER_UPDATE" and paper["checks_passed"] == paper["checks_total"] == 38, "38/38 PASS")
check("scientific_no_go", finalization["scientific_result"] == "FIXED_GFP_OBSERVED_R1_STRUCTURE_INCREMENT_NO_GO_DEVELOPMENT_ONLY" and not finalization["structure_increment_pass"] and "NO-GO" in text, "development no-go")
check("no_overclaim", all(x in text for x in ("development", "非完整 CDS", "非蛋白 OOD", "非普遍结构证伪")), "scope and limitations present")
feature_max = max(independent["feature_max_abs_delta"].values())
prediction_max = max(independent["prediction_max_abs_delta"].values())
check("independent_feature_delta", f"{feature_max:.2e}" == "2.78e-16" and "2.78e-16" in text, feature_max)
check("independent_prediction_delta", f"{prediction_max:.2e}" == "1.07e-14" and "1.07e-14" in text, prediction_max)

report = {
    "schema": "a8.rk02.structure_ppt_candidate_fact_check.v1",
    "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
    "checks_passed": sum(c["pass"] for c in checks),
    "checks_total": len(checks),
    "candidate_sha256": hashlib.sha256((ROOT / "candidate-v1.xml").read_bytes()).hexdigest(),
    "production_sha256": hashlib.sha256((ROOT / "evidence/production.json").read_bytes()).hexdigest(),
    "independent_sha256": hashlib.sha256((ROOT / "evidence/independent.json").read_bytes()).hexdigest(),
    "finalization_sha256": hashlib.sha256((ROOT / "evidence/finalization.json").read_bytes()).hexdigest(),
    "paper_verification_sha256": hashlib.sha256((ROOT / "evidence/paper-verification.json").read_bytes()).hexdigest(),
    "checks": checks,
}
(ROOT / "candidate-fact-check.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
print(json.dumps({k: report[k] for k in ("status", "checks_passed", "checks_total", "candidate_sha256")}, indent=2))
if report["status"] != "PASS":
    raise SystemExit(1)
