# Experiment Registry (schema frozen, spec R6-3)

| run_id | date | phase | cmd | gpu | data_version | code_commit | hyperparams | convergence | final_metrics | status |
|---|---|---|---|---|---|---|---|---|---|---|
| CF-P1-1.2.2-ld-bench-001 | 2026-10-04 | P1 | `PYTHONPATH=src python scripts/bench_lineardesign.py --benchmark-fasta corpora/bench.fasta --n-repeats 3` | CPU (DP is CPU-bound) | gencode_v47+ensembl r112 (bench: egfp_syn+nluc) | 47e29c8 | lambda=0 (MFE-only), human codon table, 3 repeats | n/a | eGFP 27.7s/seq CAI .794 MFE -444.1; nluc 17.6s/seq CAI .825 MFE -347.5; identity 2/2 | done |
| CF-P2-2.1.2-pretrain-001 | 2026-10-04 | P2 | `CUDA_VISIBLE_DEVICES=MIG-10b9b777 PYTHONPATH=src python src/codonflow/train/run_pretrain.py --train-fasta splits/train.fasta --val-fasta splits/val.fasta --out-dir checkpoints/p2_pretrain_768d --d-model 768 --n-layers 8 --n-heads 12 --dropout 0.0 --lr 1e-5 --batch-tokens 24000` | GPU7 MIG 3g.20gb (21GB) | combined 215246 CDS, 107811 clusters, 80/10/10 cluster split | 47e29c8 | 768d/8L/12H 56.8M params, AdamW lr 1e-5 wd 0.03, token-budget 24k packing, 3705 batches/epoch | running: plateau 3x<0.1% val | e1 in progress, train loss 5.81→4.13 | running |

<!-- run_id format: CF-<phase>-<task>-<nnn> -->
