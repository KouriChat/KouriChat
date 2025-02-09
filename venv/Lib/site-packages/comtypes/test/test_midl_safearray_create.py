# coding: utf-8

from ctypes import c_int, pointer, HRESULT, POINTER
import unittest

import comtypes
import comtypes.safearray
from comtypes import CLSCTX_INPROC_SERVER, CLSCTX_LOCAL_SERVER
from comtypes.client import CreateObject, GetModule
import comtypes.typeinfo

GetModule("UIAutomationCore.dll")
from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation

ComtypesCppTestSrvLib_GUID = "{07D2AEE5-1DF8-4D2C-953A-554ADFD25F99}"

try:
    GetModule((ComtypesCppTestSrvLib_GUID, 1, 0, 0))
    from comtypes.gen.ComtypesCppTestSrvLib import StructRecordParamTest
    from comtypes.gen.ComtypesCppTestSrvLib import IDispSafearrayParamTest

    IMPORT_FAILED = False
except (ImportError, OSError):
    IMPORT_FAILED = True


class Test_midlSAFEARRAY_create(unittest.TestCase):
    def test_iunk(self):
        extra = pointer(IUIAutomation._iid_)
        iuia = CreateObject(
            CUIAutomation().IPersist_GetClassID(),
            interface=IUIAutomation,
            clsctx=CLSCTX_INPROC_SERVER,
        )
        sa_type = comtypes.safearray._midlSAFEARRAY(POINTER(IUIAutomation))
        for ptn, sa in [
            ("with extra", sa_type.create([iuia], extra=extra)),
            ("without extra", sa_type.create([iuia])),
        ]:
            with self.subTest(ptn=ptn):
                (unpacked,) = sa.unpack()
                self.assertIsInstance(unpacked, POINTER(IUIAutomation))

    @unittest.skipIf(IMPORT_FAILED, "This depends on the out of process COM-server.")
    def test_idisp(self):
        extra = pointer(IDispSafearrayParamTest._iid_)
        idisp = CreateObject(
            "Comtypes.DispSafearrayParamTest",
            clsctx=CLSCTX_LOCAL_SERVER,
            interface=IDispSafearrayParamTest,
        )
        sa_type = comtypes.safearray._midlSAFEARRAY(POINTER(IDispSafearrayParamTest))
        for ptn, sa in [
            ("with extra", sa_type.create([idisp], extra=extra)),
            ("without extra", sa_type.create([idisp])),
        ]:
            with self.subTest(ptn=ptn):
                (unpacked,) = sa.unpack()
                self.assertIsInstance(unpacked, POINTER(IDispSafearrayParamTest))

    @unittest.skipIf(IMPORT_FAILED, "This depends on the out of process COM-server.")
    def test_record(self):
        extra = comtypes.typeinfo.GetRecordInfoFromGuids(
            *StructRecordParamTest._recordinfo_
        )
        record = StructRecordParamTest()
        record.question = "The meaning of life, the universe and everything?"
        record.answer = 42
        record.needs_clarification = True
        sa_type = comtypes.safearray._midlSAFEARRAY(StructRecordParamTest)
        for ptn, sa in [
            ("with extra", sa_type.create([record], extra=extra)),
            ("without extra", sa_type.create([record])),
        ]:
            with self.subTest(ptn=ptn):
                (unpacked,) = sa.unpack()
                self.assertIsInstance(unpacked, StructRecordParamTest)
                self.assertEqual(
                    unpacked.question,
                    "The meaning of life, the universe and everything?",
                )
                self.assertEqual(unpacked.answer, 42)
                self.assertEqual(unpacked.needs_clarification, True)

    def test_HRESULT(self):
        hr = HRESULT(1)
        sa_type = comtypes.safearray._midlSAFEARRAY(HRESULT)
        with self.assertRaises(TypeError):
            sa_type.create([hr], extra=None)
        with self.assertRaises(TypeError):
            sa_type.create([hr])

    def test_ctype(self):
        extra = None
        cdata = c_int(1)
        sa_type = comtypes.safearray._midlSAFEARRAY(c_int)
        for ptn, sa in [
            ("with extra", sa_type.create([cdata], extra=extra)),
            ("without extra", sa_type.create([cdata])),
        ]:
            with self.subTest(ptn=ptn):
                (unpacked,) = sa.unpack()
                self.assertIsInstance(unpacked, int)
                self.assertEqual(unpacked, 1)


if __name__ == "__main__":
    unittest.main()
