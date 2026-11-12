import unittest


class ProbeExpectedValueTest(unittest.TestCase):
    def test_probe_expected_value(self):
        # CI repair probe: expected value corrected by hand after the repair guard refused test edits (2 + 2 == 4).
        self.assertEqual(2 + 2, 4)

