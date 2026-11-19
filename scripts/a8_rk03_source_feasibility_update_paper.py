#!/usr/bin/env python3
"""Append the independently verified source-feasibility result to A8 as v27."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
OLD_PAPER_SHA='88cc89ccf83958110fb2fb20454df691ecebdfa164f7e7806fd8797aa6e482c5'
A7_SHA='941a9d48e8397c0646c5d6ae9fdf997230c606766d0e3988b295e4bd4d44d423'
def sha256(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
def dump(path,value): Path(path).write_text(json.dumps(value,indent=2,sort_keys=True,ensure_ascii=False)+'\n')
def build_section(production,independent,final):
 rows=[]
 for x in production['veloharmo_organism_feasibility']:
  src=x['raw_source']; release='matrix + GA' if x['released_harmonized_matrix_in_pinned_repo'] else ('GA only' if x['released_ga_checkpoint_in_pinned_repo'] else 'neither')
  rows.append(f"| {x['label']} | {x['organism']} | {x['source_accession']} | {', '.join(src['runinfo_accessions'])} | {src['run_count']} | {src['size_mb']:,} | {release} |")
 velo_runs=sum(x['raw_source']['run_count'] for x in production['veloharmo_organism_feasibility']); velo_size=sum(x['raw_source']['size_mb'] for x in production['veloharmo_organism_feasibility'])
 ribo_extra=[x for x in production['ribomimo_raw_feasibility'] if x['label']!='Mohammad16']; extra_runs=sum(x['raw_source']['run_count'] for x in ribo_extra); extra_size=sum(x['raw_source']['size_mb'] for x in ribo_extra)
 total_runs=sum(x['run_count'] for x in production['runinfo_evidence'].values()); total_size=sum(x['size_mb'] for x in production['runinfo_evidence'].values())
 return f"""### 6.23 Metadata-only recovery of Ribo-seq sources and VeloHARMO release scope

We audited whether the processed Ribo-seq evidence and the five-organism VeloHARMO comparison could be connected to public raw sources without treating processed matrices as completed remapping. The audit froze `BianBian2021/VeloHARMO` at commit `38b48079856aeb9d33a1b10844d77aa8f6640032` and retained official PMC, GEO SOFT and SRA RunInfo responses with file hashes. It did not download FASTQ, BAM or SRA reads, construct UTR–CDS annotations, align reads or fit a model.

All five VeloHARMO source studies had public run-level records. Official titles and full text map Dunn13 to *Drosophila melanogaster* and GSE49197, and Pop14 to *Saccharomyces cerevisiae* and GSE63789. The five studies comprised {velo_runs} runs and {velo_size:,} MB in RunInfo metadata. These sizes describe the public archives, not data transferred by this audit.

| Source study | Organism | Study accession | RunInfo accession | Runs | RunInfo size (MB) | Pinned release |
|---|---|---|---|---:|---:|---|
{chr(10).join(rows)}

The pinned repository contained 14 tree entries and 14 materialized blob files, all with matching current SHA-256 and byte counts. Its two E. coli matrix archives were byte-identical; E. coli and yeast genetic-algorithm checkpoints were present. No harmonized matrix archive for *P. aeruginosa*, *D. melanogaster*, *S. cerevisiae* or human was present in that snapshot. Thus a public raw source and a released checkpoint must not be interpreted as a released harmonized matrix.

For the RiboMIMO source layer, Mohammad19/GSE119104 contributed {ribo_extra[0]['raw_source']['run_count']} runs and {ribo_extra[0]['raw_source']['size_mb']:,} MB, while Subtelny14/GSE53268 contributed {ribo_extra[1]['raw_source']['run_count']} runs and {ribo_extra[1]['raw_source']['size_mb']:,} MB through its current BioProject relation PRJNA231671. Together with the shared Mohammad16 archive, the seven distinct RunInfo accessions contained {total_runs} runs and {total_size:,} MB. The additional RiboMIMO archives beyond Mohammad16 therefore contributed {extra_runs} runs and {extra_size:,} MB.

Independent offline verification reparsed every required response, rechecked the study mappings and recomputed all run counts, sizes and materialized-file hashes. It passed **{independent['check_counts']['passed']}/{independent['check_counts']['total']} checks**, with maximum numeric discrepancy {independent['production_independent_max_numeric_delta']}. Finalization passed **{final['check_counts']['passed']}/{final['check_counts']['total']} checks**. This closes only the bounded metadata-feasibility subtask. UTR–CDS construction, independent raw-read/P-site remapping, four non-E. coli harmonized matrices, the full natural-distribution report, mechanism validation and model training remain unperformed. Any future remapping must freeze reference versions per study and assess read length and end assignment per sample; no global P-site offset is licensed. RK-G1 remains open and the manuscript remains non-submittable.
"""
def main():
 ap=argparse.ArgumentParser()
 for name in ['paper','a7','sync-audit','production','independent','finalization','protocol','unit-test-log','artifact-manifest','update-record']: ap.add_argument('--'+name,required=True)
 args=ap.parse_args(); paper_path=Path(args.paper)
 if sha256(paper_path)!=OLD_PAPER_SHA: raise AssertionError('A8 is not the frozen v26 input')
 if sha256(args.a7)!=A7_SHA: raise AssertionError('A7 hash mismatch')
 production=json.loads(Path(args.production).read_text()); independent=json.loads(Path(args.independent).read_text()); final=json.loads(Path(args.finalization).read_text())
 if not production['overall_pass'] or production['check_counts']!={'total':74,'passed':74,'failed':0}: raise AssertionError('production not accepted')
 if not independent['independent_pass'] or independent['check_counts']!={'total':169,'passed':169,'failed':0}: raise AssertionError('independent not accepted')
 if not final['overall_pass'] or final['check_counts']!={'total':47,'passed':47,'failed':0} or not final['bounded_source_feasibility_closed']: raise AssertionError('finalization not accepted')
 section=build_section(production,independent,final); old=paper_path.read_text()
 if '### 6.23 Metadata-only recovery' in old: raise AssertionError('section already exists')
 marker='## 7. Discussion'
 if old.count(marker)!=1: raise AssertionError('Discussion marker missing')
 updated=old.replace(marker,section+'\n'+marker,1)
 hashes={'protocol':sha256(args.protocol),'production':sha256(args.production),'independent':sha256(args.independent),'finalization':sha256(args.finalization),'unit_tests':sha256(args.unit_test_log),'artifact_manifest':sha256(args.artifact_manifest)}
 anchors=(f"| RK03 source-feasibility frozen protocol | `{hashes['protocol']}` |\n"
          f"| RK03 source-feasibility production | `{hashes['production']}` |\n"
          f"| RK03 source-feasibility independent verification | `{hashes['independent']}` |\n"
          f"| RK03 source-feasibility finalization | `{hashes['finalization']}` |\n"
          f"| RK03 source-feasibility unit tests | `{hashes['unit_tests']}` |\n"
          f"| RK03 source-feasibility artifact manifest | `{hashes['artifact_manifest']}` |\n\n")
 anchor_marker='A7 is retained as the prior manuscript snapshot.'
 if updated.count(anchor_marker)!=1: raise AssertionError('evidence anchor insertion point missing')
 updated=updated.replace(anchor_marker,anchors+anchor_marker,1)
 snapshot_dir=paper_path.parent/'snapshots'/'rk03_source_feasibility_v27'; snapshot_dir.mkdir(parents=True,exist_ok=True)
 snapshot_paper=snapshot_dir/'CodonFlow_preprint_A8_v26.md'; snapshot_audit=snapshot_dir/'a8_rk_paper_sync_audit_v26.json'; snapshot_a7=snapshot_dir/'CodonFlow_preprint_A7.md'
 snapshot_paper.write_text(old); snapshot_audit.write_text(Path(args.sync_audit).read_text()); snapshot_a7.write_text(Path(args.a7).read_text()); paper_path.write_text(updated)
 sync=json.loads(Path(args.sync_audit).read_text()); sync['base_v26_paper_sha256']=OLD_PAPER_SHA; sync['base_v26_audit_sha256']=sha256(args.sync_audit); sync['generated_sections']=sync.get('generated_sections',[])+['6.23 Metadata-only recovery of Ribo-seq sources and VeloHARMO release scope','8.1 RK03 source-feasibility evidence anchors']
 sync['last_increment']={'section':'6.23 Metadata-only recovery of Ribo-seq sources and VeloHARMO release scope','protocol_sha256':hashes['protocol'],'production_sha256':hashes['production'],'independent_sha256':hashes['independent'],'finalization_sha256':hashes['finalization'],'paper_sha256':sha256(paper_path),'scientific_scope':'metadata-only public source recovery; no UTR-CDS mapping, raw/P-site remapping, harmonization, model result or RK-G1 closure','submittable':False}
 sync['output_sha256']=sha256(paper_path); sync['pre_rk03_source_feasibility_snapshot']={'paper':str(snapshot_paper),'paper_sha256':sha256(snapshot_paper),'audit':str(snapshot_audit),'audit_sha256':sha256(snapshot_audit),'a7':str(snapshot_a7),'a7_sha256':sha256(snapshot_a7)}
 sync['rk03_source_feasibility']={'status':production['status'],'production_checks':'74/74','independent_checks':'169/169','finalization_checks':'47/47','max_numeric_delta':0,'unique_runinfo_accessions':len(production['runinfo_evidence']),'runs':sum(x['run_count'] for x in production['runinfo_evidence'].values()),'size_mb':sum(x['size_mb'] for x in production['runinfo_evidence'].values()),'utr_cds_mapping_completed':False,'raw_remapping_completed':False,'rk_g1_pass':False,'generator_training_authorized':False,'sota_claim':False}
 dump(args.sync_audit,sync)
 record={'schema':'a8-rk03-source-feasibility-paper-update-v27','old_paper_sha256':OLD_PAPER_SHA,'new_paper_sha256':sha256(paper_path),'old_sync_audit_sha256':sha256(snapshot_audit),'new_sync_audit_sha256':sha256(args.sync_audit),'a7_sha256':A7_SHA,'section':section,'evidence_anchors':anchors,'snapshot_paper':str(snapshot_paper),'snapshot_audit':str(snapshot_audit),'snapshot_a7':str(snapshot_a7),'source_hashes':hashes,'submittable':False}
 dump(args.update_record,record); print(json.dumps({'old_paper_sha256':OLD_PAPER_SHA,'new_paper_sha256':record['new_paper_sha256'],'section':'6.23','submittable':False},indent=2))
if __name__=='__main__': main()
