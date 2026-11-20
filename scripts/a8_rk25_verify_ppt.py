#!/usr/bin/env python3
"""Evidence-bound candidate and online verification for the single RK25 slide."""
from pathlib import Path
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse(path):
    root = ET.parse(path).getroot()
    namespace = root.tag.split('}')[0].strip('{') if '}' in root.tag else ''
    return root, namespace


def children(root, namespace, name):
    return list(root.findall(f'.//{{{namespace}}}{name}')) if namespace else list(root.findall(f'.//{name}'))


def direct_data(root, namespace):
    return root.find(f'{{{namespace}}}data') if namespace else root.find('data')


def text_of(element):
    return ''.join(element.itertext())


def visible_paragraphs(root, namespace):
    data = direct_data(root, namespace)
    return [text_of(p) for p in data.findall(f'.//{{{namespace}}}p')] if data is not None else []


def note_paragraphs(root, namespace):
    note = root.find(f'{{{namespace}}}note') if namespace else root.find('note')
    return [] if note is None else [text_of(p) for p in note.findall(f'.//{{{namespace}}}p')]


def normalized(text):
    return text.replace('−','-').replace('–','-')


def semantic(element):
    return (
        element.tag,
        tuple(sorted(element.attrib.items())),
        (element.text or '').strip(),
        tuple(semantic(child) for child in list(element)),
    )


def geometry(root, namespace):
    data = direct_data(root, namespace)
    output = []
    for element in list(data):
        local = element.tag.split('}')[-1]
        keys = ['topLeftX','topLeftY','width','height','startX','startY','endX','endY','type','presetHandlers']
        output.append((local,tuple((key,element.attrib.get(key)) for key in keys if key in element.attrib)))
    return output


def common_numeric_checks(result, text, check):
    norm = normalized(text)
    rows = result['confirmatory_comparisons']
    for row in rows:
        label = f"{row['left']} {row['right']} {row['metric']}"
        point = f"{row['point_delta_mean_per_seed']:+.5f}"
        low = f"{row['ci95_low']:.5f}"
        high = f"{row['ci95_high']:.5f}"
        check(f'point {label}',point in norm)
        check(f'CI low {label}',low in norm)
        check(f'CI high {label}',high in norm)
    for model in ['ribokinetic_all','boel_author','ridge_all','histgb_all']:
        value = result['metrics']['sequence_ood']['mean_across_seeds'][model]['row_spearman']
        check(f'absolute Spearman {model}',f"{value:.5f}" in norm)
    author_mse = result['metrics']['sequence_ood']['mean_across_seeds']['boel_author']['cluster_balanced_mse']
    check('author absolute MSE',f"{author_mse:.5f}" in norm)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['candidate','online'],required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--source-xml',type=Path)
    parser.add_argument('--source-response',type=Path)
    parser.add_argument('--before-xml',type=Path)
    parser.add_argument('--after-xml',type=Path)
    parser.add_argument('--before-response',type=Path)
    parser.add_argument('--after-response',type=Path)
    parser.add_argument('--slide-id')
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = json.loads(args.result.read_text())
    candidate, candidate_ns = parse(args.candidate)
    candidate_visible = visible_paragraphs(candidate,candidate_ns)
    candidate_notes = note_paragraphs(candidate,candidate_ns)
    candidate_text = '\n'.join(candidate_visible+candidate_notes)
    checks = []
    def check(name,condition):
        checks.append({'name':name,'pass':bool(condition)})
    check('candidate root slide',candidate.tag.split('}')[-1]=='slide')
    check('candidate SML namespace',candidate_ns=='https://www.larkoffice.com/sml/2.0')
    check('no invented IDs',all('id' not in element.attrib for element in candidate.iter()))
    check('five note paragraphs',len(candidate_notes)==5)
    check('one native table',len(children(candidate,candidate_ns,'table'))==1)
    table = children(candidate,candidate_ns,'table')[0]
    rows = table.findall(f'{{{candidate_ns}}}tr')
    check('table four rows',len(rows)==4)
    check('table six columns',all(len(row.findall(f'{{{candidate_ns}}}td'))==6 for row in rows))
    check('no images',len(children(candidate,candidate_ns,'img'))==0)
    check('no undefined',len(children(candidate,candidate_ns,'undefined'))==0)
    check('no embed',len(children(candidate,candidate_ns,'embed'))==0)
    data = direct_data(candidate,candidate_ns)
    for index,element in enumerate(list(data)):
        local = element.tag.split('}')[-1]
        if 'topLeftX' in element.attrib:
            x=float(element.attrib['topLeftX']); y=float(element.attrib['topLeftY'])
            width=float(element.attrib['width']); height=float(element.attrib['height'])
            check(f'canvas bounds {index} {local}',x>=0 and y>=0 and x+width<=960 and y+height<=540)
    fonts = [element.attrib.get('fontFamily') for element in candidate.iter() if 'fontFamily' in element.attrib]
    check('Inter only',set(fonts)=={'Inter'})
    sizes = [float(element.attrib['fontSize']) for element in data.iter() if 'fontSize' in element.attrib]
    check('visible minimum 9pt',min(sizes)>=9)
    check('title exact','Author model wins; all-channel mechanism increment fails' in candidate_visible)
    check('OOD size exact',any('1,336 sequence-OOD constructs' in text for text in candidate_visible))
    check('bootstrap exact',any('20,000 replicates' in text for text in candidate_visible))
    check('independent exact',any('678 / 678' in text for text in candidate_visible))
    check('dev independent exact',any('337/337' in text for text in candidate_visible))
    check('mechanism fail visible',any('MECHANISM 0/2' in text for text in candidate_visible))
    check('author reference visible',any('AUTHOR REFERENCE 4/4' in text for text in candidate_visible))
    check('RK-G1 closed',any('RK-G1 remains false' in text for text in candidate_visible))
    check('generator unauthorized',any('generator training is unauthorized' in text for text in candidate_visible))
    check('test descriptive',any('Test is descriptive' in text for text in candidate_visible))
    check('untouched unread',any('functional untouched was not read' in text for text in candidate_visible))
    check('evidence commit',any('44014ad0' in text for text in candidate_visible))
    check('closeout commit',any('38ecaf7a' in text for text in candidate_visible))
    check('page number',candidate_visible[-1]=='117 · RK25')
    check('no majority-vote claim','4/6 PASS' not in candidate_text and '4 / 6 PASS' not in candidate_text)
    check('science gates',result['mechanism_vs_author_pass'] is False and result['author_reference_pass'] is True and result['strong_comparator_chain_pass'] is False)
    common_numeric_checks(result,'\n'.join(candidate_visible),check)
    report = {
        'schema':'a8-rk25-ppt-verification-v1','mode':args.mode,
        'candidate_sha256':sha(args.candidate),'result_sha256':sha(args.result),
        'slide_title':'Author model wins; all-channel mechanism increment fails',
        'candidate_visible_paragraphs':len(candidate_visible),'candidate_note_paragraphs':len(candidate_notes),
    }
    if args.mode=='candidate':
        source_response = json.loads(args.source_response.read_text())
        source,source_ns = parse(args.source_xml)
        slides = source.findall(f'{{{source_ns}}}slide')
        check('source response ok',source_response.get('ok') is True)
        check('source revision 79',source_response['data']['revision_id']==79)
        check('source 116 pages',len(slides)==116)
        check('source last RK24',slides[-1].attrib.get('id')=='pZt')
        check('no previous RK25',all('Author model wins; all-channel mechanism increment fails' not in text_of(slide) for slide in slides))
        report.update({'source_sha256':sha(args.source_xml),'source_revision':79,'source_pages':116})
    else:
        before_response = json.loads(args.before_response.read_text())
        after_response = json.loads(args.after_response.read_text())
        before,before_ns = parse(args.before_xml)
        after,after_ns = parse(args.after_xml)
        before_slides = before.findall(f'{{{before_ns}}}slide')
        after_slides = after.findall(f'{{{after_ns}}}slide')
        check('before response ok',before_response.get('ok') is True)
        check('after response ok',after_response.get('ok') is True)
        check('one revision increment',after_response['data']['revision_id']==before_response['data']['revision_id']+1)
        check('one page append',len(after_slides)==len(before_slides)+1==117)
        check('new slide ID',after_slides[-1].attrib.get('id')==args.slide_id)
        check('new slide is last',after_slides[-1].attrib.get('id')!=before_slides[-1].attrib.get('id'))
        check('old slide IDs unchanged',[s.attrib.get('id') for s in before_slides]==[s.attrib.get('id') for s in after_slides[:-1]])
        for index,(old,new) in enumerate(zip(before_slides,after_slides[:-1]),1):
            check(f'old page semantic identity {index}',semantic(old)==semantic(new))
        online = after_slides[-1]
        check('online visible exact',visible_paragraphs(online,after_ns)==candidate_visible)
        check('online notes exact',note_paragraphs(online,after_ns)==candidate_notes)
        check('online geometry exact',geometry(online,after_ns)==geometry(candidate,candidate_ns))
        online_tables = children(online,after_ns,'table')
        check('online one table',len(online_tables)==1)
        online_rows = online_tables[0].findall(f'{{{after_ns}}}tr')
        check('online table four rows',len(online_rows)==4)
        check('online table six columns',all(len(row.findall(f'{{{after_ns}}}td'))==6 for row in online_rows))
        check('only one RK25 title',sum('Author model wins; all-channel mechanism increment fails' in text_of(slide) for slide in after_slides)==1)
        common_numeric_checks(result,'\n'.join(visible_paragraphs(online,after_ns)),check)
        report.update({'before_sha256':sha(args.before_xml),'after_sha256':sha(args.after_xml),
                       'before_revision':before_response['data']['revision_id'],
                       'after_revision':after_response['data']['revision_id'],
                       'before_pages':len(before_slides),'after_pages':len(after_slides),'slide_id':args.slide_id})
    failed = [item['name'] for item in checks if not item['pass']]
    report.update({'status':'PASS' if not failed else 'FAIL','checks_total':len(checks),
                   'checks_passed':len(checks)-len(failed),'failed_checks':failed,'checks':checks,
                   'mechanism_vs_author_pass':False,'author_reference_pass':True,
                   'strong_comparator_chain_pass':False,'rk_g1':False,'functional_untouched_evaluated':False})
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({key:report[key] for key in ['mode','status','checks_total','checks_passed','failed_checks']},indent=2))
    if failed:
        raise SystemExit(1)


if __name__=='__main__':
    main()
