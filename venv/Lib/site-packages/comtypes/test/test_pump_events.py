import gc
import unittest

from comtypes.client import PumpEvents


class PumpEventsTest(unittest.TestCase):
    def test_pump_events_doesnt_leak_cycles(self):
        gc.collect()
        for i in range(3):
            PumpEvents(0.05)
            ncycles = gc.collect()
            self.assertEqual(ncycles, 0)


if __name__ == "__main__":
    unittest.main()
