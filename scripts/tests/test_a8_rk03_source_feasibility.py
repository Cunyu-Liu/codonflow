#!/usr/bin/env python3
import csv, importlib.util, json, unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
PROD=HERE/'a8_rk03_source_feasibility.py'
PROTOCOL=HERE/'a8_rk03_source_feasibility_protocol_v1.json'
if not PROD.exists(): PROD=HERE.parent/'a8_rk03_source_feasibility.py'
if not PROTOCOL.exists(): PROTOCOL=HERE.parent.parent/'configs/a8_rk03_source_feasibility_protocol_v1.json'
spec=importlib.util.spec_from_file_location('source_feasibility',PROD)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
SOFT='''!Series_title = Synthetic study
!Series_sample_id = GSM1
!Series_sample_id = GSM2
!Series_relation = SRA: https://www.ncbi.nlm.nih.gov/sra?term=SRP000001
!Series_relation = BioProject: https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1
^SAMPLE = GSM1
!Sample_library_strategy = RNA-Seq
!Sample_data_processing = Genome_build: test1
!Sample_data_processing = P-site: read 5' end plus 15 nt
^SAMPLE = GSM2
!Sample_library_strategy = RNA-Seq
!Sample_data_processing = Genome_build: test1
!Sample_data_processing = Reads mapped with 3'-end assignment
'''
RUNINFO='''Run,Experiment,spots,bases,size_MB,download_path,LibraryStrategy
SRR1,SRX1,10,1000,2,https://example/SRR1,RNA-Seq
SRR2,SRX2,20,2000,3,https://example/SRR2,Ribo-Seq
'''
class TestSourceFeasibility(unittest.TestCase):
 def test_soft_title(self): self.assertEqual(m.parse_soft(SOFT)['title'],'Synthetic study')
 def test_soft_series_samples(self): self.assertEqual(m.parse_soft(SOFT)['series_sample_count'],2)
 def test_soft_sample_records(self): self.assertEqual(m.parse_soft(SOFT)['sample_record_count'],2)
 def test_soft_sra(self): self.assertEqual(m.parse_soft(SOFT)['sra_relations'],['SRP000001'])
 def test_soft_bioproject(self): self.assertEqual(m.parse_soft(SOFT)['bioproject_relations'],['PRJNA1'])
 def test_soft_genome(self): self.assertEqual(m.parse_soft(SOFT)['genome_builds'],['test1'])
 def test_soft_site_evidence(self): self.assertEqual(len(m.parse_soft(SOFT)['site_assignment_evidence']),2)
 def test_runinfo_runs(self): self.assertEqual(m.parse_runinfo(RUNINFO)['run_count'],2)
 def test_runinfo_bases(self): self.assertEqual(m.parse_runinfo(RUNINFO)['bases'],3000)
 def test_runinfo_size(self): self.assertEqual(m.parse_runinfo(RUNINFO)['size_mb'],5)
 def test_runinfo_strategies(self): self.assertEqual(m.parse_runinfo(RUNINFO)['library_strategies'],{'RNA-Seq':1,'Ribo-Seq':1})
 def test_runinfo_rejects_empty(self):
  with self.assertRaises(ValueError): m.parse_runinfo('Run,Experiment\n')
 def test_protocol_is_metadata_only(self):
  p=json.loads(PROTOCOL.read_text())
  self.assertTrue(p['network_policy']['metadata_only']); self.assertFalse(p['network_policy']['download_fastq']); self.assertFalse(p['required_boundaries']['raw_read_remapping_completed'])
 def test_protocol_has_five_references(self):
  p=json.loads(PROTOCOL.read_text())
  self.assertEqual(len(p['veloharmo']['references']),5)
  self.assertEqual(p['veloharmo']['expected_released_harmonized_matrix_organisms'],['E.coli'])
if __name__=='__main__': unittest.main()
