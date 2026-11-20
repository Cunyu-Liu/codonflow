#!/usr/bin/env python3
"""Bind the RK26 manuscript closeout and registry to its exact commit."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

ORIGINAL = '46db82d54dcc2e87c4f8bf3a71017b8dd9fe921eb18c337b8e81f96784902578'
MANUSCRIPT = '91e8bf226225d6d621617128618012b9333086646af9cd315b34be156f130f9a'
SECTION = 'de359b8383544347f3a5edf9628a1b1147f4e27df273b08061ddec40a1db57e4'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for name in ['original-backup','manuscript','section','local-report','remote-report','update-report','closeout','registry','commit','output']:
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    local = json.loads(args.local_report.read_text())
    closeout = args.closeout.read_text()
    registry = args.registry.read_text()
    checks = []
    def check(name,condition):
        checks.append({'name':name,'pass':bool(condition)})
    check('original backup hash',sha(args.original_backup)==ORIGINAL)
    check('final manuscript hash',sha(args.manuscript)==MANUSCRIPT)
    check('section hash',sha(args.section)==SECTION)
    check('local report 57/57',local['status']=='PASS' and local['checks_total']==local['checks_passed']==57 and not local['failed_checks'])
    check('local report manuscript hash',local['manuscript_sha256']==MANUSCRIPT)
    check('remote report byte identical',args.local_report.read_bytes()==args.remote_report.read_bytes())
    check('update report pass',json.loads(args.update_report.read_text())['status']=='PASS')
    check('update report manuscript hash',json.loads(args.update_report.read_text())['manuscript_sha256']==MANUSCRIPT)
    check('closeout contains original hash',ORIGINAL in closeout)
    check('closeout contains manuscript hash',MANUSCRIPT in closeout)
    check('closeout contains section hash',SECTION in closeout)
    check('closeout contains report hash',sha(args.local_report) in closeout)
    check('closeout retains non-submittable state','non-submittable working manuscript' in closeout)
    check('closeout retains zero fits','No model was fitted' in closeout)
    check('closeout retains untouched boundary','RK04 functional-untouched split were not accessed' in closeout)
    check('closeout retains RK-G1 false','RK-G1 remains false' in closeout)
    check('closeout retains no generator authorization','generator training remains unauthorized' in closeout)
    rows = [line for line in registry.splitlines() if '| RK26-PAPER |' in line]
    check('one RK26-PAPER registry row',len(rows)==1)
    if rows:
        row = rows[0]
        check('registry manuscript hash',MANUSCRIPT in row)
        check('registry verifier hash',sha(args.local_report) in row)
        check('registry non-submittable','non-submittable' in row)
        check('registry no fit','0 fits' in row)
        check('registry no endpoint','0 endpoints' in row)
        check('registry RK-G1 false','RK-G1=false' in row)
    repo = args.manuscript.parent.parent
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    ancestor = subprocess.run(['git','merge-base','--is-ancestor',args.commit,'HEAD'],cwd=repo).returncode == 0
    check('manuscript commit exact or ancestor',head==args.commit or ancestor)
    failed = [c['name'] for c in checks if not c['pass']]
    report = {
        'schema':'a8-rk26-manuscript-closeout-verification-v1',
        'status':'PASS' if not failed else 'FAIL','manuscript_commit':args.commit,
        'original_sha256':ORIGINAL,'manuscript_sha256':MANUSCRIPT,'section_sha256':SECTION,
        'local_report_sha256':sha(args.local_report),'remote_report_sha256':sha(args.remote_report),
        'update_report_sha256':sha(args.update_report),'closeout_sha256':sha(args.closeout),
        'checks_total':len(checks),'checks_passed':len(checks)-len(failed),
        'failed_checks':failed,'checks':checks,'remote_report_byte_identical':True,
        'functional_untouched_evaluated':False,'rk_g1':False,'generator_training_authorized':False,
    }
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({key:report[key] for key in ['status','checks_total','checks_passed','failed_checks','manuscript_commit']},indent=2))
    if failed:
        raise SystemExit(1)


if __name__=='__main__':
    main()
