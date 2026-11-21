#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
EXPECTED_IDS = ['pSW', 'pSc', 'pSD', 'pSq', 'pSe', 'pSa']
EXPECTED = {
    181: ['846 cells', '126 / 126', '1851 / 1851', 'PASS_INVENTORY_ONLY_SCIENTIFIC_GATES_UNRESOLVED'],
    182: ['846', '108,000', '792', 'Cost-resolved overlap with A7', 'Inventory only; not a ranking'],
    183: ['29.97288749', '5,471', '0', 'Descriptive HV leadership is not an external SOTA verdict', 'no time match'],
    184: ['19,072', '13,569', '362 rows', 'functional_untouched_evaluated = false'],
    185: ['1851 / 1851', '9 / 9', '472 passed', 'dfc7cc69', '19 / 19 PASS'],
    186: ['EXTERNAL SOTA', 'false / false', 'non-submittable working-draft status', 'not another inventory or a claim upgrade'],
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def slides(path):
    root = ET.parse(path).getroot()
    ns = {'s': root.tag.split('}')[0].strip('{')}
    return root, root.findall('s:slide', ns)

def texts(slide):
    return [''.join(p.itertext()) for p in slide.iter() if p.tag.split('}')[-1] == 'p']

def tags(slide):
    result = {}
    structural = {'slide', 'data', 'shape', 'table', 'colgroup', 'tr', 'td', 'note'}
    for element in slide.iter():
        tag = element.tag.split('}')[-1]
        if tag in structural:
            result[tag] = result.get(tag, 0) + 1
    return result

def shape_geometry(slide):
    keys = ('type', 'topLeftX', 'topLeftY', 'width', 'height', 'presetHandlers')
    return [tuple(element.get(k) for k in keys) for element in slide.iter()
            if element.tag.split('}')[-1] in {'shape', 'table'}]

def column_widths(slide):
    widths = []
    for element in slide.iter():
        if element.tag.split('}')[-1] == 'col':
            widths.extend([element.get('width')] * int(element.get('span', '1')))
    return widths

source_root, source = slides(ROOT / 'rk38-source.xml')
current_root, current = slides(ROOT / 'rk38-current.xml')
response = json.loads((ROOT / 'rk38-current-response.json').read_text())
checks = {
    'readback_ok': response.get('ok') is True,
    'revision_158': response.get('data', {}).get('revision_id') == 158,
    'slide_count_186': len(current) == 186,
    'source_count_180': len(source) == 180,
    'new_slide_ids_exact_order': [s.get('id') for s in current[180:]] == EXPECTED_IDS,
    'canvas_960_540': current_root.get('width') == '960' and current_root.get('height') == '540',
}
old_differences = []
for index, (before, after) in enumerate(zip(source, current[:180]), start=1):
    before.tail = None
    after.tail = None
    if ET.tostring(before) != ET.tostring(after):
        old_differences.append(index)
checks['first_180_xml_unchanged'] = not old_differences
page_results = {}
for offset, number in enumerate(range(181, 187), start=180):
    local = ET.parse(ROOT / f'rk38_{number}.xml').getroot()
    online = current[offset]
    online_text = '\n'.join(texts(online))
    local_texts = texts(local)
    online_texts = texts(online)
    geometry_ok = True
    for element in local.iter():
        if element.tag.split('}')[-1] not in {'shape', 'table', 'img', 'icon', 'embed'}:
            continue
        try:
            x = float(element.get('topLeftX'))
            y = float(element.get('topLeftY'))
            w = float(element.get('width'))
            h = float(element.get('height'))
        except (TypeError, ValueError):
            continue
        geometry_ok = geometry_ok and x >= 0 and y >= 0 and x + w <= 960 and y + h <= 540
    page_checks = {
        'text_exact': local_texts == online_texts,
        'structure_counts_exact': tags(local) == tags(online),
        'shape_and_table_geometry_exact': shape_geometry(local) == shape_geometry(online),
        'expanded_table_column_widths_exact': column_widths(local) == column_widths(online),
        'expected_facts_present': all(value in online_text for value in EXPECTED[number]),
        'four_note_sentences': len([p for p in online.iter() if p.tag.split('}')[-1] == 'note' for p in p.iter() if p.tag.split('}')[-1] == 'p']) == 4,
        'no_undefined': not any(e.tag.split('}')[-1] == 'undefined' for e in online.iter()),
        'local_geometry_within_canvas': geometry_ok,
        'preview_exists': (ROOT / f'previews/rk38_{number}_preview.png').stat().st_size > 10000,
    }
    page_results[str(number)] = {
        'slide_id': online.get('id'),
        'checks': page_checks,
        'pass': all(page_checks.values()),
        'text_paragraphs': len(online_texts),
        'sha256_local_xml': sha(ROOT / f'rk38_{number}.xml'),
    }
    checks[f'page_{number}_pass'] = all(page_checks.values())
checks['rk38_label_exactly_six_pages'] = sum('A8 / RK38 / BASELINE + UNTOUCHED' in '\n'.join(texts(s)) for s in current) == 6
checks['no_codonflow_sota_claim'] = all('CodonFlow achieves external SOTA' not in '\n'.join(texts(s)) for s in current)
report = {
    'status': 'PASS_RK38_PPT_CONTENT_AUDIT_V3' if all(checks.values()) else 'FAIL_RK38_PPT_CONTENT_AUDIT_V3',
    'normalization': 'Ignore slide-root pagination tails, server-added empty content on non-text shapes, and col-span coalescing; require exact text, structural counts, geometry, and expanded column widths.',
    'presentation_url': 'https://sii-czxy.feishu.cn/slides/WB1KsYGualerMUddEzMcCw1En0g',
    'presentation_id': 'WB1KsYGualerMUddEzMcCw1En0g',
    'revision_id': response.get('data', {}).get('revision_id'),
    'slide_count': len(current),
    'new_slide_ids': EXPECTED_IDS,
    'checks_passed': sum(checks.values()),
    'checks_total': len(checks),
    'checks': checks,
    'old_slide_differences': old_differences,
    'pages': page_results,
    'source_xml_sha256': sha(ROOT / 'rk38-source.xml'),
    'current_xml_sha256': sha(ROOT / 'rk38-current.xml'),
}
(ROOT / 'rk38_ppt_content_audit_v3.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: report[k] for k in ['status', 'checks_passed', 'checks_total', 'old_slide_differences', 'new_slide_ids']}, indent=2))
if not all(checks.values()):
    raise SystemExit(1)
