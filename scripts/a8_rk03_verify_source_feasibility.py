#!/usr/bin/env python3
"""Independent frozen-response verifier; does not import production or use network."""
import csv, hashlib, json, re, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'configs/a8_rk03_source_feasibility_protocol_v1.json'
A=ROOT/'audits/20261120/RK03'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def main():
 protocol=json.loads(P.read_text()); prod=json.loads((A/'source_feasibility_v1.json').read_text()); raw=Path(protocol['artifact_root'])/'raw'; checks=[]; deltas=[]
 def add(name,ok,evidence=None): checks.append({'check':name,'pass':bool(ok),'evidence':evidence})
 def eq(name,a,b):
  ok=a==b; add(name,ok,{'independent':a,'production':b})
  if isinstance(a,(int,float)) and isinstance(b,(int,float)): deltas.append(abs(a-b))
 eq('protocol_sha',sha(P),prod['protocol_sha256'])
 required=[r for r in prod['retrieval'] if r['required']]
 for r in required:
  f=Path(r['path']); add('required_retrieval_success_'+r['label'],r.get('ok') is True); add('required_raw_sha_'+r['label'],f.exists() and sha(f)==r.get('sha256'))
 # Independently inspect the full text of each source paper.
 for ref in protocol['veloharmo']['references']:
  text=(raw/f"{ref['pmcid']}.html").read_text(errors='replace'); pr=next(x for x in prod['source_paper_evidence'] if x['label']==ref['label'])
  add(ref['label']+'_doi',ref['doi'].lower() in text.lower()); add(ref['label']+'_accession',ref['accession'] in text)
  eq(ref['label']+'_production_accession_flag',ref['accession'] in text,pr['accession_found'])
 # Independent SOFT extraction directly from raw lines.
 geo_ind={}
 for acc,g in prod['geo_evidence'].items():
  text=(raw/f'{acc}.soft.txt').read_text(errors='replace'); lines=text.splitlines(); vals=lambda prefix:[x.split('=',1)[1].strip() for x in lines if x.startswith(prefix)]
  title=(vals('!Series_title') or [None])[0]; samples=len(set(vals('!Series_sample_id')))
  relations=sorted(set(re.findall(r'SRP\d+','\n'.join(x for x in lines if x.startswith('!Series_relation = SRA')))))
  builds=sorted(set(x.strip() for x in re.findall(r'Genome_build:\s*([^\n]+)',text,re.I)))
  geo_ind[acc]={'sra_relations':relations,'run_count':0,'size_mb':0}
  eq(acc+'_title',title,g['title']); eq(acc+'_samples',samples,g['series_sample_count']); eq(acc+'_relations',relations,g['sra_relations']); eq(acc+'_builds',builds,g['genome_builds'])
  for evidence in g['site_assignment_evidence']: add(acc+'_site_evidence_'+hashlib.sha256(evidence.encode()).hexdigest()[:12],evidence in text)
 # Independent RunInfo recomputation.
 run_ind={}
 for acc,r in prod['runinfo_evidence'].items():
  rows=list(csv.DictReader((raw/f'{acc}.runinfo.csv').open()))
  runs=len(set(x['Run'] for x in rows)); size=sum(int(float(x.get('size_MB') or 0)) for x in rows); bases=sum(int(float(x.get('bases') or 0)) for x in rows); paths=sum(bool(x.get('download_path')) for x in rows)
  eq(acc+'_runs',runs,r['run_count']); eq(acc+'_size_mb',size,r['size_mb']); eq(acc+'_bases',bases,r['bases']); eq(acc+'_download_paths',paths,r['download_path_rows'])
  run_ind[acc]={'run_count':runs,'size_mb':size}
 # Independently rehash the frozen materialized source/payload inventory.
 v=protocol['veloharmo']; mat_path=Path(v['materialization_audit']); tree_path=Path(v['source_tree_audit']); mat=json.loads(mat_path.read_text()); tree=json.loads(tree_path.read_text())
 add('materialization_sha',sha(mat_path)==v['materialization_audit_sha256']); add('source_tree_sha',sha(tree_path)==v['source_tree_audit_sha256'])
 eq('repository_commit',mat['commit'],prod['pinned_repository']['commit']); add('source_tree_commit',tree['commit']==mat['commit']==v['pinned_commit'])
 for rec in mat['files']:
  base=Path(v['payload_dir']) if rec['storage']=='teams' else Path(v['source_dir']); f=base/rec['path']; current=sha(f) if f.exists() else None
  add('materialized_file_'+rec['path'],current==rec['sha256'] and f.stat().st_size==rec['bytes'])
 zips=sorted(x['path'] for x in mat['files'] if x['path'].endswith('E.coli.summary.add.pro.SS.txt.zip')); cps=sorted(x['path'] for x in mat['files'] if x['path'].startswith('Genetic_algorithm/') and x['path'].endswith('.pth'))
 eq('release_zips',zips,prod['pinned_repository']['harmonized_matrix_zips']); eq('release_checkpoints',cps,prod['pinned_repository']['ga_checkpoints'])
 add('two_ecoli_zips_identical',len({x['sha256'] for x in mat['files'] if x['path'] in zips})==1)
 # Cross-check aggregated study records against independently parsed runinfo.
 for v in prod['veloharmo_organism_feasibility']:
  acc=v['source_accession']; src=v['raw_source']; expected=[]
  if acc in geo_ind: expected=geo_ind[acc]['sra_relations']
  elif acc in prod['runinfo_evidence']: expected=[acc]
  rr=[run_ind[x] for x in expected]
  run_count=sum(x['run_count'] for x in rr); size=sum(x['size_mb'] for x in rr)
  eq(v['label']+'_aggregate_runs',run_count,src['run_count']); eq(v['label']+'_aggregate_size',size,src['size_mb'])
  add(v['label']+'_raw_public',src['public_runinfo_available'] and run_count>0)
  expected_release=v['organism']=='Escherichia coli'; add(v['label']+'_matrix_scope',v['released_harmonized_matrix_in_pinned_repo']==expected_release)
 for r in prod['ribomimo_raw_feasibility']:
  add(r['label']+'_raw_public',r['raw_source']['public_runinfo_available'] and r['raw_source']['run_count']>0)
  add(r['label']+'_cds_only_not_utr_map','CDS-only' in r['processed_matrix_scope'] and r['status'].endswith('REMAP_NOT_PERFORMED'))
 add('exactly_one_released_matrix',sum(x['released_harmonized_matrix_in_pinned_repo'] for x in prod['veloharmo_organism_feasibility'])==1)
 add('four_unreleased_harmonized_matrices',sum(not x['released_harmonized_matrix_in_pinned_repo'] for x in prod['veloharmo_organism_feasibility'])==4)
 add('no_read_files',prod['large_read_files_downloaded']==[])
 add('no_utr_map',prod['utr_cds_and_site_protocol']['utr_cds_mapping_completed'] is False)
 add('no_raw_remap',prod['utr_cds_and_site_protocol']['raw_read_remapping_completed'] is False)
 add('no_global_offset',prod['utr_cds_and_site_protocol']['global_p_site_offset_permitted'] is False)
 add('rk_g1_open',prod['boundaries']['rk_g1_closed'] is False)
 add('generator_unauthorized',prod['boundaries']['expensive_generator_training_authorized'] is False)
 add('manuscript_not_submittable',prod['boundaries']['manuscript_submittable'] is False)
 add('production_checks_all_pass',all(x['pass'] for x in prod['checks']))
 add('production_terminal_status',prod['status']==protocol['expected_terminal_status'])
 ok=all(x['pass'] for x in checks)
 out={'protocol_id':protocol['protocol_id'],'production_report':str(A/'source_feasibility_v1.json'),'independent_pass':ok,'status':'INDEPENDENT_SOURCE_FEASIBILITY_PASS' if ok else 'INDEPENDENT_SOURCE_FEASIBILITY_FAIL','check_counts':{'total':len(checks),'passed':sum(x['pass'] for x in checks),'failed':sum(not x['pass'] for x in checks)},'checks':checks,'production_independent_max_numeric_delta':max(deltas,default=0),'network_used':False,'production_module_imported':False,'conclusion':'Independent raw-response and pinned-mirror recomputation supports metadata recoverability only; it is not UTR-CDS construction, raw-read/P-site remapping, harmonized-matrix generation, model evidence, or RK-G1 closure.'}
 (A/'source_feasibility_independent_v1.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n'); print(json.dumps({k:out[k] for k in ['independent_pass','status','check_counts','production_independent_max_numeric_delta']},indent=2))
 if not ok: raise SystemExit(1)
if __name__=='__main__': main()
