#!/usr/bin/env python3
"""Evidence-bound RK24 slide candidate and post-write verification."""
import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def local(tag):
    return tag.rsplit('}', 1)[-1]


def children(el, name):
    return [x for x in list(el) if local(x.tag) == name]


def child(el, name):
    found = children(el, name)
    return found[0] if found else None


def slide_list(root):
    return [root] if local(root.tag) == 'slide' else children(root, 'slide')


def paragraphs(el):
    return [''.join(p.itertext()) for p in el.iter() if local(p.tag) == 'p'] if el is not None else []


def slide_text(slide):
    return '\n'.join(paragraphs(child(slide, 'data')))


def note_text(slide):
    return '\n'.join(paragraphs(child(slide, 'note')))


def semantic(el):
    attrs = tuple(sorted((k, v) for k, v in el.attrib.items() if k != 'id' and not (local(el.tag) == 'col' and k == 'span')))
    if local(el.tag) == 'colgroup':
        merged = []
        for item in list(el):
            span = int(item.attrib.get('span', '1'))
            base = semantic(item)
            if merged and merged[-1][0] == base:
                merged[-1] = (base, merged[-1][1] + span)
            else:
                merged.append((base, span))
        return (local(el.tag), attrs, (el.text or '').strip(), tuple(merged))
    return (local(el.tag), attrs, (el.text or '').strip(), tuple(semantic(x) for x in list(el)))


def add(checks, name, condition, detail=None):
    checks.append({'name': name, 'pass': bool(condition), 'detail': detail})


def verify_slide(slide, result, verification, comparator, test_commit, closeout_commit, checks, prefix):
    text = slide_text(slide)
    notes = note_text(slide)
    test = result['split_results']['test']
    metrics = test['metrics']
    comps = test['primary_inference']['comparisons']
    add(checks, prefix + '_independent_status', verification['status'] == 'PASS_INDEPENDENT_VERIFICATION')
    add(checks, prefix + '_independent_153', verification['checks_total'] == verification['checks_passed'] == 153 and not verification['checks_failed'])
    for key in ('max_static_feature_difference', 'max_prediction_difference', 'max_metric_difference', 'max_bootstrap_difference', 'max_permutation_difference'):
        add(checks, prefix + '_' + key, verification[key] < 1e-8 and str(verification[key]) in notes)
    add(checks, prefix + '_primary_gate_positive', verification['scientific_gate']['all_four_pass'] is True and verification['scientific_gate']['rk_g1'] is False)
    add(checks, prefix + '_test_n', test['n'] == 634 and '634 test constructs' in text)
    add(checks, prefix + '_multiclass_clusters', test['primary_inference']['multiclass_clusters'] == 556 and '556 protein clusters' in text)
    add(checks, prefix + '_binary_clusters', test['primary_inference']['binary_clusters'] == 364 and str(test['primary_inference']['binary_clusters']) in notes)
    add(checks, prefix + '_resampling', test['primary_inference']['bootstrap_replicates'] == 20000 and test['primary_inference']['permutation_replicates'] == 20000 and '20,000 bootstrap + 20,000 permutations' in text)
    scalar_metrics = (
        ('base_auc', metrics['binary']['base']['auc']),
        ('author_auc', metrics['binary']['author']['auc']),
        ('base_logloss', metrics['binary']['base']['logloss']),
        ('author_logloss', metrics['binary']['author']['logloss']),
        ('base_spearman', metrics['multiclass']['base']['spearman']),
        ('author_spearman', metrics['multiclass']['author']['spearman']),
        ('base_mse', metrics['multiclass']['base']['mse']),
        ('author_mse', metrics['multiclass']['author']['mse']),
    )
    for label, value in scalar_metrics:
        add(checks, prefix + '_' + label + '_visible', f'{value:.5f}' in text)
        add(checks, prefix + '_' + label + '_notes', str(value) in notes)
    for key in ('binary_delta_auc', 'binary_logloss_improvement', 'multiclass_delta_spearman', 'multiclass_mse_improvement'):
        comp = comps[key]
        add(checks, prefix + '_' + key + '_visible', f"{comp['effect']:+.5f}" in text)
        add(checks, prefix + '_' + key + '_ci_visible', f"[{comp['ci95'][0]:.5f}, {comp['ci95'][1]:.5f}]" in text)
        add(checks, prefix + '_' + key + '_notes', str(comp['effect']) in notes and str(comp['ci95'][0]) in notes and str(comp['ci95'][1]) in notes)
        add(checks, prefix + '_' + key + '_positive_gate', comp['passes_all'] is True and comp['p_holm'] == 0.000199990000499975 and str(comp['p_holm']) in notes)
    hist = comparator['metrics']['rk23_histgb_plus_uh']
    effects = comparator['descriptive_effects']
    for label, value in (
        ('histgb_spearman', hist['spearman']), ('histgb_mse', hist['mse']),
        ('histgb_delta_spearman', effects['author_minus_histgb_spearman']),
        ('histgb_mse_improvement', effects['histgb_minus_author_mse']),
    ):
        add(checks, prefix + '_' + label + '_visible', f'{value:+.5f}' in text if 'delta' in label or 'improvement' in label else f'{value:.5f}' in text)
        add(checks, prefix + '_' + label + '_notes', str(value) in notes)
    add(checks, prefix + '_comparator_descriptive', comparator['status'] == 'PASS_DESCRIPTIVE_HISTGB_COMPARATOR' and comparator['primary_gate_changed'] is False and 'descriptive only' in notes)
    for phrase in ('4 / 4 PASS', '153 / 153', 'HistGB comparison is descriptive, not a new p-value family.', 'RK-G1 remains false; generator training is unauthorized.', 'Functional untouched unread; no CodonFlow-RK or SOTA claim.', '116 · RK24', test_commit[:8], closeout_commit[:8]):
        add(checks, prefix + '_visible_' + phrase[:32], phrase in text)
    add(checks, prefix + '_commits', test_commit in notes and closeout_commit in notes)
    add(checks, prefix + '_no_false_generator_claim', 'generator training is authorized.' not in text and 'RK-G1 remains true' not in text)
    add(checks, prefix + '_notes_five_paragraphs', len(note_text(slide).splitlines()) == 5)
    data = child(slide, 'data')
    add(checks, prefix + '_data_present', data is not None)
    ids = [x.attrib['id'] for x in slide.iter() if 'id' in x.attrib]
    add(checks, prefix + '_ids_unique', len(ids) == len(set(ids)), len(ids))
    tables = [x for x in slide.iter() if local(x.tag) == 'table']
    add(checks, prefix + '_one_table', len(tables) == 1)
    if tables:
        rows = children(tables[0], 'tr')
        add(checks, prefix + '_table_five_rows', len(rows) == 5)
        add(checks, prefix + '_table_six_columns', all(len(children(row, 'td')) == 6 for row in rows))
        cols = child(tables[0], 'colgroup')
        add(checks, prefix + '_table_width', cols is not None and sum(int(c.attrib['width']) * int(c.attrib.get('span', '1')) for c in children(cols, 'col')) == 864)
    bounded = 0
    bounds_ok = True
    for el in list(data) if data is not None else []:
        if 'width' not in el.attrib:
            continue
        bounded += 1
        x, y = float(el.attrib['topLeftX']), float(el.attrib['topLeftY'])
        w, h = float(el.attrib['width']), float(el.attrib['height'])
        bounds_ok = bounds_ok and x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= 960 and y + h <= 540
    add(checks, prefix + '_canvas_bounds', bounds_ok and bounded >= 30, bounded)
    add(checks, prefix + '_no_external_media', not any(local(x.tag) in ('image', 'video', 'audio', 'iframe', 'formula', 'embed') for x in slide.iter()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=('candidate', 'online'), required=True)
    ap.add_argument('--candidate', required=True)
    ap.add_argument('--result', required=True)
    ap.add_argument('--verification', required=True)
    ap.add_argument('--comparator', required=True)
    ap.add_argument('--test-commit', required=True)
    ap.add_argument('--closeout-commit', required=True)
    ap.add_argument('--before')
    ap.add_argument('--after')
    ap.add_argument('--response')
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    result = json.loads(Path(args.result).read_text())
    verification = json.loads(Path(args.verification).read_text())
    comparator = json.loads(Path(args.comparator).read_text())
    candidate = slide_list(ET.parse(args.candidate).getroot())[0]
    checks = []
    if args.mode == 'candidate':
        verify_slide(candidate, result, verification, comparator, args.test_commit, args.closeout_commit, checks, 'candidate')
        extra = {}
    else:
        before = slide_list(ET.parse(args.before).getroot())
        after = slide_list(ET.parse(args.after).getroot())
        response = json.loads(Path(args.response).read_text())
        add(checks, 'baseline_115', len(before) == 115, len(before))
        add(checks, 'baseline_last_pZN', before[-1].attrib.get('id') == 'pZN', before[-1].attrib.get('id'))
        add(checks, 'after_116', len(after) == 116, len(after))
        add(checks, 'response_ok', response.get('ok') is True)
        response_data = response.get('data', {})
        new_id = after[-1].attrib.get('id')
        add(checks, 'response_slide_id_matches', response_data.get('slide_id') == new_id, {'response': response_data.get('slide_id'), 'after': new_id})
        add(checks, 'new_slide_not_duplicate', new_id not in [s.attrib.get('id') for s in before], new_id)
        old_same = [semantic(a) == semantic(b) for a, b in zip(before, after[:len(before)])]
        add(checks, 'all_old_pages_semantically_preserved', all(old_same), {'changed_pages': [i + 1 for i, ok in enumerate(old_same) if not ok]})
        add(checks, 'old_page_ids_preserved', [s.attrib.get('id') for s in before] == [s.attrib.get('id') for s in after[:len(before)]])
        verify_slide(after[-1], result, verification, comparator, args.test_commit, args.closeout_commit, checks, 'online')
        add(checks, 'new_slide_matches_candidate_semantically', semantic(candidate) == semantic(after[-1]))
        add(checks, 'new_slide_text_matches_candidate', slide_text(candidate) == slide_text(after[-1]))
        add(checks, 'new_slide_notes_match_candidate', note_text(candidate) == note_text(after[-1]))
        extra = {'new_slide_id': new_id, 'before_slides': len(before), 'after_slides': len(after), 'old_pages_semantically_preserved': all(old_same)}
    report = {'status': 'PASS' if all(x['pass'] for x in checks) else 'FAIL', 'mode': args.mode, 'checks_total': len(checks), 'checks_passed': sum(x['pass'] for x in checks), 'checks_failed': [x['name'] for x in checks if not x['pass']], 'checks': checks, **extra}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'checks'}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
