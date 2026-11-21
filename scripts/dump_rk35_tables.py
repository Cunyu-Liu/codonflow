import json
import hashlib
import pandas as pd

AUD = "audits/20261122/RK35/"
ROOT = "/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk35/coverage_transport_v1/model_results_v1/"
r = json.load(open(AUD + "rk35_coverage_transport_result_v1.json"))
sm = pd.read_csv(ROOT + "seed_metrics.csv")
sm["arm"] = sm["arm"].fillna("null")
ps = r["primary_seed"]

LABEL = {
    "trunc_vs_simple": "trunc−simple",
    "exact_vs_trunc": "exact−trunc",
}
MODEL = {"ridge": "Ridge", "histgb": "HistGB"}
METRIC = {"spearman_effect": "Spearman", "mse_improvement": "MSE improvement"}

print("=== PRIMARY TABLE ROWS ===")
for t in r["primary_tests"]:
    m, c, met = t["test"].split("__")
    eff = t["observed_effect"]
    lo, hi = t["ci95"]
    raw = t["p_cluster_swap"]
    holm = t["p_holm"]
    seeds = t["positive_seeds"]
    pas = "Yes" if t["pass"] else "No"
    print(f"| {LABEL[c]} | {MODEL[m]} | {METRIC[met]} | {eff:.6f} | [{lo:.6f}, {hi:.6f}] | {raw:.6f} | {holm:.6f} | {seeds}/10 | {pas} |")

print("\n=== GATE VALUES ===")
for t in r["gate_tests"]:
    print(t["test"], f"eff={t['observed_effect']:.6f}", f"CI=[{t['ci95'][0]:.6f},{t['ci95'][1]:.6f}]", f"raw={t['p_cluster_swap']:.6f}", f"holm={t['p_holm']:.6f}", "pass=", t["pass"])

print("\n=== ABS PERF TABLE ROWS (primary seed) ===")
cur = sm[sm["seed"] == ps].set_index("arm")
order = ["null", "simple", "exact_local", "cds_start_local", "trunc_local", "trunc_local_d0"]
ARMLABEL = {"null": "null", "simple": "simple", "exact_local": "exact local d2", "cds_start_local": "CDS-start d2", "trunc_local": "trunc CDS4-45 d2", "trunc_local_d0": "trunc CDS4-45 d0"}
for m in ("ridge", "histgb"):
    for a in order:
        key = "null" if a == "null" else f"{m}_{a}"
        row = cur.loc[key]
        ml = "Intercept" if a == "null" else MODEL[m]
        print(f"| {ml} | {ARMLABEL[a]} | {row['spearman']:.6f} | {row['mse']:.6f} |")

print("\n=== SECONDARY DESCRIPTIVE ===")
for t in r["secondary_tests"]:
    print(t["test"], f"eff={t['observed_effect']:.6f}", f"CI=[{t['ci95'][0]:.6f},{t['ci95'][1]:.6f}]", f"holm={t['p_holm']:.6f}", f"seeds={t['positive_seeds']}/10", "pass=", t["pass"])

print("\n=== SHAS ===")
for label, fn in [("protocol", "configs/a8_rk35_coverage_transport_protocol_v1.json"),
                  ("result", AUD + "rk35_coverage_transport_result_v1.json"),
                  ("independent_v2", AUD + "rk35_coverage_transport_independent_v2.json"),
                  ("reproduction_comparison_v2", AUD + "rk35_reproduction_comparison_v2.json"),
                  ("closeout", AUD + "rk35_closeout_v1.json"),
                  ("preflight", AUD + "rk35_preflight_v1.json")]:
    print(label, hashlib.sha256(open(fn, "rb").read()).hexdigest())

print("\n=== WALL ===")
print("production_wall", r["component_wall_seconds"])
ind = json.load(open(AUD + "rk35_coverage_transport_independent_v2.json"))
print("independent_wall", ind["component_wall_seconds"], "checks", ind["checks_passed"], "/", ind["checks_total"])
print("max_pred", ind["max_prediction_abs_delta"], "max_inference", ind["max_inference_abs_delta"], "gate", ind["consistency_gate_max_delta"])