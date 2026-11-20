#!/usr/bin/env python3
"""Insertion-only RK26 manuscript update with exact source reconstruction."""
from pathlib import Path
import argparse
import hashlib
import json

ORIGINAL_SHA256 = '46db82d54dcc2e87c4f8bf3a71017b8dd9fe921eb18c337b8e81f96784902578'
HEADING = '### 6.37 Fixed-protein single-to-double synonymous OOD was not supported by MAGE pair coverage'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for name in ['original','section','result','independent','closeout','output','report']:
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    original = args.original.read_text()
    section = args.section.read_text()
    result = json.loads(args.result.read_text())
    independent = json.loads(args.independent.read_text())
    closeout = json.loads(args.closeout.read_text())
    assert sha(args.original) == ORIGINAL_SHA256
    assert section.startswith(HEADING+'\n')
    assert HEADING not in original
    assert '| RK26 ' not in original
    assert original.count('\n## 7. Discussion') == 1
    assert original.count('\nA7 is retained as the prior manuscript snapshot.') == 1
    assert result['scientific_outcome'] == 'FIXED_PROTEIN_SINGLE_TO_DOUBLE_SYNONYMOUS_OOD_NOT_SUPPORTED_BY_SAMPLE_COVERAGE'
    assert result['rows'] == 8192 and result['synonymous_single_variants'] == 6 and result['synonymous_double_variants'] == 4
    assert result['model_fits'] == result['functional_endpoint_evaluations'] == result['confidence_intervals_or_p_values'] == 0
    assert independent['status'] == 'PASS' and independent['checks_total'] == independent['checks_passed'] == 42
    assert closeout['status'] == 'PASS' and closeout['checks_total'] == closeout['checks_passed'] == 54
    assert closeout['production_result_sha256'] == sha(args.result)
    assert closeout['independent_report_sha256'] == sha(args.independent)
    evidence = {
        'RK26 frozen pair-feasibility protocol':result['protocol_sha256'],
        'RK26 raw MAGE pair source':result['source']['raw_sha256'],
        'RK26 clean MAGE pair source':result['source']['clean_sha256'],
        'RK26 sequence-only pair facts':result['artifacts']['pair_facts_csv_gz']['sha256'],
        'RK26 pair-feasibility result':sha(args.result),
        'RK26 independent pair-feasibility verification':sha(args.independent),
        'RK26 scientific closeout':closeout['closeout_sha256'],
        'RK26 closeout verification':sha(args.closeout),
        'RK26 manuscript section':sha(args.section),
    }
    manuscript = original.replace('\n## 7. Discussion','\n'+section.strip()+'\n\n## 7. Discussion',1)
    rows = ''.join(f'| {name} | `{digest}` |\n' for name,digest in evidence.items())
    manuscript = manuscript.replace('\nA7 is retained as the prior manuscript snapshot.',rows+'\nA7 is retained as the prior manuscript snapshot.',1)
    without_section = manuscript.replace('\n'+section.strip()+'\n\n## 7. Discussion','\n## 7. Discussion',1)
    ledger_rows = [line for line in without_section.splitlines() if line.startswith('| RK26 ')]
    recovered = '\n'.join(line for line in without_section.splitlines() if not line.startswith('| RK26 '))+'\n'
    assert len(ledger_rows) == len(evidence) == 9
    assert recovered == original
    assert manuscript.count(section.strip()) == 1
    assert manuscript.count(HEADING) == 1
    args.output.write_text(manuscript)
    report = {
        'schema':'a8-rk26-manuscript-update-v1','status':'PASS',
        'original_sha256':sha(args.original),'section_sha256':sha(args.section),
        'manuscript_sha256':sha(args.output),'result_sha256':sha(args.result),
        'independent_sha256':sha(args.independent),'closeout_sha256':sha(args.closeout),
        'inserted_heading':HEADING,'evidence_rows':evidence,'evidence_row_count':len(ledger_rows),
        'old_manuscript_reconstruction_exact':True,'insertion_only':True,
        'functional_untouched_evaluated':False,'rk_g1':False,'generator_training_authorized':False,
    }
    args.report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({key:report[key] for key in ['status','manuscript_sha256','section_sha256','evidence_row_count','old_manuscript_reconstruction_exact']},indent=2))


if __name__=='__main__':
    main()
