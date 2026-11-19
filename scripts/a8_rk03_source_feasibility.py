#!/usr/bin/env python3
"""Metadata-only Ribo/VeloHARMO source-feasibility audit; never downloads reads."""
import argparse, csv, hashlib, io, json, re, subprocess, time, urllib.error, urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()

def fetch(url,path,policy,required=True):
 rec={'url':url,'path':str(path),'required':required,'attempts':0}
 for attempt in range(1,int(policy['retries'])+1):
  rec['attempts']=attempt
  try:
   req=urllib.request.Request(url,headers={'User-Agent':policy['user_agent'],'Accept':'text/html,application/json,text/plain,*/*'})
   with urllib.request.urlopen(req,timeout=int(policy['timeout_seconds'])) as r:
    raw=r.read(); rec['http_status']=getattr(r,'status',200)
   path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(raw)
   rec.update(ok=True,bytes=len(raw),sha256=sha(path)); return rec
  except urllib.error.HTTPError as e:
   body=e.read(); rec.update(ok=False,http_status=e.code,error=f'HTTP {e.code}',bytes=len(body))
   path.parent.mkdir(parents=True,exist_ok=True); path.with_suffix(path.suffix+'.error.txt').write_bytes(body)
   if e.code not in (429,500,502,503,504): return rec
  except Exception as e:
   rec.update(ok=False,error=f'{type(e).__name__}: {e}')
  if attempt<int(policy['retries']): time.sleep(float(policy['backoff_seconds'])*attempt)
 return rec

def parse_soft(text):
 lines=text.splitlines()
 vals=lambda prefix:[x.split('=',1)[1].strip() for x in lines if x.startswith(prefix)]
 proc=vals('!Sample_data_processing')
 site=sorted(set(x for x in proc if re.search(r'P-site|A-site|offset|3.{0,3}-end|5.{0,3}-end',x,re.I)))
 return {
  'title':(vals('!Series_title') or [None])[0],
  'series_sample_count':len(set(vals('!Series_sample_id'))),
  'sample_record_count':sum(x.startswith('^SAMPLE') for x in lines),
  'sra_relations':sorted(set(re.findall(r'SRP\d+','\n'.join(vals('!Series_relation = SRA'))))),
  'bioproject_relations':sorted(set(re.findall(r'PRJNA\d+','\n'.join(vals('!Series_relation = BioProject'))))),
  'genome_builds':sorted(set(y.strip() for x in proc for y in re.findall(r'Genome_build:\s*([^\n]+)',x,re.I))),
  'library_strategies':dict(Counter(vals('!Sample_library_strategy'))),
  'site_assignment_evidence':site,
  'supplementary_files':sorted(set(vals('!Series_supplementary_file'))),
  'accessions_in_text':sorted(set(re.findall(r'(?:GSE|SRP|SRX|SRR|PRJNA)\d+',text)))
 }

def parse_runinfo(text):
 rows=list(csv.DictReader(io.StringIO(text)))
 if not rows or 'Run' not in rows[0]: raise ValueError('RunInfo has no Run rows')
 def total(key):
  out=0
  for r in rows:
   try: out+=int(float(r.get(key) or 0))
   except ValueError: pass
  return out
 return {'run_count':len(set(r['Run'] for r in rows)),'row_count':len(rows),
  'experiment_count':len(set(r.get('Experiment','') for r in rows if r.get('Experiment'))),
  'spots':total('spots'),'bases':total('bases'),'size_mb':total('size_MB'),
  'download_path_rows':sum(bool(r.get('download_path')) for r in rows),
  'library_strategies':dict(Counter(r.get('LibraryStrategy','') for r in rows)),
  'runs':sorted(set(r['Run'] for r in rows))}

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--protocol',default=str(ROOT/'configs/a8_rk03_source_feasibility_protocol_v1.json')); ap.add_argument('--output'); args=ap.parse_args()
 p=Path(args.protocol); protocol=json.loads(p.read_text()); art=Path(protocol['artifact_root']); raw=art/'raw'; raw.mkdir(parents=True,exist_ok=True)
 checks=[]
 def add(name,ok,evidence=None): checks.append({'check':name,'pass':bool(ok),'evidence':evidence})
 retrieval=[]
 # Optional live endpoints: errors are retained and never replace the pinned mirror.
 for label,url in [('veloharmo_publisher',protocol['veloharmo']['article_url']),('veloharmo_live_github_tree',protocol['veloharmo']['github_tree_url'])]:
  rec=fetch(url,raw/f'{label}.response',protocol['network_policy'],required=False); rec['label']=label; retrieval.append(rec)
 # Five source papers identify the organism-specific raw accessions.
 references=[]
 for ref in protocol['veloharmo']['references']:
  url=protocol['pmc_url_template'].format(pmcid=ref['pmcid']); path=raw/f"{ref['pmcid']}.html"
  rec=fetch(url,path,protocol['network_policy']); rec['label']=ref['label']; retrieval.append(rec)
  text=path.read_text(errors='replace') if rec.get('ok') else ''
  doi_ok=ref['doi'].lower() in text.lower(); acc_ok=ref['accession'] in text
  references.append({**ref,'source_url':url,'source_sha256':rec.get('sha256'),'doi_found':doi_ok,'accession_found':acc_ok})
  add(f"{ref['label']}_doi_in_official_full_text",doi_ok)
  add(f"{ref['label']}_accession_in_official_full_text",acc_ok,ref['accession'])
 # GEO SOFT records and their sample-level processing metadata.
 geo={}
 for acc in protocol['ribomimo_geo_accessions']+protocol['additional_veloharmo_geo_accessions']:
  url=protocol['geo_url_template'].format(accession=acc); path=raw/f'{acc}.soft.txt'
  rec=fetch(url,path,protocol['network_policy']); rec['label']=acc; retrieval.append(rec)
  if not rec.get('ok'): add(f'{acc}_soft_retrieved',False); continue
  parsed=parse_soft(path.read_text(errors='replace')); geo[acc]={**parsed,'source_url':url,'source_sha256':rec['sha256'],'bytes':rec['bytes']}
  add(f'{acc}_soft_retrieved',True,rec['sha256'])
  add(f'{acc}_series_title_present',bool(parsed['title']),parsed['title'])
  add(f'{acc}_sample_metadata_present',parsed['series_sample_count']>0,parsed['series_sample_count'])
  add(f'{acc}_sra_relation_present',len(parsed['sra_relations'])>0,parsed['sra_relations'])
 # SRA RunInfo establishes public run-level recoverability, not downloaded reads.
 run_accessions=list(protocol['direct_bioproject_accessions'])
 for g in geo.values(): run_accessions.extend(g['sra_relations'])
 run_accessions=sorted(set(run_accessions)); runs={}
 for acc in run_accessions:
  url=protocol['runinfo_url_template'].format(accession=acc); path=raw/f'{acc}.runinfo.csv'
  rec=fetch(url,path,protocol['network_policy']); rec['label']=acc; retrieval.append(rec)
  if not rec.get('ok'): add(f'{acc}_runinfo_retrieved',False); continue
  try: parsed=parse_runinfo(path.read_text(errors='replace'))
  except Exception as e:
   add(f'{acc}_runinfo_parsed',False,str(e)); continue
  runs[acc]={**parsed,'source_url':url,'source_sha256':rec['sha256']}
  add(f'{acc}_runinfo_public_runs',parsed['run_count']>0,parsed['run_count'])
  add(f'{acc}_runinfo_size_nonnegative',parsed['size_mb']>=0,parsed['size_mb'])
  add(f'{acc}_runinfo_download_paths',parsed['download_path_rows']>0,parsed['download_path_rows'])
 # Pinned official repository mirror: release contents, not a live-GitHub claim.
 repo=Path(protocol['veloharmo']['repository'])
 commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
 files=[]
 for f in sorted(repo.rglob('*')):
  if f.is_file() and '.git' not in f.relative_to(repo).parts:
   files.append({'path':str(f.relative_to(repo)),'bytes':f.stat().st_size,'sha256':sha(f)})
 paths=[x['path'] for x in files]
 zips=sorted(x for x in paths if x.startswith('GA_Species_') and x.endswith('.zip'))
 checkpoints=sorted(x for x in paths if x.startswith('GA/') and x.endswith('GA.pickle'))
 source_ref=(repo/'VeloHARMO/source_references.py').read_text()
 add('pinned_repository_commit',commit==protocol['veloharmo']['pinned_commit'],commit)
 add('only_ecoli_harmonized_matrix_zip',zips==['GA_Species_Ecoli_public.zip'],zips)
 add('ecoli_and_yeast_ga_checkpoints_only',checkpoints==['GA/Ecoli/GA.pickle','GA/yeast/GA.pickle'],checkpoints)
 add('all_five_source_dois_in_pinned_mirror',all(r['doi'] in source_ref for r in protocol['veloharmo']['references']))
 add('no_other_species_harmonized_matrix_zip',len(zips)==1)
 # Compact per-study feasibility records.
 def raw_for(acc):
  if acc in geo:
   relations=geo[acc]['sra_relations']; r=[runs[x] for x in relations if x in runs]
   return {'geo_accession':acc,'runinfo_accessions':relations,'run_count':sum(x['run_count'] for x in r),'size_mb':sum(x['size_mb'] for x in r),'genome_builds':geo[acc]['genome_builds'],'site_assignment_evidence':geo[acc]['site_assignment_evidence'],'public_runinfo_available':bool(r)}
  r=runs.get(acc)
  return {'bioproject_accession':acc,'runinfo_accessions':[acc] if r else [],'run_count':r['run_count'] if r else 0,'size_mb':r['size_mb'] if r else 0,'genome_builds':[],'site_assignment_evidence':[],'public_runinfo_available':bool(r)}
 velo=[]
 for ref in references:
  organism_key={'Escherichia coli':'Ecoli','Pseudomonas aeruginosa':'Paer','Drosophila melanogaster':'Dmel','Saccharomyces cerevisiae':'yeast','Homo sapiens':'human'}[ref['organism']]
  velo.append({'organism':ref['organism'],'label':ref['label'],'source_accession':ref['accession'],'source_paper_accession_verified':ref['accession_found'],'released_harmonized_matrix_in_pinned_repo':f'GA_Species_{organism_key}_public.zip' in zips,'released_ga_checkpoint_in_pinned_repo':any(x.startswith(f'GA/{organism_key}/') for x in checkpoints),'raw_source':raw_for(ref['accession']),'status':'RAW_PUBLIC_BUT_HARMONIZED_MATRIX_NOT_IN_PINNED_REPO' if organism_key!='Ecoli' else 'ECOLI_MATRIX_AND_RAW_PUBLIC'})
 ribo=[]
 for acc,label in [('GSE72899','Mohammad16'),('GSE119104','Mohammad19'),('GSE53268','Subtelny14')]:
  ribo.append({'label':label,'accession':acc,'processed_matrix_scope':'CDS-only A-site matrix; no UTR-CDS map constructed by this audit','raw_source':raw_for(acc),'status':'PUBLIC_RAW_METADATA_RECOVERABLE_REMAP_NOT_PERFORMED'})
 forbidden=[str(f) for f in art.rglob('*') if f.is_file() and (f.suffix.lower() in ('.fastq','.fq','.bam','.sra') or any(str(f).endswith(x) for x in ('.fastq.gz','.fq.gz')))]
 add('no_large_read_files_downloaded',not forbidden,forbidden)
 add('all_five_veloharmo_raw_sources_public',all(x['raw_source']['public_runinfo_available'] for x in velo))
 add('four_non_ecoli_harmonized_matrices_absent',sum(x['released_harmonized_matrix_in_pinned_repo'] for x in velo)==1)
 add('all_three_ribomimo_raw_sources_public',all(x['raw_source']['public_runinfo_available'] for x in ribo))
 add('utr_cds_mapping_not_claimed',protocol['required_boundaries']['utr_cds_mapping_completed'] is False)
 add('raw_remapping_not_claimed',protocol['required_boundaries']['raw_read_remapping_completed'] is False)
 add('no_global_offset_claimed',protocol['required_boundaries']['no_global_p_site_offset'] is True)
 add('rk_g1_remains_open',protocol['required_boundaries']['rk_g1_closed'] is False)
 add('generator_remains_unauthorized',protocol['required_boundaries']['expensive_generator_training_authorized'] is False)
 ok=all(x['pass'] for x in checks)
 report={'protocol_id':protocol['protocol_id'],'protocol_sha256':sha(p),'created_utc':datetime.now(timezone.utc).isoformat(),'status':protocol['expected_terminal_status'] if ok else 'SOURCE_FEASIBILITY_AUDIT_INCOMPLETE','overall_pass':ok,'scope':'Official metadata and pinned-release feasibility audit only; no FASTQ/BAM/SRA download, alignment, UTR-CDS construction, model fitting or model evaluation.','checks':checks,'check_counts':{'total':len(checks),'passed':sum(x['pass'] for x in checks),'failed':sum(not x['pass'] for x in checks)},'retrieval':retrieval,'source_paper_evidence':references,'geo_evidence':geo,'runinfo_evidence':runs,'pinned_repository':{'path':str(repo),'commit':commit,'files':files,'harmonized_matrix_zips':zips,'ga_checkpoints':checkpoints,'live_api_scope':'Live API/publisher responses are retained separately; a 404/403 does not alter the pinned-mirror evidence.'},'veloharmo_organism_feasibility':velo,'ribomimo_raw_feasibility':ribo,'utr_cds_and_site_protocol':{'utr_cds_mapping_completed':False,'raw_read_remapping_completed':False,'reference_versions_must_be_frozen_per_study':True,'read_length_and_end_assignment_must_be_assessed_per_sample':True,'global_p_site_offset_permitted':False,'reason':'GEO/source papers expose heterogeneous processed assignments and genome builds; public reads make a new protocol feasible but do not validate a universal offset or recreate UTR annotations.'},'large_read_files_downloaded':forbidden,'boundaries':protocol['required_boundaries'],'conclusion':'Public raw sources are recoverable at runinfo level and the pinned VeloHARMO mirror contains only the Ecoli harmonized matrix; four other organisms have public source studies but no released harmonized matrix in that snapshot. UTR-CDS mapping and independent P-site remapping remain feasible future protocols, not completed evidence.'}
 out=Path(args.output) if args.output else Path(protocol['audit_root'])/'source_feasibility_v1.json'; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
 manifest=[{'path':str(f.relative_to(art)),'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(art.rglob('*')) if f.is_file() and f.name!='artifact_manifest.json']
 (art/'artifact_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({'output':str(out),'overall_pass':ok,'status':report['status'],'checks':report['check_counts'],'runinfo':{k:{'runs':v['run_count'],'size_mb':v['size_mb']} for k,v in runs.items()},'artifact_root':str(art)},indent=2))
 if not ok: raise SystemExit(1)
if __name__=='__main__': main()
