#!/usr/bin/env python3
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local(tag):
    return tag.rsplit('}', 1)[-1]


def slides(root):
    return [x for x in list(root) if local(x.tag) == 'slide']


def signature(el):
    return [local(el.tag), sorted(el.attrib.items()), (el.text or '').strip(), [signature(c) for c in list(el)]]


def deck_signature(items):
    return hashlib.sha256(json.dumps([signature(x) for x in items], ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def texts(el, note=False):
    out = []
    for node in el.iter():
        if local(node.tag) == 'p':
            ancestors_note = False
            # ElementTree has no parent pointer; partition below instead.
            out.append(''.join(node.itertext()))
    return out


def visible_texts(slide):
    data = next((x for x in list(slide) if local(x.tag) == 'data'), None)
    return [] if data is None else [''.join(n.itertext()) for n in data.iter() if local(n.tag) == 'p']


def note_texts(slide):
    note = next((x for x in list(slide) if local(x.tag) == 'note'), None)
    return [] if note is None else [''.join(n.itertext()) for n in note.iter() if local(n.tag) == 'p']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--candidate', required=True)
    ap.add_argument('--result', required=True)
    ap.add_argument('--independent', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--baseline')
    ap.add_argument('--current')
    ap.add_argument('--expected-slide-id')
    a = ap.parse_args()
    result = json.loads(Path(a.result).read_text())
    independent = json.loads(Path(a.independent).read_text())
    candidate = ET.parse(a.candidate).getroot()
    checks = []
    def check(name, ok, details=None):
        checks.append({'name': name, 'pass': bool(ok), 'details': details})

    visible = visible_texts(candidate)
    notes = note_texts(candidate)
    all_text = '\n'.join(visible + notes)
    check('candidate_root_slide', local(candidate.tag) == 'slide', candidate.tag)
    check('five_note_paragraphs', len(notes) == 5, len(notes))
    check('no_undefined_or_embed', not any(local(n.tag) in {'undefined', 'embed'} for n in candidate.iter()))
    check('no_emoji_or_external_images', not any(local(n.tag) == 'img' and n.attrib.get('src', '').startswith('http') for n in candidate.iter()))
    check('independent_47', independent['status'] == 'PASS' and independent['n_passed'] == 47, independent['n_passed'])
    check('four_primary_endpoints', len(result['primary_tests']) == 4 and result['sequence_cluster_ood_mfe_increment_pass'], result['scientific_conclusion'])
    check('fixed_protein_boundaries', result['scientific_flags']['fixed_protein'] and result['scientific_flags']['sequence_cluster_ood'] and not result['scientific_flags']['protein_ood'] and not result['scientific_flags']['velocity_or_decay_measured'] and not result['scientific_flags']['RK_G1_complete'] and not result['scientific_flags']['generator_training_authorized'], result['scientific_flags'])

    effect_by_test = {x['test']: x for x in result['primary_tests']}
    for test_name, record in effect_by_test.items():
        effect = f"+{record['observed_effect']:.5f}"
        ci = f"95% CI [{record['ci95'][0]:.5f}, {record['ci95'][1]:.5f}]"
        check(f'visible_{test_name}_effect', effect in visible, effect)
        check(f'visible_{test_name}_ci', ci in visible, ci)
        check(f'visible_{test_name}_seed_stability', record['positive_seeds'] == 10 and any('10/10 seeds' in x for x in visible), record['positive_seeds'])
        check(f'note_{test_name}_exact', str(record['observed_effect']) in all_text and str(record['ci95'][0]) in all_text and str(record['ci95'][1]) in all_text and str(record['p_holm']) in all_text, test_name)
    absolute = {x['arm']: x for x in result['primary_absolute_performance']}
    for arm in ['ridge_simple', 'ridge_structure', 'ridge_mfe_only', 'histgb_simple', 'histgb_structure', 'histgb_mfe_only']:
        row = absolute[arm]
        spear = f"{row['spearman']:.5f}".replace('-', '−')
        mse = f"{row['mse']:.5f}"
        check(f'visible_{arm}_spearman', spear in visible, spear)
        check(f'visible_{arm}_mse', mse in visible, mse)
    for token in ['150 exact CDS', '37 clusters', '300 real CPU fits', 'Independent 47/47', 'closeout 97/97', 'RK-G1 remains false; generator training is unauthorized.', '119 · RK27', '8a62836b', '95257f29']:
        check(f'required_visible_{token}', any(token in x for x in visible), token)
    for token in ['b601db3b0a5bec6b228492846f0058a0d959439c0eeebada05b749daa366ed5e', '1e657146110a553071b169578839cbd0c45e357d9d4ff32394f297848d2df5f4', '8a62836bb73b34bcae529bae6a21f6e3eefc85d1', '95257f290062d0f7d1ad2ab7bab21eef0b485437']:
        check(f'note_hash_or_commit_{token[:8]}', token in all_text, token)

    geometry_errors = []
    for node in candidate.iter():
        if local(node.tag) in {'shape', 'img', 'table', 'icon', 'embed'} and 'topLeftX' in node.attrib:
            x, y = float(node.attrib['topLeftX']), float(node.attrib['topLeftY'])
            w, h = float(node.attrib['width']), float(node.attrib['height'])
            if x < 0 or y < 0 or x + w > 960 or y + h > 540:
                geometry_errors.append({'tag': local(node.tag), 'bbox': [x, y, w, h]})
    check('all_elements_inside_960_by_540', not geometry_errors, geometry_errors)
    table_checks = []
    for table in [n for n in candidate.iter() if local(n.tag) == 'table']:
        cols = next((c for c in list(table) if local(c.tag) == 'colgroup'), None)
        col_width = sum(float(c.attrib['width']) for c in list(cols) if local(c.tag) == 'col') if cols is not None else 0
        rows = [c for c in list(table) if local(c.tag) == 'tr']
        row_height = sum(float(r.attrib['height']) for r in rows)
        table_checks.append({'columns': col_width, 'target_width': float(table.attrib['width']), 'rows': row_height, 'target_height': float(table.attrib['height']), 'n_rows': len(rows)})
    check('table_dimensions_reconcile', all(abs(x['columns'] - x['target_width']) < 1e-9 and abs(x['rows'] - x['target_height']) < 1e-9 and x['n_rows'] == 7 for x in table_checks), table_checks)

    if a.baseline or a.current:
        if not (a.baseline and a.current and a.expected_slide_id):
            raise SystemExit('post mode requires baseline, current and expected-slide-id')
        baseline_root = ET.parse(a.baseline).getroot()
        current_root = ET.parse(a.current).getroot()
        old = slides(baseline_root)
        new = slides(current_root)
        check('post_page_count_119', len(old) == 118 and len(new) == 119, {'before': len(old), 'after': len(new)})
        check('post_old_118_semantically_unchanged', deck_signature(old) == deck_signature(new[:118]), {'before': deck_signature(old), 'after_first_118': deck_signature(new[:118])})
        check('post_new_slide_is_last_and_expected', new[-1].attrib.get('id') == a.expected_slide_id, new[-1].attrib.get('id'))
        check('post_canvas_unchanged', baseline_root.attrib.get('width') == current_root.attrib.get('width') == '960' and baseline_root.attrib.get('height') == current_root.attrib.get('height') == '540', current_root.attrib)
        check('post_visible_text_exact', visible_texts(new[-1]) == visible, {'candidate': len(visible), 'online': len(visible_texts(new[-1]))})
        check('post_notes_exact', note_texts(new[-1]) == notes, {'candidate': len(notes), 'online': len(note_texts(new[-1]))})
        check('post_RK26_last_old_page_preserved', new[117].attrib.get('id') == 'pZL', new[117].attrib.get('id'))

    report = {
        'schema': 'a8-rk27-ppt-verification-v1',
        'mode': 'post' if a.current else 'pre',
        'status': 'PASS' if all(x['pass'] for x in checks) else 'FAIL',
        'n_checks': len(checks),
        'n_passed': sum(x['pass'] for x in checks),
        'candidate_sha256': sha(a.candidate),
        'result_sha256': sha(a.result),
        'independent_sha256': sha(a.independent),
        'checks': checks,
    }
    if a.baseline:
        report['baseline_sha256'] = sha(a.baseline)
    if a.current:
        report['current_sha256'] = sha(a.current)
        report['slide_id'] = a.expected_slide_id
    Path(a.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'n_checks': len(checks), 'n_passed': report['n_passed'], 'failed': [x for x in checks if not x['pass']]}, ensure_ascii=False, indent=2))
    if report['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
