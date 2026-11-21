import json
import sys

r = json.load(open(sys.argv[1]))
print("status:", r["status"])
print("conclusion:", r["scientific_conclusion"])
print("decision_code:", r["decision_code"])
print("gate_pass:", r["consistency_gate"]["pass"])
print("fits new/reused/eval:", r["new_model_fits"], r["reused_model_fits"], r["evaluated_model_fits"])
print("\n== PRIMARY TESTS ==")
for t in r["primary_tests"]:
    name = t["test"]
    eff = t["observed_effect"]
    lo, hi = t["ci95"]
    ph = t["p_holm"]
    ps = t["positive_seeds"]
    print(f"{name:55s} eff={eff:+.4f} CI=[{lo:+.4f},{hi:+.4f}] pHolm={ph:.4g} seeds={ps}/10 pass={t['pass']}")
print("\n== GATE TESTS ==")
for t in r["gate_tests"]:
    print(f"{t['test']:55s} eff={t['observed_effect']:+.4f} pass={t['pass']}")
print("\n== SECONDARY (descriptive) ==")
for t in r["secondary_tests"]:
    name = t["test"]
    eff = t["observed_effect"]
    lo, hi = t["ci95"]
    print(f"{name:55s} eff={eff:+.4f} CI=[{lo:+.4f},{hi:+.4f}] pHolm={t['p_holm']:.4g} seeds={t['positive_seeds']}/10 pass={t['pass']}")
print("\n== ABS PERF (primary seed) ==")
for m, arms in r["primary_absolute_performance"].items():
    for a, v in arms.items():
        print(f"{m:7s} {a:18s} rho={v['spearman']:.4f} mse={v['mse']:.4f}")