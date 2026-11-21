import json
import pandas as pd
import numpy as np

root = "/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk35/coverage_transport_v1/model_results_v1/"
pm = pd.read_csv(root + "seed_metrics.csv")
tl = pd.read_csv(root + "training_log.csv")
print("prod seed_metrics rows:", len(pm))
print("prod arms:", list(pm["arm"].unique()))
print("prod seeds:", list(pm["seed"].unique()))
print("dup keys:", pm.duplicated(subset=["seed", "arm"]).sum())
print("training_log rows:", len(tl), "new_sum:", int(tl["new_model_fits"].sum()), "reused_sum:", int(tl["reused_model_fits"].sum()))
print("training_log cols:", list(tl.columns))
# reconstruct ind_metrics arm set as verifier does
oof = pd.read_csv(root + "oof_predictions.csv")
value_cols = [c for c in oof.columns if c == "null" or c.startswith("ridge_") or c.startswith("histgb_")]
print("oof value_cols:", value_cols)
print("expected ind_metrics rows:", len(value_cols) * 10)