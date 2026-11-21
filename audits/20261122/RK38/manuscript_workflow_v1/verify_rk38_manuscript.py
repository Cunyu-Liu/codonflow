#!/usr/bin/env python3
import hashlib
import json
import subprocess
from pathlib import Path

REPO = Path('/home/codonflow-a8-rk')
AUDIT = REPO / 'audits/20261122/RK38'
WORKFLOW = AUDIT / 'manuscript_workflow_v1'
BASELINE_REF = '83469e5b1f87f467827ecd5a09483d8f2ccc205d'
MANUSCRIPT_REL = 'paper/CodonFlow_preprint_A8.md'

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

after_bytes = (REPO / MANUSCRIPT_REL).read_bytes()
after = after_bytes.decode('utf-8')
section_bytes = (AUDIT / 'rk38_manuscript_section_v1.md').read_bytes()
section = section_bytes.decode('utf-8').rstrip('\n') + '\n'
before_bytes = subprocess.check_output(
    ['git', 'show', f'{BASELINE_REF}:{MANUSCRIPT_REL}'], cwd=REPO
)
before = before_bytes.decode('utf-8')
insert = section + '\n'
restored = after.replace(insert, '', 1) if after.count(insert) == 1 else ''
prepare = json.loads((WORKFLOW / 'prepare_check.json').read_text())
draft = json.loads((WORKFLOW / 'draft_check.json').read_text())
deliver_status_log = (WORKFLOW / 'status.log').read_text()
deliver = json.loads(deliver_status_log)
checks = {
    'section_exactly_once': after.count(section) == 1,
    'section_6_49_once': after.count('### 6.49 ') == 1,
    'table_30_once': after.count('**Table 30**') == 1,
    'table_31_once': after.count('**Table 31**') == 1,
    'discussion_after_section': after.find('## 7. Discussion') > after.find('### 6.49 '),
    'baseline_restored_exactly': restored == before,
    'workflow_prepare_pass': prepare.get('status') == 'pass',
    'workflow_write_pass': draft.get('status') == 'pass',
    'workflow_deliver_pass': deliver.get('status') == 'PASS' and deliver.get('stage') == 'deliver',
    'coverage_846_present': 'reconciled 846 record-seed-method cells' in section,
    'external_126_present': 'all 126 record-method cells matched' in section,
    'descriptive_hv_bounded': 'descriptively highest mean normalized hypervolume' in section and 'not dense-budget areas under the curve' in section,
    'untouched_not_evaluated': 'untouched outcomes and new file-content hashes were not read' in section,
    'rk20_2_of_8_present': 'passed only 2/8 sequence-OOD comparisons' in section,
    'independent_1851_present': section.count('1851/1851') >= 2,
    'closeout_9_present': 'Closeout passed 9/9 checks' in section,
    'tests_472_present': '472 passed, 1 skipped, and 5 subtests passed' in section,
    'scientific_gates_false': 'External SOTA, a complete time-matched seven-method comparison, functional-untouched confirmation, RK-G1, and manuscript submittability remain false.' in section,
    'evidence_anchor_once': after.count('{.evidence-anchor #sec-6-49}') == 1,
}
integration = {
    'status': 'PASS_RK38_MANUSCRIPT_INTEGRATION' if restored == before else 'FAIL_RK38_MANUSCRIPT_INTEGRATION',
    'baseline_ref': BASELINE_REF,
    'before_sha256': sha(before_bytes),
    'after_sha256': sha(after_bytes),
    'before_lines': len(before.splitlines()),
    'after_lines': len(after.splitlines()),
    'section_sha256': sha(section_bytes),
}
(AUDIT / 'rk38_manuscript_integration_v1.json').write_text(json.dumps(integration, indent=2) + '\n')
audit = {
    'status': 'PASS_RK38_MANUSCRIPT_AUDIT' if all(checks.values()) else 'FAIL_RK38_MANUSCRIPT_AUDIT',
    'checks_passed': sum(checks.values()),
    'checks_total': len(checks),
    'checks': checks,
    'manuscript_sha256': sha(after_bytes),
    'restored_baseline_sha256': sha(before_bytes),
    'section_sha256': sha(section_bytes),
    'manuscript_lines': len(after.splitlines()),
}
(AUDIT / 'rk38_manuscript_audit_v1.json').write_text(json.dumps(audit, indent=2) + '\n')
print(json.dumps(audit, indent=2))
if not all(checks.values()):
    raise SystemExit(1)
