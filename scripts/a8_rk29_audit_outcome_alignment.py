#!/usr/bin/env python3
"""Post-freeze RK29 alignment gate. No model fitting or target analysis."""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import math
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import a8_rk29_label_free_coverage as cov


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--coverage-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol-freeze-commit", required=True)
    parser.add_argument("--authorize-alignment-outcome-read", action="store_true")
    args = parser.parse_args()
    assert args.authorize_alignment_outcome_read
    start = time.perf_counter()
    protocol = json.loads(args.protocol.read_text())
    coverage = json.loads(args.coverage_report.read_text())
    assert coverage["protocol_sha256"] == cov.sha256(args.protocol)
    assert coverage["status"] == "PASS_LABEL_FREE_COVERAGE_AUDIT_FEASIBLE"
    for spec in protocol["inputs"].values():
        assert cov.sha256(spec["path"]) == spec["sha256"]
    time_map = protocol["outcome_access"]["geo_to_outcome_timepoint_map"]
    outcome_columns = ["Protein_id", "Group"] + list(time_map.values()) + ["Decay_rate", "Predicted_mRNA_stability"]
    _, _, outcome_records = cov.read_xlsx_selected(protocol["inputs"]["outcome_xlsx"]["path"], outcome_columns)
    outcome = pd.DataFrame(outcome_records)
    geo = pd.read_csv(protocol["inputs"]["geo_perfect_csv_gz"]["path"])
    fasta = cov.read_fasta_gz(protocol["inputs"]["reference_fasta_gz"]["path"])
    geo_names = sorted(set(geo["Name"].astype(str)))
    assert len(outcome) == len(geo_names) == 955
    canonical = {name: cov.canonical_metadata(name) for name in geo_names}
    names_by_protein = collections.defaultdict(list)
    for name in geo_names:
        names_by_protein[canonical[name][0]].append(name)
    outcome_groups = outcome.groupby("Protein_id", sort=True).indices
    assert set(outcome_groups) == set(names_by_protein)

    candidate_sizes = []
    design_group_factorials = []
    cartesian_proteins = []
    total_pair_checks = 0
    for protein, row_indices in sorted(outcome_groups.items()):
        names = sorted(names_by_protein[protein])
        n = len(row_indices)
        assert len(names) == n
        protein_geo = geo[geo["Name"].isin(names)]
        assert len(protein_geo) == n * n
        assert protein_geo.groupby("Name").size().eq(n).all()
        for row_index in row_indices:
            row = outcome.iloc[int(row_index)]
            for name in names:
                assert canonical[name][0] == protein
                name_geo = protein_geo[protein_geo["Name"] == name]
                mask = np.ones(len(name_geo), dtype=bool)
                for geo_column, outcome_column in time_map.items():
                    mask &= np.isclose(name_geo[geo_column].to_numpy(float), float(row[outcome_column]), atol=1e-12, rtol=0.0)
                # Auxiliary metadata identifies the measurement row, not the sequence Name.
                mask &= (name_geo["Protein_id"].to_numpy(str) == row["Protein_id"])
                mask &= (name_geo["Group"].to_numpy(str) == row["Group"])
                assert int(mask.sum()) == 1, (protein, row_index, name, int(mask.sum()))
                total_pair_checks += 1
        cartesian_proteins.append({"Protein_id": protein, "n_names": n, "n_measurements": n, "n_geo_rows": len(protein_geo)})
        for group in sorted(set(outcome.iloc[row_indices]["Group"])):
            group_rows = [i for i in row_indices if outcome.iloc[int(i)]["Group"] == group]
            group_names = [name for name in names if canonical[name] == (protein, group)]
            k = len(group_rows)
            assert len(group_names) == k
            # Every name matches every measurement in this protein/design group.
            candidate_sizes.extend([k] * k)
            design_group_factorials.append(math.factorial(k))

    n_valid_assignments = math.prod(design_group_factorials)
    n_ambiguous_rows = sum(size > 1 for size in candidate_sizes)
    n_ambiguous_groups = sum(value > 1 for value in design_group_factorials)
    assert n_ambiguous_rows > 0 and n_ambiguous_groups > 0 and n_valid_assignments > 1
    example_names = ["c1-p10-rA-r1", "c1-p10-rB-r1"]
    example_sequences = [fasta[name] for name in example_names]
    report = {
        "schema": "a8-rk29-outcome-alignment-gate-v1",
        "status": "NOT_DISCRIMINATING_SOURCE_ALIGNMENT_OR_COVERAGE_FAILED",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": str(args.protocol), "protocol_sha256": cov.sha256(args.protocol),
        "protocol_freeze_commit": args.protocol_freeze_commit,
        "coverage_report_sha256": cov.sha256(args.coverage_report),
        "audit_script_sha256": cov.sha256(Path(__file__).resolve()),
        "inputs": {key: {"path": spec["path"], "sha256": spec["sha256"]} for key, spec in protocol["inputs"].items()},
        "n_s6_measurements": len(outcome), "n_unique_fasta_names": len(geo_names), "n_geo_rows": len(geo),
        "geo_is_within_protein_name_by_measurement_cartesian_product": True,
        "cartesian_pair_checks_passed": total_pair_checks,
        "cartesian_proteins": cartesian_proteins,
        "candidate_size_distribution": dict(sorted(collections.Counter(candidate_sizes).items())),
        "n_rows_with_unique_name_candidate": sum(size == 1 for size in candidate_sizes),
        "n_rows_with_ambiguous_name_candidates": n_ambiguous_rows,
        "n_protein_design_groups": len(design_group_factorials),
        "n_protein_design_groups_with_unique_assignment": len(design_group_factorials) - n_ambiguous_groups,
        "n_protein_design_groups_with_multiple_assignments": n_ambiguous_groups,
        "n_valid_global_sequence_outcome_assignments": str(n_valid_assignments),
        "log10_n_valid_global_assignments": math.log10(n_valid_assignments),
        "unique_sequence_outcome_assignment": False,
        "representative_ambiguity": {
            "Protein_id": "c1_p10", "Group": "iCodon_1", "names": example_names,
            "sequences_identical": example_sequences[0] == example_sequences[1],
            "full_sequence_hamming_distance": sum(a != b for a, b in zip(*example_sequences)),
            "full_sequence_sha256": [hashlib.sha256(seq.encode()).hexdigest() for seq in example_sequences],
            "both_names_match_both_s6_measurement_vectors": True,
        },
        "stop_reason": "The GEO perfect table contains every within-protein FASTA-name by measurement-vector pairing. The nine values identify a measurement but cannot identify its sequence; multiple distinct full-sequence assignments satisfy the frozen join.",
        "forbidden_fallbacks_not_used": ["row-order join", "nearest-value join", "arbitrary first match", "target-informed sequence selection", "post-hoc join-rule revision"],
        "model_fit_performed": False, "analysis_rows_generated": 0, "scientific_result_generated": False,
        "functional_untouched_read": False, "expensive_generative_training_performed": False,
        "elapsed_seconds": float(time.perf_counter() - start),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    cov.write_json(args.output, report)
    concise = {key: value for key, value in report.items() if key not in {"cartesian_proteins", "inputs"}}
    print(json.dumps(concise, indent=2))


if __name__ == "__main__":
    main()
