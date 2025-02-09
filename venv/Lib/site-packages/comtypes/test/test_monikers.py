from _ctypes import COMError
from ctypes import byref, POINTER
import contextlib
import unittest

import comtypes
from comtypes.client import GetModule, CreateObject
from comtypes import hresult, GUID

with contextlib.redirect_stdout(None):  # supress warnings
    GetModule("msvidctl.dll")
from comtypes.gen import MSVidCtlLib as msvidctl
from comtypes.gen.MSVidCtlLib import IBindCtx, IMoniker, IRunningObjectTable


MKSYS_ITEMMONIKER = 4
ROTFLAGS_ALLOWANYCLIENT = 1


def _create_item_moniker(delim: str, item: str) -> IMoniker:
    mon = POINTER(IMoniker)()
    comtypes._ole32.CreateItemMoniker(delim, item, byref(mon))
    return mon  # type: ignore


def _create_bctx() -> IBindCtx:
    bctx = POINTER(IBindCtx)()
    # The first parameter is reserved and must be 0.
    comtypes._ole32.CreateBindCtx(0, byref(bctx))
    return bctx  # type: ignore


def _create_rot() -> IRunningObjectTable:
    rot = POINTER(IRunningObjectTable)()
    # The first parameter is reserved and must be 0.
    comtypes._ole32.GetRunningObjectTable(0, byref(rot))
    return rot  # type: ignore


class Test_IMoniker(unittest.TestCase):
    def test_IsSystemMoniker(self):
        item_id = str(GUID.create_new())
        mon = _create_item_moniker("!", item_id)
        self.assertEqual(mon.IsSystemMoniker(), MKSYS_ITEMMONIKER)


class Test_IBindCtx(unittest.TestCase):
    def test_EnumObjectParam(self):
        bctx = _create_bctx()
        with self.assertRaises(COMError) as err_ctx:
            # calling `EnumObjectParam` results in a return value of E_NOTIMPL.
            # https://learn.microsoft.com/en-us/windows/win32/api/objidl/nf-objidl-ibindctx-enumobjectparam#notes-to-callers
            bctx.EnumObjectParam()
        self.assertEqual(err_ctx.exception.hresult, hresult.E_NOTIMPL)


class Test_IRunningObjectTable(unittest.TestCase):
    def test_register_and_revoke_item_moniker(self):
        vidctl = CreateObject(msvidctl.MSVidCtl, interface=msvidctl.IMSVidCtl)
        item_id = str(GUID.create_new())
        mon = _create_item_moniker("!", item_id)
        rot = _create_rot()
        bctx = _create_bctx()
        self.assertEqual(mon.IsRunning(bctx, None, None), hresult.S_FALSE)
        dw_reg = rot.Register(ROTFLAGS_ALLOWANYCLIENT, vidctl, mon)
        self.assertEqual(mon.IsRunning(bctx, None, None), hresult.S_OK)
        self.assertEqual(f"!{item_id}", mon.GetDisplayName(bctx, None))
        self.assertEqual(rot.GetObject(mon).QueryInterface(msvidctl.IMSVidCtl), vidctl)
        rot.Revoke(dw_reg)
        self.assertEqual(mon.IsRunning(bctx, None, None), hresult.S_FALSE)
