### 6.52 Internal basin selection improves simple search but does not close the common-input actual-set gap

RK41 tested whether initialization-basin selection could improve search without importing comparator sequences. For each of 18 development records and three seeds, eight distinct protein-only synonymous initializations were generated and scored. The first-member arm retained pool index zero, whereas the best-member arm selected the initialization with the highest search utility; both then continued hill-climbing within a shared evaluation cache to exactly 11 unique-scorer outputs. Thus, eight pool evaluations and only three subsequent unique local-search points were used, and the comparison did not silently add budget. Raw arms disabled native calibration during initialization and search, while calibrated arms were retained as scale-interaction diagnostics. No new arm used LinearDesign, EnsembleDesign, native synonymous DNA, or another external sequence. The experiment added 216 runs and 2,376 unique-scorer calls to 108 accepted RK40 runs.

Table 36 reports the three frozen primary families. Selecting the best raw initialization rather than the first improved trajectory-maximum utility by 0.050030 and single-point normalized hypervolume by 0.031529. The best-initialization arm also exceeded the original raw sequential search by 0.788952 for utility and 0.486789 for single-point hypervolume. Both internal families passed: all confidence limits were positive, all Holm-adjusted sign-flip tests were significant, and every seed-averaged effect was positive. These results support an initialization-basin contribution within the frozen proxy-search contract.

**Table 36**

*Frozen RK41 Primary Inference*

| Primary family | Endpoint | Effect | 95% CI | Holm-adjusted *p* | Seed direction |
|:---|:---|---:|:---:|---:|:---:|
| Best vs first raw initialization | Best normalized weighted utility | 0.050030 | [0.035533, 0.064341] | 0.000099995 | 3/3 positive |
| Best vs first raw initialization | Best single-point normalized HV | 0.031529 | [0.015111, 0.052030] | 0.000849958 | 3/3 positive |
| Best initialization vs raw sequential | Best normalized weighted utility | 0.788952 | [0.621305, 0.952120] | 0.000099995 | 3/3 positive |
| Best initialization vs raw sequential | Best single-point normalized HV | 0.486789 | [0.330474, 0.658647] | 0.000099995 | 3/3 positive |
| Best raw initialization vs LinearDesign-11 | First-*k* actual-set HV | -29.215520 | [-41.230472, -18.981136] | 0.000099995 | 0/3 positive |
| Best raw initialization vs LinearDesign-11 | First-*k* pairwise NED | 0.165764 | [0.149476, 0.182711] | 0.000099995 | 3/3 positive |

*Note.* Effects are left method minus right method after averaging three seeds within each record. Inference used 20,000 paired bootstrap replicates and 20,000 sign-flip replicates across 18 records, with Holm correction over the two endpoints in each family. HV = hypervolume; NED = normalized edit distance; *k* is LinearDesign-11's record-specific observed output count.

The external comparison did not pass. Best raw initialization remained significantly worse than LinearDesign-11 on first-*k* actual-set hypervolume, with a negative effect for every seed. Pairwise NED instead increased significantly, indicating greater within-archive sequence diversity, but the frozen family required both endpoints and diversity cannot compensate for the hypervolume failure. Table 37 shows that the best raw pool arm improved absolute internal endpoints and actual-set hypervolume relative to raw sequential search while remaining far below LinearDesign-11 on actual-set hypervolume. Calibrated arms are descriptive scale diagnostics, not common-input designs.

**Table 37**

*Mean Absolute RK41 Search and Actual-Set Performance*

| Method | Best utility | Best single-point HV | First-*k* HV | First-*k* NED |
|:---|---:|---:|---:|---:|
| Raw sequential, budget 11 | 2.457592 | 0.287328 | 0.258270 | 0.004692 |
| Raw pool first, budget 11 | 3.196515 | 0.742588 | 0.751843 | 0.237085 |
| Raw pool best, budget 11 | 3.246544 | 0.774117 | 0.757367 | 0.237053 |
| Calibrated pool first, budget 11 | 3.196515 | 0.742881 | 0.751843 | 0.237085 |
| Calibrated pool best, budget 11 | 3.310026 | 0.826891 | 0.756650 | 0.237103 |
| LinearDesign-11 | 11.798970 | 26.439732 | 29.972887 | 0.071289 |

*Note.* Values average seeds within records and then records. All methods were evaluated under the same post hoc frozen normalization. Calibrated pool arms read development-native calibration before search and therefore do not share the raw common-input contract. These are proxy-objective outcomes, not functional-expression measurements.

Independent verification passed 5,401/5,401 checks across 324 runs and 3,564 raw points. It reconstructed every eight-member pool, selection index, and complete new trajectory, independently rescored 1,604 unique sequences with maximum absolute objective error 0.0, and reproduced all metrics and inference. The detached clean closeout passed 1,114/1,114 checks, and the full project suite recorded 494 passed tests, one skip, and five passed subtests.

Accordingly, RK41 supports internal multistart initialization as a useful search component but leaves the common-input actual-set task unresolved. It does not establish external SOTA, unified time-matched performance, functional improvement, protein-OOD generalization, untouched-confirmation success, RK-G1 completion, or manuscript-submittable status.
