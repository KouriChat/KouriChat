# coding: utf-8

import unittest

from comtypes import CLSCTX_LOCAL_SERVER
from comtypes.client import CreateObject, GetModule
from ctypes import byref, pointer

ComtypesCppTestSrvLib_GUID = "{07D2AEE5-1DF8-4D2C-953A-554ADFD25F99}"

try:
    GetModule((ComtypesCppTestSrvLib_GUID, 1, 0, 0))
    import comtypes.gen.ComtypesCppTestSrvLib as ComtypesCppTestSrvLib

    IMPORT_FAILED = False
except (ImportError, OSError):
    IMPORT_FAILED = True


@unittest.skipIf(IMPORT_FAILED, "This depends on the out of process COM-server.")
class Test_DispMethods(unittest.TestCase):
    """Test dispmethods with record and record pointer parameters."""

    EXPECTED_INITED_QUESTIONS = "The meaning of life, the universe and everything?"

    def _create_dispifc(self) -> "ComtypesCppTestSrvLib.IDispRecordParamTest":
        # Explicitely ask for the dispinterface of the component.
        return CreateObject(
            "Comtypes.DispRecordParamTest",
            clsctx=CLSCTX_LOCAL_SERVER,
            interface=ComtypesCppTestSrvLib.IDispRecordParamTest,
        )

    def test_inout_byref(self):
        dispifc = self._create_dispifc()
        # Passing a record by reference to a method that has declared the parameter
        # as [in, out] we expect modifications of the record on the server side to
        # also change the record on the client side.
        test_record = ComtypesCppTestSrvLib.StructRecordParamTest()
        self.assertEqual(test_record.question, None)
        self.assertEqual(test_record.answer, 0)
        self.assertEqual(test_record.needs_clarification, False)
        dispifc.InitRecord(byref(test_record))
        self.assertEqual(test_record.question, self.EXPECTED_INITED_QUESTIONS)
        self.assertEqual(test_record.answer, 42)
        self.assertEqual(test_record.needs_clarification, True)

    def test_inout_pointer(self):
        dispifc = self._create_dispifc()
        # Passing a record pointer to a method that has declared the parameter
        # as [in, out] we expect modifications of the record on the server side to
        # also change the record on the client side.
        test_record = ComtypesCppTestSrvLib.StructRecordParamTest()
        self.assertEqual(test_record.question, None)
        self.assertEqual(test_record.answer, 0)
        self.assertEqual(test_record.needs_clarification, False)
        dispifc.InitRecord(pointer(test_record))
        self.assertEqual(test_record.question, self.EXPECTED_INITED_QUESTIONS)
        self.assertEqual(test_record.answer, 42)
        self.assertEqual(test_record.needs_clarification, True)

    def test_in_record(self):
        # Passing a record to a method that has declared the parameter just as [in]
        # we expect modifications of the record on the server side NOT to change
        # the record on the client side.
        # We also need to test if the record gets properly passed to the method on
        # the server side. For this, the 'VerifyRecord' method returns 'True' if
        # all record fields have values equivalent to the initialization values
        # provided by 'InitRecord'.
        inited_record = ComtypesCppTestSrvLib.StructRecordParamTest()
        inited_record.question = self.EXPECTED_INITED_QUESTIONS
        inited_record.answer = 42
        inited_record.needs_clarification = True
        for rec, expected, (q, a, nc) in [
            (inited_record, True, (self.EXPECTED_INITED_QUESTIONS, 42, True)),
            # Also perform the inverted test. For this, create a blank record.
            (ComtypesCppTestSrvLib.StructRecordParamTest(), False, (None, 0, False)),
        ]:
            with self.subTest(expected=expected, q=q, a=a, nc=nc):
                # Perform the check on initialization values.
                self.assertEqual(self._create_dispifc().VerifyRecord(rec), expected)
                self.assertEqual(rec.question, q)
                # Check if the 'answer' field is unchanged although the method
                # modifies this field on the server side.
                self.assertEqual(rec.answer, a)
                self.assertEqual(rec.needs_clarification, nc)


if __name__ == "__main__":
    unittest.main()
