import doctest
import unittest
from typing import Optional


def load_tests(
    loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: Optional[str]
) -> unittest.TestSuite:
    import comtypes.test.test_showevents

    tests.addTests(doctest.DocTestSuite(comtypes.test.test_showevents))
    return tests


class ShowEventsExamples:
    def StdFont_ShowEvents(self):
        """
        >>> from comtypes.client import CreateObject, GetModule, ShowEvents, PumpEvents
        >>> _ = GetModule('scrrun.dll')  # generating `Scripting` also generates `stdole`
        >>> from comtypes.gen import stdole
        >>> font = CreateObject(stdole.StdFont)
        >>> conn = ShowEvents(font)
        # event found: FontEvents_FontChanged
        >>> font.Name = 'Arial'
        Event FontEvents_FontChanged(None, 'Name')
        >>> font.Italic = True
        Event FontEvents_FontChanged(None, 'Italic')
        >>> PumpEvents(0.01)  # just calling. assertion does in `test_pump_events.py`
        >>> conn.disconnect()
        """
        pass


if __name__ == "__main__":
    unittest.main()
