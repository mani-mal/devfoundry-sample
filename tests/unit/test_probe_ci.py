import unittest


class ProbeExpectedValueTest(unittest.TestCase):
    def test_probe_expected_value(self):
        # CI repair probe: deliberately wrong expected value (2 + 2 == 5).
        self.assertEqual(2 + 2, 5)

