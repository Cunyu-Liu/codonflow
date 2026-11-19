# RiboMIMO Mohammad16 → Subtelny14 training record

- Status: `PASS_COMPLETE`; scientific result: `RIBOMIMO_STUDY_OOD_NO_UNIFORM_SIGNIFICANT_ADVANTAGE_OVER_RIDGE`.
- Official architecture/loss/optimizer and source-validation global-R2 checkpoint selection retained.
- Target evaluation occurred only after source training, early stopping and source-only ridge selection.
- Wall times are observed on a shared GPU and are not time-matched cost evidence.

| Seed | Split seed | Train/valid/target | Best/last epoch | Best source val. R2 | Ridge alpha | Train s | Ridge s | Target eval s | Independent best/last | Independent train s |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1234 | 815 | 1062/117/3921 | 10/15 | 0.485331353 | 100 | 226.044 | 6.708 | 31.468 | 10/15 | 224.865 |
| 2345 | 80 | 1062/117/3921 | 10/15 | 0.485328818 | 100 | 215.123 | 6.967 | 22.993 | 10/15 | 226.375 |
| 3456 | 667 | 1062/117/3921 | 13/18 | 0.493297366 | 100 | 282.649 | 6.761 | 29.279 | 13/18 | 282.349 |

## Evidence files

- Production: `audits/20261119/RK05/ribomimo_study_ood_production_v1.json` (SHA256 `0b78fe4cb06294a572928adab63e5f840f13f308274d7a8dbfd0efdb5f85d239`)
- Independent verification: `audits/20261119/RK05/ribomimo_study_ood_independent_v1.json` (SHA256 `5cbfcaa35828042a0cb1abda20c7e60e6d6094ad8a0d3407c3f114fd621869e1`)
- Finalization: `audits/20261119/RK05/ribomimo_study_ood_finalization_v1.json` (SHA256 `1f247fb05c08ff4499be50a6ab5b551d1b76db154cf9f9f882b72af4a9016d0e`)

Full per-epoch source-validation histories, official logs, checkpoints and target prediction hashes are retained in the production and independent reports.
