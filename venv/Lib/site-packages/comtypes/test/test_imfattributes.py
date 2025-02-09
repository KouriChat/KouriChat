import contextlib
import unittest as ut

from ctypes import POINTER, pointer, windll
from comtypes import GUID
import comtypes.client


class Test_IMFAttributes(ut.TestCase):
    def test_imfattributes(self):
        with contextlib.redirect_stdout(None):  # supress warnings, see test_client.py
            comtypes.client.GetModule("msvidctl.dll")
        from comtypes.gen import MSVidCtlLib

        imf_attrs = POINTER(MSVidCtlLib.IMFAttributes)()
        hres = windll.mfplat.MFCreateAttributes(pointer(imf_attrs), 2)
        self.assertEqual(hres, 0)

        MF_TRANSCODE_ADJUST_PROFILE = GUID("{9c37c21b-060f-487c-a690-80d7f50d1c72}")
        set_int_value = 1
        # IMFAttributes.SetUINT32() is an example of a function that has a parameter
        # without an `in` or `out` direction; see also test_inout_args.py
        imf_attrs.SetUINT32(MF_TRANSCODE_ADJUST_PROFILE, set_int_value)
        get_int_value = imf_attrs.GetUINT32(MF_TRANSCODE_ADJUST_PROFILE)
        self.assertEqual(set_int_value, get_int_value)


if __name__ == "__main__":
    ut.main()
