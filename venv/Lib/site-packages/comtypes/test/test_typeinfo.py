import os
import unittest
from ctypes import POINTER, byref
from comtypes import GUID, COMError
from comtypes.automation import DISPATCH_METHOD
from comtypes.typeinfo import (
    LoadTypeLibEx,
    LoadRegTypeLib,
    QueryPathOfRegTypeLib,
    TKIND_INTERFACE,
    TKIND_DISPATCH,
    TKIND_ENUM,
)


class Test(unittest.TestCase):
    def test_LoadTypeLibEx(self):
        dllname = "scrrun.dll"
        with self.assertRaises(WindowsError):
            LoadTypeLibEx("<xxx.xx>")
        tlib = LoadTypeLibEx(dllname)
        self.assertTrue(tlib.GetTypeInfoCount())
        tlib.GetDocumentation(-1)
        self.assertEqual(tlib.IsName("ifile"), "IFile")
        self.assertEqual(tlib.IsName("IFILE"), "IFile")
        self.assertTrue(tlib.FindName("IFile"))
        self.assertEqual(tlib.IsName("Spam"), None)
        tlib.GetTypeComp()

    def test_LoadRegTypeLib(self):
        tlib = LoadTypeLibEx("scrrun.dll")
        attr = tlib.GetLibAttr()
        info = attr.guid, attr.wMajorVerNum, attr.wMinorVerNum
        other_tlib = LoadRegTypeLib(*info)
        self.assert_tlibattr_equal(tlib, other_tlib)

    def assert_tlibattr_equal(self, tlib, other_tlib):
        attr, other_attr = tlib.GetLibAttr(), other_tlib.GetLibAttr()
        # `assert tlib == other_tlib` will fail in some environments.
        # But their attributes are equal even if difference of environments.
        self.assertEqual(attr.guid, other_attr.guid)
        self.assertEqual(attr.wMajorVerNum, other_attr.wMajorVerNum)
        self.assertEqual(attr.wMinorVerNum, other_attr.wMinorVerNum)
        self.assertEqual(attr.lcid, other_attr.lcid)
        self.assertEqual(attr.wLibFlags, other_attr.wLibFlags)

        # for n in dir(attr):
        #     if not n.startswith("_"):
        #         print "\t", n, getattr(attr, n)

    def test_QueryPathOfRegTypeLib(self):
        dllname = "scrrun.dll"
        tlib = LoadTypeLibEx(dllname)
        attr = tlib.GetLibAttr()
        info = attr.guid, attr.wMajorVerNum, attr.wMinorVerNum
        path = QueryPathOfRegTypeLib(*info)
        path = path.split("\0")[0]
        self.assertTrue(path.lower().endswith(dllname))

    def test_TypeInfo(self):
        tlib = LoadTypeLibEx("scrrun.dll")
        for index in range(tlib.GetTypeInfoCount()):
            ti = tlib.GetTypeInfo(index)
            ta = ti.GetTypeAttr()
            ti.GetDocumentation(-1)
            c_tlib, c_index = ti.GetContainingTypeLib()
            self.assert_tlibattr_equal(c_tlib, tlib)
            self.assertEqual(c_index, index)
            if ta.typekind in (TKIND_INTERFACE, TKIND_DISPATCH):
                if ta.cImplTypes:
                    href = ti.GetRefTypeOfImplType(0)
                    base = ti.GetRefTypeInfo(href)
                    base.GetDocumentation(-1)
                    ti.GetImplTypeFlags(0)
            for f in range(ta.cFuncs):
                fd = ti.GetFuncDesc(f)
                names = ti.GetNames(fd.memid, 32)
                ti.GetIDsOfNames(*names)
                ti.GetMops(fd.memid)

            for v in range(ta.cVars):
                ti.GetVarDesc(v)

        guid_null = GUID()
        with self.assertRaises(COMError):
            tlib.GetTypeInfoOfGuid(guid_null)

        guid = GUID("{C7C3F5A4-88A3-11D0-ABCB-00A0C90FFFC0}")
        ti = tlib.GetTypeInfoOfGuid(guid)
        c_tlib, c_index = ti.GetContainingTypeLib()
        c_ti = c_tlib.GetTypeInfo(c_index)
        self.assert_tlibattr_equal(c_tlib, tlib)
        self.assertEqual(c_ti, ti)
        self.assertEqual(guid, ti.GetTypeAttr().guid)


if __name__ == "__main__":
    unittest.main()
