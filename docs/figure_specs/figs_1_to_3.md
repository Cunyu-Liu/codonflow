# Figure specs (frozen BEFORE numbers, per spec 3.2.6 discipline)

## Fig-1 (EXP-1) Baseline preference collapse

- Type: 1×2 panel bar chart (eGFP | nanoLuc), shared style.
- Bars: pairwise NED mean (3 arms: uniform / RSCU-weighted / CAI-greedy),
  colors #3b7dd8 / #d86f3b / #888888, error = 3-seed std (thin black caps).
- Overlaid line (twin axis, green circles dashed): codon entropy (bits).
- Title per panel: gene name + KS p-value (uniform vs RSCU-weighted).
- Bottom annotation: codonGPT mean log-lik for uniform vs RSCU-weighted
  (the AR model prefers the collapsed direction).
- Caption claim: constrained AR preference shrinks synonymous diversity.

## Fig-2 (EXP-2) Gated vs same-budget post-filter

- Type: 1×2 panel grouped bar chart per family.
- Groups (x): gated_guided / uniform+filter(topK) / uniform+filter(all).
- Bars: hypervolume (3-D: CAI, -MFE, -|GC-0.55|), ref point
  (0.5, 100, -0.2); error = 3-seed std.
- Overlaid markers (right axis): feasible rate (diamonds), time-to-first-
  usable (inverted triangles, normalized 0-1).
- Annotation: Wilcoxon p-value gated vs filter topK (paired, n=6).
- Caption claim: under equal scoring budget the gated terminal
  distribution converts budget into feasible quality faster.

## Fig-3 (EXP-3) Preference scan

- Type: 2 scatter panels (CAI vs -MFE; CAI vs -|GC-0.55|).
- 7 direction clusters (colored, marker per direction; corner directions
  annotated at edges).
- Reference front: non-dominated union of all methods (black step line).
- Per-cluster non-dominated share in legend.
- Caption claim: Doob-h preference shaping spans the Pareto front.

Frozen 2026-10-05 (A2 state: ATC v2 normalization, hypervolume
maximization convention). Any change = amendment.
