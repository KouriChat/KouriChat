import ctypes
import unittest as ut
from unittest import mock

from comtypes import automation, COMError, IUnknown
from comtypes.client import CreateObject, dynamic, GetModule, lazybind


class Test_Dispatch_Function(ut.TestCase):
    # It is difficult to cause intentionally errors "in the regular way".
    # So `mock` is used to cover conditional branches.
    def test_returns_dynamic_Dispatch_if_takes_dynamic_Dispatch(self):
        obj = mock.MagicMock(spec=dynamic._Dispatch)
        self.assertIs(dynamic.Dispatch(obj), obj)

    def test_returns_lazybind_Dispatch_if_takes_ptrIDispatch(self):
        # Conditional branches that return `lazybind.Dispatch` are also covered by
        # `test_dyndispatch` and others.
        obj = mock.MagicMock(spec=ctypes.POINTER(automation.IDispatch))
        self.assertIsInstance(dynamic.Dispatch(obj), lazybind.Dispatch)

    def test_returns_dynamic_Dispatch_if_takes_ptrIDispatch_and_raised_comerr(self):
        obj = mock.MagicMock(spec=ctypes.POINTER(automation.IDispatch))
        obj.GetTypeInfo.side_effect = COMError(0, "test", ("", "", "", 0, 0))
        self.assertIsInstance(dynamic.Dispatch(obj), dynamic._Dispatch)

    def test_returns_dynamic_Dispatch_if_takes_ptrIDispatch_and_raised_winerr(self):
        obj = mock.MagicMock(spec=ctypes.POINTER(automation.IDispatch))
        obj.GetTypeInfo.side_effect = WindowsError()
        self.assertIsInstance(dynamic.Dispatch(obj), dynamic._Dispatch)

    def test_returns_what_is_took_if_takes_other(self):
        obj = object()
        self.assertIs(dynamic.Dispatch(obj), obj)


class Test_Dispatch_Class(ut.TestCase):
    # `MethodCaller` and `_Collection` are indirectly covered in this.
    def test_dict(self):
        # The following conditional branches are not covered;
        # - not `hresult in ERRORS_BAD_CONTEXT`
        # - not `0 != enum.Skip(index)`
        # - other than `COMError` raises in `__getattr__`
        orig = CreateObject("Scripting.Dictionary", interface=automation.IDispatch)
        d = dynamic._Dispatch(orig)
        d.CompareMode = 42
        d.Item["foo"] = 1
        d.Item["bar"] = "spam foo"
        d.Item["baz"] = 3.14
        self.assertEqual(d[0], "foo")
        self.assertEqual(d.Item["foo"], 1)
        self.assertEqual([k for k in iter(d)], ["foo", "bar", "baz"])
        self.assertIsInstance(hash(d), int)
        d._FlagAsMethod("_NewEnum")
        self.assertIs(type(d._NewEnum()), ctypes.POINTER(IUnknown))
        scrrun = GetModule("scrrun.dll")
        scr_dict = d.QueryInterface(scrrun.IDictionary)
        self.assertIsInstance(scr_dict, scrrun.IDictionary)
        d.Item["qux"] = scr_dict
        with self.assertRaises(IndexError):
            d[4]
        with self.assertRaises(AttributeError):
            d.__foo__


if __name__ == "__main__":
    ut.main()
