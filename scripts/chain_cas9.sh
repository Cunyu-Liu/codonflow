#!/bin/bash
CKPT=/mnt/cunyuliu/codonflow/checkpoints/p2_pretrain_v2_corrupt/converged.pt
L=/home/cunyuliu/codonflow/scripts/launch_e5ood.sh
S5=MIG-6e59f9af-2716-5bf2-ac6e-fb05ef744585
JSON=/mnt/cunyuliu/codonflow/eval_outputs/E5_ood_nluc_s2.json
while [ ! -f $JSON ]; do sleep 60; done
sleep 30
tmux new-session -d -s e5o_cas9 "$L $S5 /mnt/cunyuliu/codonflow/corpora/cas9_probe.fasta $CKPT cas9 20 3 --n-steps 5 --n-candidates 5"
echo "cas9 launched at $(date)" >> /mnt/cunyuliu/codonflow/logs/e5ood_watch.log
