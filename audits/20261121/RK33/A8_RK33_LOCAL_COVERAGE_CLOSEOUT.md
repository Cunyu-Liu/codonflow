# A8 / RK33 — Local observed-R1 coverage closeout

**Status: SCIENTIFIC AND REPRODUCTION CLOSEOUT PASS.** The result remains retrospective and is not independent confirmation.

## Frozen question and execution

Under the same 152 Mordstein HEK293 observed-R1 variants, 74 whole-sequence clusters, ten seeds, five folds, simple sequence backbone, Ridge/HistGB models, and inference protocol, RK33 tested whether a 42-nt CDS4–45 local MFE improves over no structure, a single full-300 MFE, and the RK28 full-300/window48 three-feature arm.

The protocol was frozen before outcomes were fitted. The label-free preflight passed 21/21 checks; both synthetic suites passed 18/18. The first production attempt stopped before fitting because target CSV round-trip comparison used zero-tolerance equality. Only that identity check was changed to a 1e-12 absolute tolerance; the scientific design did not change, and the failure log is retained.

| Item | Verified value |
|---|---:|
| New model fits | 200 |
| Reused accepted RK28 fits | 200 |
| Total evaluated fits | 400 |
| Primary endpoints | 12 |
| Production / independent time | 154.170620 / 213.348891 s |

## Scientific decision

**LOCAL42_OBSERVED_R1_STRUCTURE_INCREMENT_NOT_SUPPORTED — 0/12 endpoints passed.** All 12 whole-cluster 95% confidence intervals cross zero and all unified Holm-adjusted p-values are 1.0. The smallest unadjusted permutation p-value is 0.16799160041997901, so the failure is not merely an edge created by multiplicity correction. Positive seed counts in some local42–full3 comparisons do not override failed observed-effect, interval, or multiplicity gates.

## Independent verification and clean reproduction

The independent raw-source/model/statistics implementation passed 76/76 checks and reproduced the same three-family gate. A separate no-hardlinks checkout of `20e1ac389313fc21c36e82a5745be3d89bf0dffa` repeated production and independent verification. The comparison passed 90/90 checks; 12/12 CSV files were byte-identical and 52/52 NPZ arrays were exactly equal.

| Component | Original | Clean checkout |
|---|---:|---:|
| Production | 154.170620 s | 158.617696 s |
| Independent verification | 213.348891 s | 190.443288 s |

Full project tests: **429 passed, 1 skipped** (20.16 s).

## Evidence hashes

| Evidence | SHA256 |
|---|---|
| protocol | `d5a3282f0d03a384b3d77c3d30d2a98b315c0624d16e6d97563d09cee60a96fe` |
| preflight | `ff3b3159230fc8650a8f1b873c4c2d412ee42a5fc5c0bbce53240c2fccac706d` |
| result | `d341694fb336ba579bbb990d80d7b17eafff104250052cea8577e4b927c08b64` |
| independent | `3b53c5118bc93a71a5eaadaaaf22e48f13bc0b2d580b017308348a0ff171fa8d` |
| reproduction | `7808acc84567fe972be0ddb870c23bd8714da2bc1e0dbdb1421ff08a5171e455` |
| project_tests | `06863b85f1efec936bdff6af62a62899b3434588d90aa0ab4d7cf2972ebcd12f` |
| failed_console | `2efeb37fe85848b06d275057ff2ce58398631184befe4209bccca4e8d1242a18` |
| production_console | `102d74fd64fdd47740dd17833436a349d31706ed83ba92901a515507dc9fe7b6` |
| closeout verification | `ae09d302c8dd331aa59239c6e90180289e3c7ab34a030d3510e26b6af55c334b` |

## Non-claims and remaining tasks

This experiment does not reconstruct the exact start-aware Kudla window: the observed FASTA begins at CDS position 4 and lacks the start ATG, four upstream nucleotides, complete UTR–CDS context, and measured structure. It does not identify host, assay, measured-versus-predicted structure, or dangling-end effects. It provides no external-SOTA, unified time-matched, complete seven-method dense-trajectory, multispecies VeloHARMO, functional/protein-OOD, prospective DBTL, or RK-G1 result. Functional untouched data were not read; expensive generator training was not authorized; no wet-lab work was performed.

The full manuscript remains a non-submittable working draft until those gates are complete.
