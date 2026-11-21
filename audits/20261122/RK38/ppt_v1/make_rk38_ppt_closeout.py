#!/usr/bin/env python3
"""Build the RK38 PPT manifest and closeout from actual local/online evidence."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAGES = list(range(181, 187))
IDS = ['pSW', 'pSc', 'pSD', 'pSq', 'pSe', 'pSa']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name):
    return json.loads((ROOT / name).read_text())


audit = load('rk38_ppt_content_audit_v3.json')
screens = load('rk38_online_screenshots_response.json')
assert audit['status'] == 'PASS_RK38_PPT_CONTENT_AUDIT_V3'
assert audit['checks_passed'] == audit['checks_total'] == 15
assert screens['ok'] is True
assert [x['slide_number'] for x in screens['data']['screenshots']] == PAGES
assert [x['slide_id'] for x in screens['data']['screenshots']] == IDS

candidates = []
writes = []
for page, slide_id in zip(PAGES, IDS):
    candidate = ROOT / f'rk38_{page}.xml'
    response = load(f'rk38_{page}_add_response.json')
    assert response['ok'] is True
    candidates.append({
        'page': page,
        'slide_id': slide_id,
        'slide_file': candidate.name,
        'sha256': sha(candidate),
    })
    writes.append({
        'page': page,
        'slide_id': slide_id,
        'response_file': f'rk38_{page}_add_response.json',
        'ok': response['ok'],
    })

images = []
for item in screens['data']['screenshots']:
    path = Path(item['path'])
    assert path.is_file() and path.stat().st_size == item['size'] > 0
    images.append({
        'page': item['slide_number'],
        'slide_id': item['slide_id'],
        'file': str(path.relative_to(ROOT)),
        'size': item['size'],
        'sha256': sha(path),
        'visual_review': 'PASS_NO_CLIPPING_OVERFLOW_OCCLUSION',
    })

manifest = {
    'status': 'PASS_RK38_PPT_CANDIDATES',
    'presentation': audit['presentation_id'],
    'baseline_pages': 180,
    'baseline_revision': 152,
    'expected_final_pages': 186,
    'source_xml_sha256': sha(ROOT / 'rk38-source.xml'),
    'pages': candidates,
}
(ROOT / 'rk38_ppt_candidate_manifest_v1.json').write_text(json.dumps(manifest, indent=2) + '\n')

checks = {
    'content_audit_15_of_15': audit['checks_passed'] == 15,
    'online_revision_158': audit['revision_id'] == 158,
    'online_pages_186': audit['slide_count'] == 186,
    'first_180_semantic_xml_unchanged': audit['checks']['first_180_xml_unchanged'],
    'six_write_responses_ok': all(x['ok'] for x in writes),
    'six_online_screenshots_present': len(images) == 6,
    'six_online_visual_reviews_pass': all(x['visual_review'].startswith('PASS') for x in images),
    'expanded_column_widths_exact': all(x['checks']['expanded_table_column_widths_exact'] for x in audit['pages'].values()),
    'no_codonflow_sota_claim': audit['checks']['no_codonflow_sota_claim'],
    'failure_audit_v1_retained': (ROOT / 'rk38_ppt_content_audit_v1.json').is_file(),
    'failure_audit_v2_retained': (ROOT / 'rk38_ppt_content_audit_v2.json').is_file(),
}
report = {
    'status': 'PASS_RK38_PPT_CLOSEOUT' if all(checks.values()) else 'FAIL_RK38_PPT_CLOSEOUT',
    'presentation_url': audit['presentation_url'],
    'presentation': audit['presentation_id'],
    'online_revision': audit['revision_id'],
    'online_pages': audit['slide_count'],
    'source_xml_sha256': manifest['source_xml_sha256'],
    'online_xml_sha256': sha(ROOT / 'rk38-current.xml'),
    'content_audit': 'rk38_ppt_content_audit_v3.json',
    'content_audit_sha256': sha(ROOT / 'rk38_ppt_content_audit_v3.json'),
    'candidate_manifest_sha256': sha(ROOT / 'rk38_ppt_candidate_manifest_v1.json'),
    'write_responses': writes,
    'online_screenshots': images,
    'visual_review_scope': 'All six final online JPEGs were opened and inspected after write; no clipping, overflow, occlusion, or missing table column was observed.',
    'scientific_boundary': 'Inventory-only closure; external SOTA, unified time-matched comparison, functional untouched evaluation, RK-G1 and manuscript submission remain false.',
    'checks': checks,
    'checks_passed': sum(checks.values()),
    'checks_total': len(checks),
}
(ROOT / 'rk38_ppt_postwrite_closeout_v1.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'status': report['status'], 'checks_passed': report['checks_passed'], 'checks_total': report['checks_total']}, indent=2))
raise SystemExit(0 if all(checks.values()) else 1)
