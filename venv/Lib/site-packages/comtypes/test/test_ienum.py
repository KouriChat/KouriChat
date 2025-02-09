import contextlib
import unittest as ut

from ctypes import POINTER
from comtypes import GUID
import comtypes.client


class Test_IEnum(ut.TestCase):
    def test_ienum(self):
        with contextlib.redirect_stdout(None):  # supress warnings, see test_client.py
            comtypes.client.GetModule("msvidctl.dll")
        from comtypes.gen import MSVidCtlLib as vidlib

        CLSID_AviSplitter = GUID("{1b544c20-fd0b-11ce-8c63-00aa0044b51e}")

        avisplitter = comtypes.client.CreateObject(
            CLSID_AviSplitter,
            interface=vidlib.IBaseFilter,
        )
        pinEnum = avisplitter.EnumPins()
        self.assertIsInstance(pinEnum, POINTER(vidlib.IEnumPins))
        # make sure pinEnum is iterable and non-empty
        pins = list(pinEnum)
        self.assertGreater(len(pins), 0)


if __name__ == "__main__":
    ut.main()
