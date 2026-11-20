#!/usr/bin/env python3
"""Evidence-bound candidate and online verification for the single RK26 slide."""
from pathlib import Path
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET

TITLE = 'Only 4 synonymous doubles: interaction OOD is not supported'
SCIENCE_COMMIT = '6c142514701188efc7cdf79dd99eaf637685434c'
CLOSEOUT_COMMIT = '09338fb1fb834c72550ad509db2a4692daa97969'


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


def table_matrix(table, namespace):
    rows = table.findall(f'{{{namespace}}}tr')
    return [[text_of(td).strip() for td in row.findall(f'{{{namespace}}}td')] for row in rows]


def expected_matrix(result):
    rows = [['Pair','WT codons','All rows','All singles','All doubles','Syn singles','Syn doubles','Coverage']]
    for pair in result['pair_contexts']:
        rows.append([
            pair['pair_id'].replace('-', '–'),
            pair['wt_codon1'] + ';' + pair['wt_codon2'],
            f"{pair['rows']:,}", str(pair['single_total']), f"{pair['double_total']:,}",
            str(pair['single_synonymous']), str(pair['double_synonymous']),
            'PASS' if pair['coverage_rule_pass'] == 1 else 'FAIL',
        ])
    rows.append(['Total','—',f"{result['rows']:,}",str(result['record_class_counts']['single_codon_variant_in_pair_assay']),
                 f"{result['record_class_counts']['codon_pair_variant']:,}",str(result['synonymous_single_variants']),
                 str(result['synonymous_double_variants']),'NOT FEASIBLE'])
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['candidate','online'],required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--independent',type=Path,required=True)
    parser.add_argument('--closeout',type=Path,required=True)
    parser.add_argument('--source-xml',type=Path)
    parser.add_argument('--source-response',type=Path)
    parser.add_argument('--before-xml',type=Path)
    parser.add_argument('--after-xml',type=Path)
    parser.add_argument('--before-response',type=Path)
    parser.add_argument('--after-response',type=Path)
    parser.add_argument('--write-response',type=Path)
    parser.add_argument('--slide-id')
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = json.loads(args.result.read_text())
    independent = json.loads(args.independent.read_text())
    closeout = json.loads(args.closeout.read_text())
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
    check('table eight columns',all(len(row.findall(f'{{{candidate_ns}}}td'))==8 for row in rows))
    check('table exact science matrix',table_matrix(table,candidate_ns)==expected_matrix(result))
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
    check('title exact',TITLE in candidate_visible)
    check('pair rows exact',any('8,192 pair-assay constructs' in text for text in candidate_visible))
    check('synonymous singles exact',any('6 SYN SINGLES' in text for text in candidate_visible))
    check('synonymous doubles exact',any('4 SYN DOUBLES' in text for text in candidate_visible))
    check('independent exact',any('42 / 42' in text for text in candidate_visible))
    check('closeout exact',any('closeout 54/54' in text for text in candidate_visible))
    check('candidate closed',any('CANDIDATE CLOSED' in text for text in candidate_visible))
    check('no model fits visible',any('0 model fits' in text for text in candidate_visible))
    check('no endpoints visible',any('No model, endpoint, CI or p-value was produced.' in text for text in candidate_visible))
    check('RK-G1 closed',any('RK-G1 remains false' in text for text in candidate_visible))
    check('generator unauthorized',any('generator training is unauthorized' in text for text in candidate_visible))
    check('untouched unread',any('RK04 untouched split not accessed' in text for text in candidate_visible))
    check('science commit visible',any('6c142514' in text for text in candidate_visible))
    check('closeout commit visible',any('09338fb1' in text for text in candidate_visible))
    check('page number',candidate_visible[-1]=='118 · RK26')
    check('paper source in notes',result['source']['paper_url'] in candidate_text)
    check('raw hash in notes',result['source']['raw_sha256'] in candidate_text)
    check('clean hash in notes',result['source']['clean_sha256'] in candidate_text)
    check('facts hash in notes',result['artifacts']['pair_facts_csv_gz']['sha256'] in candidate_text)
    check('result hash in notes',closeout['production_result_sha256'] in candidate_text)
    check('independent hash in notes',closeout['independent_report_sha256'] in candidate_text)
    check('science commit in notes',SCIENCE_COMMIT in candidate_text)
    check('closeout commit in notes',CLOSEOUT_COMMIT in candidate_text)
    check('retrospective boundary','retrospective data-adequacy audit' in candidate_text)
    check('not power analysis','not a power analysis' in candidate_text)
    check('no success overclaim','MECHANISM PASS' not in candidate_text and 'OOD FEASIBLE' not in candidate_text)
    check('science outcome exact',result['scientific_outcome']=='FIXED_PROTEIN_SINGLE_TO_DOUBLE_SYNONYMOUS_OOD_NOT_SUPPORTED_BY_SAMPLE_COVERAGE')
    check('science no fit or endpoint',result['model_fits']==0 and result['functional_endpoint_evaluations']==0 and result['confidence_intervals_or_p_values']==0)
    check('science splits unread',result['original_mage_33_construct_mechanism_test_accessed'] is False and result['rk04_functional_untouched_split_accessed'] is False)
    check('science no authorization',result['rk_g1_pass'] is False and result['generator_training_authorized'] is False)
    check('independent 42 of 42',independent['status']=='PASS' and independent['checks_total']==42 and independent['checks_passed']==42 and all(c['pass'] for c in independent['checks']))
    check('independent counts exact',independent['independent_single_synonymous']==6 and independent['independent_double_synonymous']==4)
    check('closeout 54 of 54',closeout['status']=='PASS' and closeout['checks_total']==54 and closeout['checks_passed']==54 and all(c['pass'] for c in closeout['checks']))
    check('production hash bound',closeout['production_result_sha256']==sha(args.result)==independent['production_report_sha256'])
    check('independent hash bound',closeout['independent_report_sha256']==sha(args.independent))
    check('science commit bound',closeout['science_commit']==SCIENCE_COMMIT)
    report = {
        'schema':'a8-rk26-ppt-verification-v1','mode':args.mode,
        'candidate_sha256':sha(args.candidate),'result_sha256':sha(args.result),
        'independent_sha256':sha(args.independent),'closeout_sha256':sha(args.closeout),
        'slide_title':TITLE,'candidate_visible_paragraphs':len(candidate_visible),
        'candidate_note_paragraphs':len(candidate_notes),'expected_table':expected_matrix(result),
    }
    if args.mode=='candidate':
        source_response = json.loads(args.source_response.read_text())
        source,source_ns = parse(args.source_xml)
        slides = source.findall(f'{{{source_ns}}}slide')
        check('source response ok',source_response.get('ok') is True)
        check('source revision 80',source_response['data']['revision_id']==80)
        check('source 117 pages',len(slides)==117)
        check('source last RK25',slides[-1].attrib.get('id')=='pZX')
        check('no previous RK26',all(TITLE not in text_of(slide) for slide in slides))
        report.update({'source_sha256':sha(args.source_xml),'source_revision':80,'source_pages':117})
    else:
        before_response = json.loads(args.before_response.read_text())
        after_response = json.loads(args.after_response.read_text())
        write_response = json.loads(args.write_response.read_text())
        before,before_ns = parse(args.before_xml)
        after,after_ns = parse(args.after_xml)
        before_slides = before.findall(f'{{{before_ns}}}slide')
        after_slides = after.findall(f'{{{after_ns}}}slide')
        check('before response ok',before_response.get('ok') is True)
        check('after response ok',after_response.get('ok') is True)
        check('write response ok',write_response.get('ok') is True and write_response.get('data',{}).get('slide_id')==args.slide_id)
        check('one revision increment',after_response['data']['revision_id']==before_response['data']['revision_id']+1)
        check('write revision matches after',write_response['data']['revision_id']==after_response['data']['revision_id'])
        check('one page append',len(after_slides)==len(before_slides)+1==118)
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
        check('online table eight columns',all(len(row.findall(f'{{{after_ns}}}td'))==8 for row in online_rows))
        check('online table exact science matrix',table_matrix(online_tables[0],after_ns)==expected_matrix(result))
        check('only one RK26 title',sum(TITLE in text_of(slide) for slide in after_slides)==1)
        report.update({'before_sha256':sha(args.before_xml),'after_sha256':sha(args.after_xml),
                       'write_response_sha256':sha(args.write_response),
                       'before_revision':before_response['data']['revision_id'],
                       'after_revision':after_response['data']['revision_id'],
                       'before_pages':len(before_slides),'after_pages':len(after_slides),'slide_id':args.slide_id})
    failed = [item['name'] for item in checks if not item['pass']]
    report.update({'status':'PASS' if not failed else 'FAIL','checks_total':len(checks),
                   'checks_passed':len(checks)-len(failed),'failed_checks':failed,'checks':checks,
                   'confirmatory_ood_feasible':False,'model_fits':0,'functional_endpoint_evaluations':0,
                   'rk_g1':False,'generator_training_authorized':False,'functional_untouched_evaluated':False})
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({key:report[key] for key in ['mode','status','checks_total','checks_passed','failed_checks']},indent=2))
    if failed:
        raise SystemExit(1)


if __name__=='__main__':
    main()
