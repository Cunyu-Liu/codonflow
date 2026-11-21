#!/usr/bin/env python3
"""Independently audit RK38 registry, task ledger and handoff against frozen evidence."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUD = ROOT / 'audits/20261122/RK38'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    handoff = (ROOT / 'docs/handover/HANDOFF_A8_RK38_20261122.md').read_text()
    registry = (ROOT / 'experiments/REGISTRY.md').read_text()
    tasks = (ROOT / 'tasks.md').read_text()
    production = json.loads((AUD / 'rk38_baseline_untouched_inventory_v1.json').read_text())
    independent = json.loads((AUD / 'rk38_baseline_untouched_inventory_independent_v2.json').read_text())
    clean = json.loads((AUD / 'rk38_clean_reproduction_closeout_v1.json').read_text())
    manuscript = json.loads((AUD / 'rk38_manuscript_audit_v1.json').read_text())
    ppt = json.loads((AUD / 'ppt_v1/rk38_ppt_content_audit_v3.json').read_text())
    ppt_close = json.loads((AUD / 'ppt_v1/rk38_ppt_postwrite_closeout_v1.json').read_text())
    paper = ROOT / 'paper/CodonFlow_preprint_A8.md'
    tests = (AUD / 'rk38_full_pytest.log').read_text()
    checks = {
        'registry_row_once': registry.count('| RK38 |') == 1,
        'tasks_section_once': tasks.count('## 2026-11-22：RK38') == 1,
        'handoff_inventory_only': 'PASS_INVENTORY_ONLY_SCIENTIFIC_GATES_UNRESOLVED' in handoff,
        'handoff_commit_chain': all(x in handoff for x in ('83469e5b', 'dfc7cc69', '0cb827ed')),
        'production_inventory_only': production.get('status') == 'PASS_INVENTORY_ONLY_SCIENTIFIC_GATES_UNRESOLVED',
        'production_846_cells': '846' in json.dumps(production),
        'production_126_cells': '126' in json.dumps(production),
        'independent_1851_pass': independent.get('n_pass') == independent.get('n_checks') == 1851 and independent.get('n_fail') == 0,
        'clean_9_pass': clean.get('n_pass') == clean.get('n_checks') == 9 and clean.get('n_fail') == 0,
        'project_tests_472': '472 passed' in tests and '1 skipped' in tests,
        'manuscript_19_pass': manuscript.get('checks_passed') == manuscript.get('checks_total') == 19,
        'paper_sha_exact': sha(paper) == '7660294a876314c5ed9b24d70e49c68be3199d995f24cf53be0246d47a600f61',
        'paper_2096_lines': len(paper.read_text().splitlines()) == 2096,
        'ppt_15_pass': ppt.get('checks_passed') == ppt.get('checks_total') == 15,
        'ppt_revision_158': ppt.get('revision_id') == 158 and ppt.get('slide_count') == 186,
        'ppt_closeout_11_pass': ppt_close.get('checks_passed') == ppt_close.get('checks_total') == 11,
        'ppt_visual_six_pass': len(ppt_close.get('online_screenshots', [])) == 6 and all(x['visual_review'].startswith('PASS') for x in ppt_close['online_screenshots']),
        'scientific_gates_open': all(x in handoff for x in ('external SOTA', 'time-matched', 'RK-G1', 'manuscript submittable')),
        'untouched_not_read': 'new_functional_labels_read=false' in handoff and 'functional_untouched_evaluated=false' in handoff,
        'generator_not_authorized': '昂贵生成训练未授权' in handoff,
        'large_artifacts_on_teams': '/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk38/' in handoff,
        'failure_audits_retained': all((AUD / f'ppt_v1/rk38_ppt_content_audit_{v}.json').is_file() for v in ('v1', 'v2')),
        'next_task_discriminating': 'RK39' in handoff and '不得再做同类资产盘点' in handoff,
    }
    report = {
        'status': 'PASS_RK38_DOCUMENTATION_CLOSEOUT' if all(checks.values()) else 'FAIL_RK38_DOCUMENTATION_CLOSEOUT',
        'checks': checks,
        'checks_passed': sum(checks.values()),
        'checks_total': len(checks),
        'evidence_sha256': {
            'production': sha(AUD / 'rk38_baseline_untouched_inventory_v1.json'),
            'independent_v2': sha(AUD / 'rk38_baseline_untouched_inventory_independent_v2.json'),
            'clean_closeout': sha(AUD / 'rk38_clean_reproduction_closeout_v1.json'),
            'manuscript': sha(paper),
            'ppt_content_v3': sha(AUD / 'ppt_v1/rk38_ppt_content_audit_v3.json'),
            'ppt_closeout': sha(AUD / 'ppt_v1/rk38_ppt_postwrite_closeout_v1.json'),
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': report['status'], 'checks_passed': report['checks_passed'], 'checks_total': report['checks_total']}, indent=2))
    raise SystemExit(0 if all(checks.values()) else 1)


if __name__ == '__main__':
    main()
