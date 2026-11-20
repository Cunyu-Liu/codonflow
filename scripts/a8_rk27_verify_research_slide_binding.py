#!/usr/bin/env python3
"""Bind the verified online RK27 slide to its scientific and readback evidence."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', type=Path, default=Path('/home/codonflow-a8-rk'))
    ap.add_argument('--report', type=Path, required=True)
    a = ap.parse_args()
    audit = a.repo / 'audits/20261121/RK27'
    manifest = json.loads((audit / 'rk27_research_slide_manifest_v1.json').read_text())
    pre = json.loads((audit / 'rk27_research_slide_preflight_v1.json').read_text())
    online = json.loads((audit / 'rk27_research_slide_online_verification_v1.json').read_text())
    add = json.loads((audit / 'rk27_research_slide_add_response_v1.json').read_text())
    readback = json.loads((audit / 'rk27_research_slide_readback_response_v1.json').read_text())
    closeout = json.loads((audit / 'rk27_closeout_verification_v1.json').read_text())
    checks = []
    def check(name, ok, details=None):
        checks.append({'name': name, 'pass': bool(ok), 'details': details})

    check('preflight_50', pre['status'] == 'PASS' and pre['n_checks'] == 50 and pre['n_passed'] == 50, pre['n_passed'])
    check('online_57', online['status'] == 'PASS' and online['n_checks'] == 57 and online['n_passed'] == 57, online['n_passed'])
    check('write_response', add['ok'] and add['data']['slide_id'] == 'pZy' and add['data']['revision_id'] == 82, add['data'])
    check('readback_response', readback['ok'] and readback['data']['revision_id'] == 82 and readback['data']['content_saved'], readback['data']['revision_id'])
    check('manifest_identity', manifest['slide_id'] == 'pZy' and manifest['slide_number'] == 119 and manifest['final_slide_count'] == 119 and manifest['final_revision_id'] == 82, manifest['slide_id'])
    check('old_deck_protection', manifest['baseline_slide_count'] == 118 and manifest['baseline_last_slide_id'] == 'pZL' and manifest['old_slides_unchanged'], manifest['old_slides_unchanged'])
    check('candidate_hash', sha(a.repo / manifest['candidate_xml']['path']) == manifest['candidate_xml']['sha256'] == pre['candidate_sha256'] == online['candidate_sha256'], manifest['candidate_xml']['sha256'])
    check('preflight_hash', sha(audit / 'rk27_research_slide_preflight_v1.json') == manifest['preflight_verification']['sha256'], manifest['preflight_verification']['sha256'])
    check('online_report_hash', sha(audit / 'rk27_research_slide_online_verification_v1.json') == manifest['online_verification']['sha256'], manifest['online_verification']['sha256'])
    for name, record in manifest['large_readback_artifacts'].items():
        path = Path(record['path'])
        check(f'{name}_exists_and_hash', path.exists() and sha(path) == record['sha256'], record)
        check(f'{name}_large_asset_location', str(path).startswith('/teams/HoulabData_1788502323/liucunyu/'), str(path))
    check('science_result_hash_binding', online['result_sha256'] == manifest['scientific_result_sha256'] == 'b601db3b0a5bec6b228492846f0058a0d959439c0eeebada05b749daa366ed5e', online['result_sha256'])
    check('independent_hash_binding', online['independent_sha256'] == manifest['independent_report_sha256'] == '1e657146110a553071b169578839cbd0c45e357d9d4ff32394f297848d2df5f4', online['independent_sha256'])
    check('science_closeout_97', closeout['status'] == 'PASS' and closeout['n_checks'] == 97 and closeout['n_passed'] == 97, closeout['n_passed'])
    for label, commit in [('science', manifest['science_commit']), ('closeout', manifest['closeout_commit'])]:
        rc = subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'HEAD'], cwd=a.repo).returncode
        check(f'{label}_commit_is_ancestor', rc == 0, commit)
    check('scope_and_global_gate', manifest['scientific_scope'] == 'retrospective fixed-GFP sequence-cluster OOD measured-MFE increment' and not manifest['RK_G1_complete'] and not manifest['generator_training_authorized'] and not manifest['functional_untouched_read'], manifest['scientific_scope'])

    replay_report = Path('/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk27/ppt/rk27_research_slide_online_verification_postbind_v1.json')
    command = [
        '/root/miniconda3/envs/codonflow/bin/python', str(a.repo / 'scripts/a8_rk27_verify_research_slide.py'),
        '--candidate', str(a.repo / 'audits/20261121/RK27/rk27_research_slide_v1.xml'),
        '--result', str(a.repo / 'audits/20261121/RK27/rk27_sequence_cluster_ood_result_v1.json'),
        '--independent', str(a.repo / 'audits/20261121/RK27/rk27_sequence_cluster_ood_independent_v1.json'),
        '--baseline', manifest['large_readback_artifacts']['baseline_xml']['path'],
        '--current', manifest['large_readback_artifacts']['current_xml']['path'],
        '--expected-slide-id', 'pZy', '--report', str(replay_report),
    ]
    run = subprocess.run(command, cwd=a.repo, capture_output=True, text=True)
    check('postbind_verifier_replay', run.returncode == 0 and replay_report.exists(), {'returncode': run.returncode, 'stderr': run.stderr[-1000:]})
    if replay_report.exists():
        replay = json.loads(replay_report.read_text())
        check('postbind_57_and_byte_identical', replay['status'] == 'PASS' and replay['n_passed'] == 57 and sha(replay_report) == sha(audit / 'rk27_research_slide_online_verification_v1.json'), replay['n_passed'])

    report = {
        'schema': 'a8-rk27-research-slide-binding-v1',
        'status': 'PASS' if all(x['pass'] for x in checks) else 'FAIL',
        'n_checks': len(checks),
        'n_passed': sum(x['pass'] for x in checks),
        'checks': checks,
        'manifest_sha256': sha(audit / 'rk27_research_slide_manifest_v1.json'),
        'slide_id': 'pZy',
        'slide_number': 119,
        'revision_id': 82,
        'RK_G1_complete': False,
        'generator_training_authorized': False,
    }
    a.report.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': report['status'], 'n_checks': len(checks), 'n_passed': report['n_passed'], 'failed': [x for x in checks if not x['pass']]}, indent=2))
    if report['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
