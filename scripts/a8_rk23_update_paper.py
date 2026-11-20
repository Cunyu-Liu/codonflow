#!/usr/bin/env python3
"""Bind the accepted RK23 protein-OOD result to the working manuscript."""
from pathlib import Path
import hashlib
import json

REPO = Path('/home/codonflow-a8-rk')
AUDIT = REPO / 'audits/20261121/RK23/paper'
PAPER = REPO / 'paper/CodonFlow_preprint_A8.md'
BACKUP = Path('/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk23/paper_v1/CodonFlow_preprint_A8.before_rk23.md')
EXPECTED_BEFORE = '5c9f9619a46ed555777f6bc9e986fc873c7ff5674406d93c19d21979155096b6'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    source = PAPER.read_bytes()
    before = hashlib.sha256(source).hexdigest()
    if before != EXPECTED_BEFORE:
        raise SystemExit(f'unexpected manuscript state: {before}')
    text = source.decode()
    if '### 6.34 ' in text:
        raise SystemExit('RK23 section already exists')
    section_path = AUDIT / 'rk23_manuscript_section.md'
    section = section_path.read_text()
    if not section.startswith('### 6.34 Boël initiation folding did not improve the frozen protein-OOD comparison\n'):
        raise SystemExit('unexpected section heading')
    marker = '## 7. Discussion'
    if text.count(marker) != 1:
        raise SystemExit('discussion marker is not unique')
    text = text.replace(marker, section + '\n' + marker, 1)
    evidence_paths = [
        ('RK23 frozen protein-OOD protocol', REPO / 'audits/20261121/RK23/a8_rk23_boel_uh_protocol_v1.json'),
        ('RK23 frozen development result', REPO / 'audits/20261121/RK23/rk23_dev_result_v1.json'),
        ('RK23 frozen test result', REPO / 'audits/20261121/RK23/rk23_test_result_v1.json'),
        ('RK23 independent development verification', REPO / 'audits/20261121/RK23/rk23_dev_independent_verification_v1.json'),
        ('RK23 independent test verification', REPO / 'audits/20261121/RK23/rk23_test_independent_verification_v1.json'),
        ('RK23 test predictions', Path('/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk23/protein_ood_v1/test/rk23_test_predictions.csv.gz')),
        ('RK23 test resampling', Path('/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk23/protein_ood_v1/test/rk23_test_resampling_test.npz')),
        ('RK23 scientific closeout', REPO / 'docs/handover/A8_RK23_BOEL_UH_CLOSEOUT.md'),
        ('RK23 manuscript section', section_path),
        ('RK23 manuscript prepare check', AUDIT / 'prepare_check.json'),
        ('RK23 manuscript draft check', AUDIT / 'draft_check.json'),
        ('RK23 manuscript writing status', AUDIT / 'status.json'),
    ]
    rows = [f'| {name} | `{sha(path)}` |' for name, path in evidence_paths]
    block = '\n'.join(rows)
    tail = '\n\nA7 is retained as the prior manuscript snapshot.'
    if text.count(tail) != 1:
        raise SystemExit('evidence-table tail is not unique')
    text = text.replace(tail, '\n' + block + tail, 1)
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    BACKUP.write_bytes(source)
    PAPER.write_text(text)
    report = {
        'schema': 'a8-rk23-paper-update-v1',
        'status': 'PASS_PENDING_INDEPENDENT_VERIFICATION',
        'before_sha256': before,
        'after_sha256': sha(PAPER),
        'backup': str(BACKUP),
        'section_sha256': sha(section_path),
        'section_body': section,
        'evidence_block': block,
        'evidence': [{'name': name, 'path': str(path), 'sha256': sha(path)} for name, path in evidence_paths],
        'scientific_flags': {
            'primary_protein_ood_increment_supported': False,
            'functional_untouched_evaluated': False,
            'rk_g1_pass': False,
            'expensive_generation_authorized': False,
            'submittable': False,
        },
    }
    (AUDIT / 'rk23_paper_update_v1.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': report['status'], 'before_sha256': before, 'after_sha256': report['after_sha256'], 'evidence_rows': len(rows)}, indent=2))


if __name__ == '__main__':
    main()
