#!/usr/bin/env python3
"""Apply the reviewed CAGFN bounded-smoke increment to manuscript v23."""
import argparse, hashlib, json, shutil
from pathlib import Path

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',required=True);ap.add_argument('--report',required=True);a=ap.parse_args()
    repo=Path(a.repo).resolve();paper=repo/'paper/CodonFlow_preprint_A8.md';auditp=repo/'paper/a8_rk_paper_sync_audit.json';a7=repo/'paper/CodonFlow_preprint_A7.md'
    assert sha(paper)=='dd87b75d5b3d73e2db5500921a12d0195ad5b0c299b06ea487f341f6cd40b419'
    assert sha(auditp)=='b39f57a006b3aeaa9e46bb781dafad76d5901c9c849dcb4f96dafecd4d2a8f92'
    assert sha(a7)=='941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423'
    root=repo/'audits/20261118/RK05';runp=root/'cagfn_official_smoke_v4.json';indp=root/'cagfn_official_smoke_independent_v4.json';finp=root/'cagfn_official_smoke_finalization_v1.json';protop=repo/'configs/a8_rk05_cagfn_official_smoke_protocol_v4.json'
    run=json.loads(runp.read_text());ind=json.loads(indp.read_text());fin=json.loads(finp.read_text());protocol=json.loads(protop.read_text())
    assert fin['status']=='PASS_RK05_CAGFN_OFFICIAL_BOUNDED_SMOKE' and fin['completion']['paper_update_authorized']
    assert ind['status']=='PASS' and ind['checks_passed']==33 and ind['checks_total']==33
    s=ind['summary'];c=ind['cost']
    snap=repo/'paper/snapshots/rk05_cagfn_v23';snap.mkdir(parents=True,exist_ok=True)
    shutil.copy2(paper,snap/'CodonFlow_preprint_A8_v22.md');shutil.copy2(auditp,snap/'a8_rk_paper_sync_audit_v22.json');shutil.copy2(a7,snap/'CodonFlow_preprint_A7.md')
    section=f"""### 6.19 CAGFN official-source bounded train-generate-audit chain

I evaluated the public CAGFN source tree (Laajil et al., 2025) at commit `952ccf9682988ef88cf1251877e918b85fbee9e9`. The public tree contained no pretrained weights, so a real training run was required. The associated OpenReview page is marked rejected and is not treated as peer-reviewed acceptance. The published environment declared TorchGFN 1.1.1, but that version lacks the imported `MLP` class; versions 1.2 and 2.0.1 also failed the disclosed import or estimator checks. I therefore retained the unmodified CAGFN source and used TorchGFN 2.1.0 at commit `1fab00a1f388aba902b5c9c1b778f4d0ae6e18a0` as a dependency-compatibility recovery, not as the original author environment or an author-endorsed correction.

The successful process executed the official unconditional `main.py` on the 33-codon small-protein configuration with an explicit MLP override, two iterations, 20 samples, batch size 16, seed 42 and one CPU thread. Three earlier bounded attempts were retained unchanged: a wrapper interpreter-path failure, an unconditional estimator assertion under TorchGFN 2.0.1, and a conditional-entry import failure under TorchGFN 2.0.1. The recovered process completed in {c['total_wall_clock_seconds']:.6f} s of total wall clock, including {c['training_seconds']:.2f} s reported for training and {c['inference_seconds']:.2f} s for sampling, and saved a real checkpoint with two finite loss and reward entries.

Independent raw-output verification passed {ind['checks_passed']}/{ind['checks_total']} checks. All 20 sequences were unique, 99 nt long, protein-identical, AUG-initiated and free of internal stops. Direct CAI and bundled-RNAFolder recomputation, rather than the upstream exception-to-zero utilities, reproduced every printed value within two-decimal rounding error; no MFE or CAI value was zero. Finalization passed {fin['checks_passed']}/{fin['checks_total']} checks.

| Bounded CAGFN smoke quantity | Independently recomputed value |
|---|---:|
| Unique / total sequences | {s['n_unique_sequences']} / {s['n_sequences']} |
| Protein identity | 20 / 20 |
| Mean GC (%) | {s['mean_gc_percent']:.6f} |
| Mean bundled-RNAFolder MFE (kcal/mol) | {s['mean_official_rnafolder_mfe_kcal_mol']:.6f} |
| Mean CAI using the source's human reference set | {s['mean_cai']:.6f} |
| Mean pairwise normalized edit distance | {s['mean_pairwise_normalized_edit_distance']:.6f} |

This is a bounded dependency-recovery smoke, not a converged model, full CAGFN reproduction or comparative performance result. Its MFE uses CAGFN's bundled `RNAFolder`, not the ViennaRNA-based scorer used for LinearDesign and EnsembleDesign; its CAI uses the hard-coded human reference set, not each target's natural mRNA. The MLP override also differs from the architecture named in the small-protein YAML. Accordingly, these descriptive values are not entered into the seven-method matrix, and the measured times are not time-matched costs. This section contains no functional, OOD, wet-lab or SOTA claim.

"""
    old=paper.read_text();marker='## 7. Discussion\n';assert old.count(marker)==1
    text=old.replace(marker,section+marker,1)
    anchor_names=[('RK05 CAGFN v4 frozen protocol',protop),('RK05 CAGFN retained v1 failure',root/'cagfn_official_smoke_v1.json'),('RK05 CAGFN retained v2 failure',root/'cagfn_official_smoke_v2.json'),('RK05 CAGFN retained v3 failure',root/'cagfn_official_smoke_v3.json'),('RK05 CAGFN official bounded production',runp),('RK05 CAGFN independent raw-output verification',indp),('RK05 CAGFN finalization',finp)]
    anchors=''.join(f'| {name} | `{sha(p)}` |\n' for name,p in anchor_names)
    amarker='A7 is retained as the prior manuscript snapshot.';assert text.count(amarker)==1
    text=text.replace(amarker,anchors+'\n'+amarker,1);paper.write_text(text)
    audit=json.loads(auditp.read_text());parent_audit_sha=sha(auditp)
    audit['base_v22_paper_sha256']=sha(snap/'CodonFlow_preprint_A8_v22.md');audit['base_v22_audit_sha256']=parent_audit_sha
    for name in ['6.19 CAGFN official-source bounded train-generate-audit chain','8.1 RK05 CAGFN evidence anchors']:
        if name not in audit['generated_sections']:audit['generated_sections'].append(name)
    audit['schema_version']='a8-rk-paper-sync-v18';audit['pre_rk05_cagfn_snapshot']={'paper':str(snap/'CodonFlow_preprint_A8_v22.md'),'paper_sha256':sha(snap/'CodonFlow_preprint_A8_v22.md'),'audit':str(snap/'a8_rk_paper_sync_audit_v22.json'),'audit_sha256':sha(snap/'a8_rk_paper_sync_audit_v22.json'),'a7':str(snap/'CodonFlow_preprint_A7.md'),'a7_sha256':sha(snap/'CodonFlow_preprint_A7.md')}
    for key,p in [('cagfn_protocol_v4',protop),('cagfn_production_v4',runp),('cagfn_independent_v4',indp),('cagfn_finalization_v1',finp)]:audit['source_paths'][key]=str(p)
    audit['scientific_scope']['cagfn_official_smoke']='Official unmodified main.py bounded MLP smoke with TorchGFN 2.1.0 compatibility recovery; two iterations and 20 samples on one 33-codon protein; real checkpoint and 20 independently verified protein-identical unique sequences; no convergence, full reproduction, matched performance, OOD or SOTA claim.'
    audit['scientific_scope']['sota']=False;audit['scientific_scope']['submittable']=False;audit['output_sha256']=sha(paper)
    audit['rk05_cagfn_v23']={'production_sha256':sha(runp),'independent_sha256':sha(indp),'finalization_sha256':sha(finp),'protocol_sha256':sha(protop),'paper_sha256':sha(paper)}
    auditp.write_text(json.dumps(audit,indent=2,sort_keys=True)+'\n')
    update={'schema':'a8.rk05.cagfn_paper_update.v1','status':'PASS','parent_paper_sha256':audit['base_v22_paper_sha256'],'parent_audit_sha256':parent_audit_sha,'paper_sha256':sha(paper),'audit_sha256':sha(auditp),'a7_sha256':sha(a7),'section':'6.19','evidence_anchor_count':len(anchor_names),'snapshot_dir':str(snap),'non_submittable':True}
    Path(a.report).write_text(json.dumps(update,indent=2)+'\n');print(json.dumps(update,indent=2))
if __name__=='__main__':main()
