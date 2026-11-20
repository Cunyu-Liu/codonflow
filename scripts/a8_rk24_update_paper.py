#!/usr/bin/env python3
"""Bind the independently accepted RK24 author baseline to the working manuscript."""
from pathlib import Path
import hashlib
import json

REPO = Path('/home/codonflow-a8-rk')
AUDIT = REPO / 'audits/20261121/RK24/paper'
PAPER = REPO / 'paper/CodonFlow_preprint_A8.md'
BACKUP = Path('/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk24/paper_v1/CodonFlow_preprint_A8.before_rk24.md')
EXPECTED_BEFORE = '168042d268da301057d9214393c25c05904c6a64d60bbb88ff265fc2cf8755b6'
EXPECTED_SECTION = 'f23926a336ecc1502e622e228a3cbf7b04577cb757c63e5695afb69a1505a2bd'
TEAMS = Path('/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk24')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    source = PAPER.read_bytes()
    before = hashlib.sha256(source).hexdigest()
    if before != EXPECTED_BEFORE:
        raise SystemExit(f'unexpected manuscript state: {before}')
    text = source.decode()
    if '### 6.35 ' in text:
        raise SystemExit('RK24 section already exists')
    section_path = AUDIT / 'rk24_manuscript_section.md'
    section = section_path.read_text()
    if sha(section_path) != EXPECTED_SECTION:
        raise SystemExit('unexpected RK24 section hash')
    heading = '### 6.35 The train-only Boël author model established a stronger protein-OOD baseline\n'
    if not section.startswith(heading):
        raise SystemExit('unexpected section heading')
    marker = '## 7. Discussion'
    if text.count(marker) != 1:
        raise SystemExit('discussion marker is not unique')
    text = text.replace(marker, section + '\n' + marker, 1)
    evidence_paths = [
        ('RK24 frozen author-model protocol', REPO / 'audits/20261121/RK24/a8_rk24_boel_author_protocol_v1.json'),
        ('RK24 reconstructed static features', TEAMS / 'author_features_v1/boel_author_static_features.csv.gz'),
        ('RK24 frozen train-only model artifact', TEAMS / 'author_train_refit_v1/dev/rk24_models.pkl'),
        ('RK24 development result', REPO / 'audits/20261121/RK24/rk24_dev_result_v1.json'),
        ('RK24 independent development verification', REPO / 'audits/20261121/RK24/rk24_dev_independent_verification_v1.json'),
        ('RK24 frozen test result', REPO / 'audits/20261121/RK24/rk24_test_result_v1.json'),
        ('RK24 test predictions', TEAMS / 'author_train_refit_v1/test/rk24_test_predictions.csv.gz'),
        ('RK24 test resampling', TEAMS / 'author_train_refit_v1/test/rk24_test_resampling_test.npz'),
        ('RK24 independent test verification', REPO / 'audits/20261121/RK24/rk24_test_independent_verification_v1.json'),
        ('RK24 development HistGB comparator', REPO / 'audits/20261121/RK24/rk24_dev_histgb_comparator_v1.json'),
        ('RK24 test HistGB comparator', REPO / 'audits/20261121/RK24/rk24_test_histgb_comparator_v1.json'),
        ('RK24 scientific closeout', REPO / 'audits/20261121/RK24/A8_RK24_BOEL_AUTHOR_CLOSEOUT.md'),
        ('RK24 manuscript section', section_path),
        ('RK24 manuscript prepare check', AUDIT / 'prepare_check.json'),
        ('RK24 manuscript draft check', AUDIT / 'draft_check.json'),
        ('RK24 manuscript writing status', AUDIT / 'status.json'),
    ]
    rows = [f'| {name} | `{sha(path)}` |' for name, path in evidence_paths]
    block = '\n'.join(rows)
    tail = '\n\nA7 is retained as the prior manuscript snapshot.'
    if text.count(tail) != 1:
        raise SystemExit('evidence-table tail is not unique')
    text = text.replace(tail, '\n' + block + tail, 1)
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    if BACKUP.exists():
        raise SystemExit(f'backup already exists: {BACKUP}')
    BACKUP.write_bytes(source)
    PAPER.write_text(text)
    report = {
        'schema': 'a8-rk24-paper-update-v1',
        'status': 'PASS_PENDING_INDEPENDENT_VERIFICATION',
        'before_sha256': before,
        'after_sha256': sha(PAPER),
        'backup': str(BACKUP),
        'section_sha256': sha(section_path),
        'section_body': section,
        'evidence_block': block,
        'evidence': [{'name': name, 'path': str(path), 'sha256': sha(path)} for name, path in evidence_paths],
        'scientific_flags': {
            'author_structure_superiority_supported_limited_scope': True,
            'codonflow_rk_superiority_supported': False,
            'fixed_protein_synonymous_mechanism_supported': False,
            'functional_untouched_evaluated': False,
            'rk_g1_pass': False,
            'expensive_generation_authorized': False,
            'submittable': False,
        },
    }
    (AUDIT / 'rk24_paper_update_v1.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': report['status'], 'before_sha256': before, 'after_sha256': report['after_sha256'], 'evidence_rows': len(rows)}, indent=2))


if __name__ == '__main__':
    main()
