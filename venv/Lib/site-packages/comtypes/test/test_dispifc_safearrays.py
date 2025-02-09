# coding: utf-8

from ctypes import byref, c_double, pointer
import unittest

import comtypes
import comtypes.safearray
from comtypes import CLSCTX_LOCAL_SERVER
from comtypes.client import CreateObject, GetModule

ComtypesCppTestSrvLib_GUID = "{07D2AEE5-1DF8-4D2C-953A-554ADFD25F99}"

try:
    GetModule((ComtypesCppTestSrvLib_GUID, 1, 0, 0))
    import comtypes.gen.ComtypesCppTestSrvLib as ComtypesCppTestSrvLib

    IMPORT_FAILED = False
except (ImportError, OSError):
    IMPORT_FAILED = True


@unittest.skipIf(IMPORT_FAILED, "This depends on the out of process COM-server.")
class Test_DispMethods(unittest.TestCase):
    """Test dispmethods with safearray and safearray pointer parameters."""

    UNPACKED_ZERO_VALS = tuple(0.0 for _ in range(10))
    UNPACKED_CONSECUTIVE_VALS = tuple(float(i) for i in range(10))

    def _create_dispifc(self) -> "ComtypesCppTestSrvLib.IDispSafearrayParamTest":
        # Explicitely ask for the dispinterface of the component.
        return CreateObject(
            "Comtypes.DispSafearrayParamTest",
            clsctx=CLSCTX_LOCAL_SERVER,
            interface=ComtypesCppTestSrvLib.IDispSafearrayParamTest,
        )

    def _create_zero_array(self):
        return comtypes.safearray._midlSAFEARRAY(c_double).create(
            [c_double() for _ in range(10)]
        )

    def _create_consecutive_array(self):
        return comtypes.safearray._midlSAFEARRAY(c_double).create(
            [c_double(i) for i in range(10)]
        )

    def test_inout_byref(self):
        dispifc = self._create_dispifc()
        # Passing a safearray by reference to a method that has declared the parameter
        # as [in, out] we expect modifications of the safearray on the server side to
        # also change the safearray on the client side.
        test_array = self._create_zero_array()
        self.assertEqual(test_array.unpack(), self.UNPACKED_ZERO_VALS)
        dispifc.InitArray(byref(test_array))
        self.assertEqual(test_array.unpack(), self.UNPACKED_CONSECUTIVE_VALS)

    def test_inout_pointer(self):
        dispifc = self._create_dispifc()
        # Passing a safearray pointer to a method that has declared the parameter
        # as [in, out] we expect modifications of the safearray on the server side to
        # also change the safearray on the client side.
        test_array = self._create_zero_array()
        self.assertEqual(test_array.unpack(), self.UNPACKED_ZERO_VALS)
        dispifc.InitArray(pointer(test_array))
        self.assertEqual(test_array.unpack(), self.UNPACKED_CONSECUTIVE_VALS)

    def test_in_safearray(self):
        # Passing a safearray to a method that has declared the parameter just as [in]
        # we expect modifications of the safearray on the server side NOT to change
        # the safearray on the client side.
        # We also need to test if the safearray gets properly passed to the method on
        # the server side. For this, the 'VerifyArray' method returns 'True' if
        # the safearray items have values equal to the initialization values
        # provided by 'InitArray'.
        for sa, expected, unpacked_content in [
            (self._create_consecutive_array(), True, self.UNPACKED_CONSECUTIVE_VALS),
            # Also perform the inverted test. For this, create a safearray with zeros.
            (self._create_zero_array(), False, self.UNPACKED_ZERO_VALS),
        ]:
            with self.subTest(expected=expected, unpacked_content=unpacked_content):
                # Perform the check on initialization values.
                self.assertEqual(self._create_dispifc().VerifyArray(sa), expected)
                # Check if the safearray is unchanged although the method
                # modifies the safearray on the server side.
                self.assertEqual(sa.unpack(), unpacked_content)


if __name__ == "__main__":
    unittest.main()
