#!/usr/bin/env python3
import sys
from pathlib import Path
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

OUT = Path(__file__).resolve().parent
FONT = 'Inter'
NAVY = 'rgba(24,37,51,1)'
MUTED = 'rgba(105,119,135,1)'
TEAL = 'rgba(24,158,132,1)'
TEAL_BG = 'rgba(220,247,238,1)'
PINK = 'rgba(206,65,102,1)'
PINK_BG = 'rgba(253,231,237,1)'
AMBER = 'rgba(176,116,24,1)'
AMBER_BG = 'rgba(255,244,211,1)'
WHITE = 'rgba(255,255,255,1)'
BORDER = 'rgba(226,232,240,1)'
ALT = 'rgba(246,248,251,1)'


def rect(x, y, w, h, fill=WHITE, border=BORDER, radius=10):
    b = f'<border color="{border}" width="1"/>' if border else ''
    return f'<shape type="round-rect" topLeftX="{x}" topLeftY="{y}" width="{w}" height="{h}" presetHandlers="{radius}"><fill><fillColor color="{fill}"/></fill>{b}</shape>'


def text(x, y, w, h, value, size=10, color=NAVY, bold=False, align='left', wrap=True):
    attrs = f'wrap="false"' if not wrap else ''
    return (f'<shape type="text" topLeftX="{x}" topLeftY="{y}" width="{w}" height="{h}">'
            f'<content textType="body" fontSize="{size}" fontFamily="{FONT}" color="{color}" '
            f'bold="{str(bold).lower()}" textAlign="{align}" verticalAlign="middle" lineSpacing="multiple:1.05" {attrs}>'
            f'<p>{escape(str(value))}</p></content></shape>')


def kpi(x, label, value, note, color=TEAL):
    return ''.join([
        rect(x, 104, 204, 76),
        text(x + 10, 110, 184, 14, label, 8, MUTED, True, wrap=False),
        text(x + 10, 126, 184, 28, value, 20, color, True, wrap=False),
        text(x + 10, 157, 184, 15, note, 7, MUTED, wrap=False),
    ])


def table(x, y, widths, rows, row_heights, aligns=None, font_size=9):
    total_w = sum(widths)
    total_h = sum(row_heights)
    aligns = aligns or ['left'] * len(widths)
    out = [f'<table topLeftX="{x}" topLeftY="{y}" width="{total_w}" height="{total_h}"><colgroup>']
    out += [f'<col width="{w}"/>' for w in widths]
    out.append('</colgroup>')
    for ri, (row, rh) in enumerate(zip(rows, row_heights)):
        out.append(f'<tr height="{rh}">')
        for ci, value in enumerate(row):
            header = ri == 0
            fill = NAVY if header else (ALT if ri % 2 == 0 else WHITE)
            color = WHITE if header else NAVY
            out.append(f'<td><fill><fillColor color="{fill}"/></fill>')
            out.append(f'<content textType="body" fontSize="{font_size}" fontFamily="{FONT}" color="{color}" bold="{str(header or (ri == len(rows)-1 and str(row[0]) == "TOTAL")).lower()}" textAlign="{aligns[ci]}" verticalAlign="middle" lineSpacing="multiple:1.0" paddingLeft="7" paddingRight="7" paddingTop="2" paddingBottom="2"><p>{escape(str(value))}</p></content></td>')
        out.append('</tr>')
    out.append('</table>')
    return ''.join(out)


def callout(y, value, kind='teal'):
    if kind == 'pink':
        fg, bg = PINK, PINK_BG
    elif kind == 'amber':
        fg, bg = AMBER, AMBER_BG
    else:
        fg, bg = TEAL, TEAL_BG
    return rect(48, y, 864, 30, bg, None, 8) + text(60, y + 3, 840, 24, value, 9, fg, True)


def slide(section, title, subtitle, body, notes, source, number):
    parts = [
        text(48, 7, 480, 15, section, 8, TEAL, True, wrap=False),
        text(650, 7, 262, 15, 'A8 / RK38 / BASELINE + UNTOUCHED', 7, MUTED, align='right', wrap=False),
        text(48, 27, 864, 40, title, 26, NAVY, True, wrap=False),
        rect(48, 72, 58, 4, TEAL, None, 1),
        text(48, 80, 864, 18, subtitle, 9, MUTED, wrap=False),
        body,
        text(48, 510, 810, 14, source, 7, MUTED, wrap=False),
        text(886, 507, 28, 17, str(number), 9, NAVY, True, align='right', wrap=False),
    ]
    note_xml = ''.join(f'<p>{escape(n)}</p>' for n in notes)
    return ('<slide xmlns="https://www.larkoffice.com/sml/2.0"><style><fill><fillColor color="rgb(248,250,252)"/></fill></style><data>'
            + ''.join(parts) + f'</data><note><content textType="body">{note_xml}</content></note></slide>')


def build(number):
    if number == 181:
        body = ''.join([
            kpi(48, 'DETAILED INVENTORY', '846 cells', 'raw record / seed / method rows'),
            kpi(268, 'EXTERNAL ACTUAL SETS', '126 / 126', 'exact DNA-set matrix alignment'),
            kpi(488, 'INDEPENDENT VERIFIER', '1851 / 1851', 'primary and clean checks'),
            kpi(708, 'NEW OUTCOMES READ', '0', 'untouched labels remain closed', PINK),
            table(48, 204, [220, 390, 254], [
                ['Question', 'Verified evidence', 'Decision'],
                ['Which raw assets exist?', 'A7, RK06, A6, LinearDesign-11 and EnsembleDesign reconciled by SHA and sequence identity', 'Asset inventory passes'],
                ['Are external sets complete?', '18 records × 7 methods; all 126 actual sets match the frozen matrix', 'Actual-set coverage passes'],
                ['Is a unified ranking supported?', 'Different input semantics, missing common dense trajectories and non-comparable costs', 'No unified causal ranking'],
                ['Was untouched evaluation run?', 'Only frozen split summaries and file metadata were used', 'No; authorization remains false'],
            ], [28, 48, 48, 48, 48], font_size=9),
            callout(438, 'PASS_INVENTORY_ONLY_SCIENTIFIC_GATES_UNRESOLVED', 'teal'),
            callout(474, 'No new training · no new external generation · no untouched outcomes · no SOTA or RK-G1 claim', 'amber'),
        ])
        return slide('01 / INVENTORY SCOPE', 'The inventory is complete; the scientific gates remain open',
                     'Read-only reconstruction · sequence-verified assets · missing evidence is not retroactively filled', body,
                     ['RK38 separates verified asset availability from scientific success.',
                      'The inventory reconciles 846 detailed cells and all 126 external actual-set cells.',
                      'No new model training, external generation or untouched outcome access occurred.',
                      'The passing result applies only to inventory integrity and reproduction.'],
                     'Source: RK38 protocol 025006e43ec1 · production 1c0994b38582 · independent v2 43299ee02438', number)
    if number == 182:
        body = ''.join([
            kpi(48, 'DETAILED CELLS', '846', 'five non-identical evidence lines'),
            kpi(268, 'LEARNED CUDA RUNS', '108', 'A7 FULL and EDIT · gate failed', PINK),
            kpi(488, 'UNIQUE SCORER CALLS', '108,000', 'RK06 · 216 × 500 ordered points'),
            kpi(708, 'SEPARATE B11 CALLS', '792', 'RK16 · four external methods'),
            table(48, 196, [220, 72, 340, 232], [
                ['Evidence line', 'Cells', 'Real execution content', 'Interpretation'],
                ['A7 / G2 FULL + EDIT + shared', '324', '108 learned CUDA + 216 shared simple-search runs', 'Existing generation failure'],
                ['RK06 dense simple search', '216', '500 ordered points per run; 108,000 scorer calls', 'Cost-resolved overlap with A7'],
                ['A6 five legacy methods', '270', '18 records × 3 seeds × 5 methods', 'External actual-set references'],
                ['LinearDesign-11 official grid', '18', '198 official runs summarized at record level', 'Objective weights are not budgets'],
                ['EnsembleDesign 11-run recovery', '18', '18 official processes; 11 runs per record', 'External actual-set reference'],
                ['TOTAL', '846', 'Sequence-verified raw record / seed / method cells', 'Inventory only; not a ranking'],
            ], [28, 38, 38, 38, 38, 38, 38], aligns=['left', 'right', 'left', 'left'], font_size=9),
            callout(466, 'RK06 and A7 shared simple search are overlapping evidence lines, not independent method replicates.', 'teal'),
        ])
        return slide('02 / VERIFIED COVERAGE', '846 verified cells reconcile the real baseline evidence',
                     'Raw-file SHA · exact record / seed / method keys · real ordered points where available', body,
                     ['The 846-cell inventory includes A7, RK06, A6 and two recovered external evidence lines.',
                      'RK06 supplies 108,000 unique scorer calls across 216 dense simple-search runs.',
                      'The 792 RK16 generation calls are a separate derived analysis and are not added to the 846 cells.',
                      'A7 and RK06 shared simple-search evidence overlap and are not independent replicates.'],
                     'Source: RK38 detailed CSV e792c6dca54d · 846 rows · RK16 792 real generation calls retained separately', number)
    if number == 183:
        body = ''.join([
            kpi(48, 'SEQUENCE-SET MATCH', '126 / 126', '18 records × 7 methods'),
            kpi(268, 'UNIQUE ACTUAL OUTPUTS', '5,471', 'aggregated across 18 records'),
            kpi(488, 'DESCRIPTIVE MAX HV', '29.9729', 'LinearDesign-11 · proxy objective'),
            kpi(708, 'CODONFLOW ARMS', '0', 'no causal CodonFlow comparison', PINK),
            table(48, 196, [230, 110, 150, 150, 224], [
                ['External method', 'Outputs', 'Mean normalized HV', 'Mean pairwise NED', 'Dense actual-set AUC'],
                ['LinearDesign-11', '131', '29.97288749', '0.07128928', 'Not available'],
                ['Legacy LinearDesign scan', '103', '29.85589404', '0.07924804', 'Not available'],
                ['GEMORNA', '1,427', '20.01528840', '0.16375052', 'Not available'],
                ['EnsembleDesign 11-run', '192', '16.69398208', '0.04580360', 'Not available'],
                ['codonGPT', '1,800', '14.53721918', '0.23001838', 'Not available'],
                ['CAI-greedy', '18', '11.52355615', '0', 'Not available'],
                ['Uniform synonymous', '1,800', '1.71876321', '0.24078285', 'Not available'],
            ], [28, 29, 29, 29, 29, 29, 29, 29], aligns=['left', 'right', 'right', 'right', 'left'], font_size=9),
            callout(445, 'Separate RK16 B11: 792 calls · AUC 22.7946 LinearDesign-11 · 14.8962 Ensemble · 5.2054 codonGPT · 0.7030 uniform', 'teal'),
            callout(479, 'Actual-set HV is descriptive only: no common dense AUC, no time match, no functional outcome, no external SOTA.', 'amber'),
        ])
        return slide('03 / EXTERNAL ACTUAL SETS', 'Descriptive HV leadership is not an external SOTA verdict',
                     'Frozen proxy objective · exact DNA-sequence sets · actual returned outputs rather than imputed budgets', body,
                     ['All 126 external actual-set cells match the frozen seven-method matrix exactly.',
                      'LinearDesign-11 has the highest descriptive normalized hypervolume under the existing proxy objective.',
                      'This is not a dense-budget, time-matched, functional or CodonFlow-versus-external result.',
                      'The RK16 B11 analysis remains separate because it covers only four methods with real ordered prefixes.'],
                     'Source: seven-method matrix 29f5c0839135 · RK38 external-cell CSV 7de82e33f842 · RK16 audit 3cd364114a6e', number)
    if number == 184:
        body = ''.join([
            kpi(48, 'MAGE UNTOUCHED ROWS', '19,072', 'metadata and frozen split only'),
            kpi(268, 'SIGNATURE GROUPS', '13,569', 'construct-signature groups'),
            kpi(488, 'SYNONYMOUS 1-CODON', '362 rows', 'small eligible-looking subset', AMBER),
            kpi(708, 'OPERATIONAL CLUSTERS', '1', 'not multi-protein OOD', PINK),
            table(48, 204, [250, 360, 254], [
                ['Observed constraint', 'Consequence', 'Scientific decision'],
                ['Mixed variant composition', 'Includes nonsynonymous, codon-pair and UTR variants beyond 362 synonymous single-codon rows', 'No general fixed-protein claim'],
                ['One operational cluster', 'No independent multi-protein cluster structure', 'No protein-family OOD claim'],
                ['RK20 passed only 2 / 8 sequence-OOD tests', 'Functional robustness was not established before this audit', 'No retrospective success relabeling'],
                ['Outcomes and new file-content hashes not read', 'Only prior split summaries and metadata entered RK38', 'Untouched evaluation remains false'],
            ], [28, 48, 48, 48, 48], font_size=9),
            callout(438, 'The audit establishes eligibility limits; it does not run or authorize an untouched evaluation.', 'teal'),
            callout(474, 'functional_untouched_evaluated = false · new_functional_labels_read = false · functional_robustness_pass = false', 'pink'),
        ])
        return slide('04 / UNTOUCHED BOUNDARY', 'Untouched metadata do not establish multi-protein confirmation',
                     'Kelsic 2016 MAGE partition · eligibility audit only · outcome labels remain closed', body,
                     ['The functional-untouched partition contains 19,072 rows and 13,569 construct-signature groups.',
                      'Only 362 rows are synonymous single-codon variants and there is one operational cluster.',
                      'The partition therefore cannot independently support a general multi-protein fixed-protein conclusion.',
                      'RK38 did not read untouched outcomes or perform a functional evaluation.'],
                     'Source: RK04 frozen split b5e3b24c0e30 · RK20 finalization af7cbcbc1f85 · RK38 metadata-only audit', number)
    if number == 185:
        body = ''.join([
            kpi(48, 'PRIMARY INDEPENDENT', '1851 / 1851', 'standard-library-only verifier'),
            kpi(268, 'CLEAN INDEPENDENT', '1851 / 1851', 'detached reproduction'),
            kpi(488, 'CLEAN CLOSEOUT', '9 / 9', 'two CSV files byte-identical'),
            kpi(708, 'FULL PROJECT TESTS', '472 passed', '1 skipped · 5 subtests passed'),
            table(48, 204, [210, 150, 504], [
                ['Stage', 'Result', 'Verified evidence'],
                ['Production inventory', '846 + 126', 'Detailed rows and external cells align to raw assets and frozen matrices'],
                ['Independent verifier v2', '1851 / 1851 PASS', 'Raw rows and sequence sets rebuilt without importing production code'],
                ['Detached clean reproduction', '1851 / 1851 + 9 / 9', 'Detailed and external CSV files byte-identical; bounded summary equality'],
                ['Manuscript §6.49 + Tables 30–31', '19 / 19 PASS', 'Workflow PASS; exact section insertion; baseline byte-for-byte restoration'],
                ['English writing workflow', 'PASS', 'prepare + write + deliver + status · markdown-only delivery'],
            ], [28, 38, 38, 38, 38, 38], font_size=9),
            callout(432, 'Manuscript SHA 7660294a8763 · science commit 83469e5b · manuscript commit dfc7cc69', 'teal'),
            callout(468, 'Failure history is retained; schema and layout fixes changed readers, not raw scientific outcomes.', 'amber'),
        ])
        return slide('05 / REPRODUCTION & PAPER', 'Independent and clean checks close the inventory evidence',
                     'Two independent 1851-check runs · byte-identical CSV reproduction · manuscript §6.49 synchronized', body,
                     ['The independent verifier passes 1851 checks in both primary and clean roots.',
                      'Clean reproduction gives byte-identical detailed and external-cell CSV files and passes nine closeout checks.',
                      'The full project suite records 472 passed tests with one skip and five subtests passed.',
                      'Manuscript section 6.49 and Tables 30 and 31 passed 19 integration and evidence checks.'],
                     'Source: independent 43299ee02438 · clean closeout 21e9ba813d87 · manuscript audit 19 / 19 PASS', number)
    if number == 186:
        body = ''.join([
            kpi(48, 'EXTERNAL SOTA', 'false', 'no unified eligible comparison', PINK),
            kpi(268, 'TIME-MATCHED', 'false', 'cost scopes are not unified', PINK),
            kpi(488, 'UNTOUCHED CONFIRMATION', 'false', 'outcomes were not evaluated', PINK),
            kpi(708, 'RK-G1 / SUBMITTABLE', 'false / false', 'scientific gates remain open', PINK),
            table(48, 204, [220, 380, 264], [
                ['Open gate', 'What is still missing', 'Allowed next evidence'],
                ['External and time-matched baselines', 'Common input semantics, real ordered budgets and comparable cost accounting', 'Preregistered common-input evaluation'],
                ['Functional and protein OOD', 'Eligible multi-protein data and robust fixed-protein confirmation', 'Feasibility audit before outcome access'],
                ['Generator evidence', 'A7/G2 failed; expensive generator training is not authorized', 'No automatic retraining or SOTA writing'],
                ['Prospective biological validation', 'No wet-lab or prospective DBTL result', 'Wild-type and strong algorithmic controls'],
                ['Manuscript readiness', 'Core functional and comparative claims remain unsupported', 'Retain non-submittable working-draft status'],
            ], [28, 43, 43, 43, 43, 43], font_size=9),
            callout(474, 'Next step must be a feasible discriminating experiment or dataset audit, not another inventory or a claim upgrade.', 'teal'),
        ])
        return slide('06 / EVIDENCE BOUNDARY', 'Asset closure does not convert into scientific closure',
                     'Inventory integrity is necessary but insufficient · negative and missing evidence remain visible', body,
                     ['RK38 closes an engineering and evidence-inventory gap, not the core scientific gates.',
                      'External SOTA, unified time matching and untouched confirmation remain false.',
                      'Functional robustness, protein OOD, prospective DBTL and generator evidence are still unresolved.',
                      'The next step must supply discriminating scientific evidence rather than another inventory.'],
                     'Source: RK38 clean closeout 21e9ba813d87 · scope remains inventory-only · manuscript remains non-submittable', number)
    raise ValueError(number)


def main():
    number = int(sys.argv[1])
    xml = build(number)
    ET.fromstring(xml)
    path = OUT / f'rk38_{number}.xml'
    path.write_text(xml, encoding='utf-8')
    print(path)


if __name__ == '__main__':
    main()
