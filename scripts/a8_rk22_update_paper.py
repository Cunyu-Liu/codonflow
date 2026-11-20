#!/usr/bin/env python3
"""Bind the accepted RK21/RK22 section to the frozen working manuscript."""
from pathlib import Path
import hashlib,json

REPO=Path('/home/codonflow-a8-rk')
AUDIT=REPO/'audits/20261121/RK22/paper'
PAPER=REPO/'paper/CodonFlow_preprint_A8.md'
BACKUP=Path('/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk22/paper_v1/CodonFlow_preprint_A8.before_rk22.md')
EXPECTED_BEFORE='fe92cf4390f9cb79281002f094ca54a6cf79672895d362f4b4d1835c7d18338e'
OLD='The functional long table contains **25,420 rows** and has SHA256 `c436b758369018fe0fd121ce6e741993e90a5de80b4706ab87082f7557b6a377`. It comprises the verified Boël cross-protein records and MAGE construct-assay rows. The row-level Kudla 154-variant sequence–expression table remains unavailable; supporting methods and degenerate oligos are not substitutes for that table.'
NEW='The functional long table contains **25,420 rows** and has SHA256 `c436b758369018fe0fd121ce6e741993e90a5de80b4706ab87082f7557b6a377`. It comprises the verified Boël cross-protein records and MAGE construct-assay rows. The previously unavailable row-level Kudla table has now been recovered: 154 measurement rows represent 150 unique exact CDS, and 72 tagged measurements represent 71 exact CDS. These fixed-GFP data are development-only; identical CDS are grouped before fitting, and no tagged nucleotide sequences were imputed (Sections 6.32–6.33).'

def sha_bytes(data): return hashlib.sha256(data).hexdigest()
def sha(path): return sha_bytes(Path(path).read_bytes())

def main():
    source=PAPER.read_bytes()
    before=sha_bytes(source)
    if before!=EXPECTED_BEFORE: raise SystemExit(f'unexpected manuscript state: {before}')
    text=source.decode()
    if text.count(OLD)!=1: raise SystemExit('old data-availability paragraph is not unique')
    if '### 6.32 ' in text or '### 6.33 ' in text: raise SystemExit('RK21/RK22 sections already exist')
    section_path=AUDIT/'rk22_manuscript_section.md'
    section=section_path.read_text()
    if not section.startswith('# RK21/RK22 Results Increment\n'): raise SystemExit('unexpected section heading')
    body=section.split('\n',1)[1].lstrip()
    marker='## 7. Discussion'
    if text.count(marker)!=1: raise SystemExit('discussion marker is not unique')
    text=text.replace(OLD,NEW,1).replace(marker,body+'\n'+marker,1)
    evidence_paths=[
        ('RK21 Kudla main source CSV',Path('/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk21/kudla_recovery_v1/derived/kudla154_source.csv')),
        ('RK21 Kudla tagged source CSV',Path('/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk21/kudla_recovery_v1/derived/kudla_tagged72_source.csv')),
        ('RK21 independent recovery verification',REPO/'audits/20261121/RK21/rk21_kudla_independent_verification_v1.json'),
        ('RK22 frozen fixed-protein protocol',REPO/'audits/20261121/RK22/a8_rk22_fixed_protein_protocol_v1.json'),
        ('RK22 fixed-protein analysis summary',REPO/'audits/20261121/RK22/rk22_analysis_summary_v1.json'),
        ('RK22 independent fixed-protein verification',REPO/'audits/20261121/RK22/rk22_independent_verification_v1.json'),
        ('RK22 manuscript section',section_path),
        ('RK22 manuscript prepare check',AUDIT/'prepare_check.json'),
        ('RK22 manuscript draft check',AUDIT/'draft_check.json'),
        ('RK22 manuscript writing status',AUDIT/'status.json'),
    ]
    rows=[f'| {name} | `{sha(path)}` |' for name,path in evidence_paths]
    block='\n'.join(rows)
    tail='\n\nA7 is retained as the prior manuscript snapshot.'
    if text.count(tail)!=1: raise SystemExit('evidence-table tail is not unique')
    text=text.replace(tail,'\n'+block+tail,1)
    BACKUP.parent.mkdir(parents=True,exist_ok=True)
    BACKUP.write_bytes(source)
    PAPER.write_text(text)
    report={
        'schema':'a8-rk22-paper-update-v1','status':'PASS_PENDING_INDEPENDENT_VERIFICATION',
        'before_sha256':before,'after_sha256':sha(PAPER),'backup':str(BACKUP),
        'section_sha256':sha(section_path),'old_data_availability_paragraph':OLD,'new_data_availability_paragraph':NEW,
        'section_body':body,'evidence_block':block,
        'evidence':[{'name':name,'path':str(path),'sha256':sha(path)} for name,path in evidence_paths],
        'scientific_flags':{'protein_ood':False,'functional_untouched_evaluated':False,'rk_g1_pass':False,'expensive_generation_authorized':False,'submittable':False}
    }
    (AUDIT/'rk22_paper_update_v1.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'status':report['status'],'before_sha256':before,'after_sha256':report['after_sha256'],'evidence_rows':len(rows)},indent=2))
if __name__=='__main__': main()
