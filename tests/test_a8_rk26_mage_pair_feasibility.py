#!/usr/bin/env python3
import csv
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO = Path('/home/codonflow-a8-rk')
sys.path.insert(0, str(REPO))
from scripts import a8_rk26_audit_mage_pair_feasibility as production
from scripts import a8_rk26_verify_mage_pair_feasibility as independent

PROTOCOL = json.loads((REPO/'audits/20261121/RK26/a8_rk26_mage_pair_feasibility_protocol_v1.json').read_text())


def row(c1, a1, p1, c2, a2, p2, wt=0, fitness=999):
    return {'codon1':c1, 'aa1':a1, 'pos1':p1, 'codon2':c2, 'aa2':a2, 'pos2':p2, 'is_wt':wt, 'fitness_rich':fitness}


class RK26FeasibilityTests(unittest.TestCase):
    def test_01_cross_implementation_synonymous_double(self):
        rows = [row('GCC','A',1,'AAA','K',2,1), row('GCT','A',1,'AAG','K',2)]
        produced = production.build_sequence_facts(pd.DataFrame(rows)[production.REQUIRED_RAW])
        replay = independent.independent_facts(rows)
        self.assertEqual(produced, replay)
        self.assertEqual(produced[1]['mutation_order'], 2)
        self.assertEqual(produced[1]['is_synonymous'], 1)
        self.assertEqual(produced[1]['mutation_signature'], '1:GCC>GCT;2:AAA>AAG')

    def test_02_non_synonymous_change_excluded(self):
        rows = [row('GCC','A',1,'AAA','K',2,1), row('TCC','S',1,'AAA','K',2)]
        facts = independent.independent_facts(rows)
        self.assertEqual(facts[1]['mutation_order'], 1)
        self.assertEqual(facts[1]['is_synonymous'], 0)

    def test_03_wild_type_and_order_consistency(self):
        rows = [row('GCC','A',1,'AAA','K',2,1), row('GCC','A',1,'AAG','K',2)]
        facts = production.build_sequence_facts(pd.DataFrame(rows)[production.REQUIRED_RAW])
        self.assertEqual([r['mutation_order'] for r in facts], [0,1])
        self.assertEqual(facts[0]['record_class'], 'wild_type_control')
        self.assertEqual(facts[1]['record_class'], 'single_codon_variant_in_pair_assay')

    def test_04_small_protocol_coverage_pass(self):
        rows = [
            row('GCC','A',1,'AAA','K',2,1), row('GCT','A',1,'AAA','K',2), row('GCA','A',1,'AAA','K',2),
            row('GCT','A',1,'AAG','K',2), row('GCA','A',1,'AAG','K',2), row('TCC','S',1,'AAC','N',2),
        ]
        protocol = dict(PROTOCOL)
        protocol['expected_pair_contexts'] = ['1-2']
        protocol['expected_rows_per_pair'] = 6
        facts = production.build_sequence_facts(pd.DataFrame(rows)[production.REQUIRED_RAW])
        counts = production.summarize_contexts(facts, protocol)
        self.assertEqual(counts[0]['single_synonymous'], 2)
        self.assertEqual(counts[0]['double_synonymous'], 2)
        self.assertEqual(counts[0]['coverage_rule_pass'], 1)

    def test_05_singleton_double_fails_coverage(self):
        protocol = dict(PROTOCOL)
        protocol['expected_pair_contexts'] = ['1-2']
        protocol['expected_rows_per_pair'] = 3
        rows = [row('GCC','A',1,'AAA','K',2,1), row('GCT','A',1,'AAA','K',2), row('GCT','A',1,'AAG','K',2)]
        # Add a second synonymous single while retaining one double.
        rows.insert(2, row('GCA','A',1,'AAA','K',2))
        protocol['expected_rows_per_pair'] = 4
        facts = independent.independent_facts(rows)
        counts = independent.independent_counts(facts, protocol)
        self.assertEqual(counts[0]['single_synonymous'], 2)
        self.assertEqual(counts[0]['double_synonymous'], 1)
        self.assertEqual(counts[0]['coverage_rule_pass'], 0)

    def test_06_outcome_columns_are_not_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'raw.csv'
            pd.DataFrame([row('GCC','A',1,'AAA','K',2,1)]).to_csv(path,index=False)
            loaded = production.load_raw_sequence_columns(path)
            self.assertEqual(list(loaded.columns), production.REQUIRED_RAW)
            self.assertNotIn('fitness_rich', loaded.columns)

    def test_07_fact_schema_is_sequence_only(self):
        self.assertNotIn('expression_value', production.FACT_COLUMNS)
        self.assertNotIn('fitness_rich', production.FACT_COLUMNS)
        self.assertNotIn('RCS', production.FACT_COLUMNS)
        self.assertEqual(production.FACT_COLUMNS, independent.EXPECTED_FACT_FIELDS)

    def test_08_clean_alignment_known_rows(self):
        raw = pd.DataFrame([row('GCC','A',1,'AAA','K',2,1), row('GCT','A',1,'AAA','K',2)])[production.REQUIRED_RAW]
        facts = production.build_sequence_facts(raw)
        clean = pd.DataFrame([
            {'source_row':2,'construct_id':'WT','mutation_signature':'','record_class':'wild_type_control','codon_position':'1;2','wt_codon':'GCC;AAA','mutant_codon':'GCC;AAA','amino_acid':'A;K'},
            {'source_row':3,'construct_id':'1:GCC>GCT','mutation_signature':'1:GCC>GCT','record_class':'single_codon_variant_in_pair_assay','codon_position':'1;2','wt_codon':'GCC;AAA','mutant_codon':'GCT;AAA','amino_acid':'A;K'},
        ])
        production.verify_clean_alignment(clean, facts)

    def test_09_deterministic_gzip_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = dict(PROTOCOL)
            protocol['outputs'] = dict(PROTOCOL['outputs'])
            protocol['outputs']['large_artifact_root'] = tmp
            rows = [row('GCC','A',1,'AAA','K',2,1), row('GCT','A',1,'AAG','K',2)]
            facts = production.build_sequence_facts(pd.DataFrame(rows)[production.REQUIRED_RAW])
            small = dict(PROTOCOL)
            small['expected_pair_contexts'] = ['1-2']
            small['expected_rows_per_pair'] = 2
            counts = production.summarize_contexts(facts, small)
            first = production.write_outputs(facts, counts, protocol)['pair_facts_csv_gz']['sha256']
            second = production.write_outputs(facts, counts, protocol)['pair_facts_csv_gz']['sha256']
            self.assertEqual(first, second)

    def test_10_independent_report_does_not_import_production(self):
        source = (REPO/'scripts/a8_rk26_verify_mage_pair_feasibility.py').read_text()
        self.assertNotIn('a8_rk26_audit_mage_pair_feasibility', source)
        self.assertNotIn('sklearn', source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
