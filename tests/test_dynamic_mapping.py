# tests/test_dynamic_mapping.py
import unittest
from decimal import Decimal

from custom_components.dmx.fixture.capability import DynamicMapping


class TestDynamicMapping(unittest.TestCase):

    def setUp(self):
        self.dynamic_mapping = DynamicMapping(range_start=0, range_end=100, dmx_start=0, dmx_end=255)

        self.base_unit = Decimal('1') / Decimal('2.55')

        self.superprecise_unit = float(Decimal('1') / Decimal('2.55') -
                         Decimal('1') / Decimal('2.55') / Decimal('255.0') -
                         Decimal('1') / Decimal('2.55') / Decimal('255.0') / Decimal('255.0'))

    def test_to_dmx(self):
        unit = float(Decimal('1') / Decimal('2.55'))

        self.assertEqual(0, self.dynamic_mapping.to_dmx(0))
        self.assertEqual(127, self.dynamic_mapping.to_dmx(50))
        self.assertEqual(255, self.dynamic_mapping.to_dmx(100))
        self.assertEqual([1], self.dynamic_mapping.to_dmx_fine(unit, num_channels=1))

    def test_from_dmx(self):
        unit = float(Decimal('1') / Decimal('2.55'))

        self.assertEqual(0, self.dynamic_mapping.from_dmx(0))
        self.assertAlmostEqual(50.0, self.dynamic_mapping.from_dmx(127), None, "", 1)
        self.assertEqual(100, self.dynamic_mapping.from_dmx(255))
        self.assertAlmostEqual(unit, self.dynamic_mapping.from_dmx_fine([1]), None, "", 1)

    def test_to_dmx_fine(self):
        precise_unit = float(Decimal('1') / Decimal('2.55') / Decimal('255.0'))

        self.assertEqual([0, 0], self.dynamic_mapping.to_dmx_fine(0, num_channels=2))
        self.assertEqual([127, 255], self.dynamic_mapping.to_dmx_fine(50, num_channels=2))
        self.assertEqual([255, 255], self.dynamic_mapping.to_dmx_fine(100, num_channels=2))
        self.assertEqual([0, 1], self.dynamic_mapping.to_dmx_fine(precise_unit, num_channels=2))

    def test_from_dmx_fine(self):
        precise_unit = float(Decimal('1') / Decimal('2.55') / Decimal('255.0'))

        self.assertEqual(0, self.dynamic_mapping.from_dmx_fine([0, 0]))
        self.assertAlmostEqual(50.00, self.dynamic_mapping.from_dmx_fine([127, 255]), 2)
        self.assertEqual(100, self.dynamic_mapping.from_dmx_fine([255, 255]))
        self.assertAlmostEqual(precise_unit, self.dynamic_mapping.from_dmx_fine([0, 1]), 2)

    def test_to_dmx_superfine(self):
        superprecise_unit = float(Decimal('1') / Decimal('2.55') / Decimal('255.0') / Decimal('255.0'))

        self.assertEqual([0, 0, 0], self.dynamic_mapping.to_dmx_fine(0, num_channels=3))
        self.assertEqual([127, 255, 255], self.dynamic_mapping.to_dmx_fine(50, num_channels=3))
        self.assertEqual([255, 255, 255], self.dynamic_mapping.to_dmx_fine(100, num_channels=3))
        self.assertEqual([0, 0, 1], self.dynamic_mapping.to_dmx_fine(superprecise_unit, num_channels=3))

    def test_from_dmx_superfine(self):
        superprecise_unit = float(Decimal('1') / Decimal('2.55') / Decimal('255.0') / Decimal('255.0'))

        self.assertEqual(0, self.dynamic_mapping.from_dmx_fine([0, 0, 0]))
        self.assertAlmostEqual(50.0000, self.dynamic_mapping.from_dmx_fine([127, 255, 255]), 4)
        self.assertEqual(100, self.dynamic_mapping.from_dmx_fine([255, 255, 255]))
        self.assertAlmostEqual(superprecise_unit, self.dynamic_mapping.from_dmx_fine([0, 0, 1]), 4)

    def tearDown(self):
        del self.dynamic_mapping


if __name__ == "__main__":
    unittest.main()
