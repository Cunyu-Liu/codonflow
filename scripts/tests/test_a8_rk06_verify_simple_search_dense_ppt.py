import unittest
import xml.etree.ElementTree as ET

from scripts import a8_rk06_verify_simple_search_dense_ppt as verifier


class SlideServiceNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.candidate = ET.fromstring('''<slide xmlns="https://www.larkoffice.com/sml/2.0"><data>
          <shape type="text" topLeftX="0" topLeftY="0" width="100" height="20"><content wrap="true"><p>Uniform  AUC 1.951</p></content></shape>
          <table topLeftX="0" topLeftY="30" width="100" height="20"><colgroup><col width="100"/></colgroup><tr><td><content textAlign="center"><p>HV500 2.334</p></content></td></tr></table>
        </data></slide>''')
        self.readback = ET.fromstring('''<slide xmlns="https://www.larkoffice.com/sml/2.0"><data>
          <shape type="text" topLeftX="0" topLeftY="0" width="100" height="20"><content><p>Uniform AUC 1.951</p></content></shape>
          <table topLeftX="0" topLeftY="30" width="100" height="20"><colgroup><col width="100" span="1"/></colgroup><tr><td><content><p>HV500 2.334</p></content></td></tr></table>
        </data></slide>''')

    def test_service_default_attributes_and_whitespace_are_equivalent(self):
        self.assertEqual(verifier.semantic(self.candidate), verifier.semantic(self.readback))
        self.assertEqual(verifier.text(self.candidate), verifier.text(self.readback))

    def test_numeric_change_is_not_normalized_away(self):
        changed = ET.fromstring(ET.tostring(self.readback))
        paragraph = next(p for p in changed.iter() if p.tag.rsplit("}", 1)[-1] == "p")
        paragraph.text = paragraph.text.replace("1.951", "1.952")
        self.assertNotEqual(verifier.semantic(self.candidate), verifier.semantic(changed))
        self.assertNotEqual(verifier.text(self.candidate), verifier.text(changed))

    def test_method_label_change_is_not_normalized_away(self):
        changed = ET.fromstring(ET.tostring(self.readback))
        paragraph = next(p for p in changed.iter() if p.tag.rsplit("}", 1)[-1] == "p")
        paragraph.text = paragraph.text.replace("Uniform", "Hill")
        self.assertNotEqual(verifier.semantic(self.candidate), verifier.semantic(changed))

    def test_text_shape_alignment_is_not_treated_as_table_default(self):
        candidate = ET.fromstring('<slide xmlns="https://www.larkoffice.com/sml/2.0"><data><shape type="text"><content textAlign="center"><p>x</p></content></shape></data></slide>')
        readback = ET.fromstring('<slide xmlns="https://www.larkoffice.com/sml/2.0"><data><shape type="text"><content><p>x</p></content></shape></data></slide>')
        self.assertNotEqual(verifier.semantic(candidate), verifier.semantic(readback))


if __name__ == "__main__":
    unittest.main()
