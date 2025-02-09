from _ctypes import COMError
from ctypes import byref, c_ubyte, POINTER
import contextlib
from pathlib import Path
import unittest

import comtypes
import comtypes.client


with contextlib.redirect_stdout(None):  # supress warnings
    mod = comtypes.client.GetModule("msvidctl.dll")

from comtypes.gen.MSVidCtlLib import IStorage


STATFLAG_DEFAULT = 0
STGC_DEFAULT = 0
STGM_CREATE = 0x00001000
STGM_DIRECT = 0x00000000
STGM_DELETEONRELEASE = 0x04000000
STGM_READ = 0x00000000
STGM_READWRITE = 0x00000002
STGM_SHARE_EXCLUSIVE = 0x00000010
STGM_TRANSACTED = 0x00010000
STGMOVE_MOVE = 0
STREAM_SEEK_SET = 0

STG_E_PATHNOTFOUND = -2147287038


class Test_IStorage(unittest.TestCase):
    CREATE_DOC_FLAG = (
        STGM_DIRECT
        | STGM_READWRITE
        | STGM_CREATE
        | STGM_SHARE_EXCLUSIVE
        | STGM_DELETEONRELEASE
    )
    CREATE_STM_FLAG = STGM_CREATE | STGM_READWRITE | STGM_SHARE_EXCLUSIVE
    OPEN_STM_FLAG = STGM_READ | STGM_SHARE_EXCLUSIVE
    CREATE_STG_FLAG = STGM_TRANSACTED | STGM_READWRITE | STGM_SHARE_EXCLUSIVE
    OPEN_STG_FLAG = STGM_TRANSACTED | STGM_READWRITE | STGM_SHARE_EXCLUSIVE

    def _create_docfile(self) -> IStorage:
        stg = POINTER(IStorage)()
        comtypes._ole32.StgCreateDocfile(None, self.CREATE_DOC_FLAG, 0, byref(stg))
        return stg  # type: ignore

    def test_CreateStream(self):
        storage = self._create_docfile()
        filepath = Path(storage.Stat(STATFLAG_DEFAULT).pwcsName)
        self.assertTrue(filepath.exists())
        stream = storage.CreateStream("example", self.CREATE_STM_FLAG, 0, 0)
        test_data = "Some data".encode("utf-8")
        pv = (c_ubyte * len(test_data)).from_buffer(bytearray(test_data))
        stream.RemoteWrite(pv, len(test_data))
        stream.Commit(STGC_DEFAULT)
        stream.RemoteSeek(0, STREAM_SEEK_SET)
        read_buffer, data_read = stream.RemoteRead(1024)
        self.assertEqual(bytearray(read_buffer)[0:data_read], test_data)
        storage.Commit(STGC_DEFAULT)
        self.assertTrue(filepath.exists())
        del storage
        self.assertFalse(filepath.exists())

    def test_CreateStorage(self):
        parent = self._create_docfile()
        child = parent.CreateStorage("child", self.CREATE_STG_FLAG, 0, 0)
        self.assertEqual("child", child.Stat(STATFLAG_DEFAULT).pwcsName)

    def test_OpenStorage(self):
        parent = self._create_docfile()
        created_child = parent.CreateStorage("child", self.CREATE_STG_FLAG, 0, 0)
        del created_child
        opened_child = parent.OpenStorage("child", None, self.OPEN_STG_FLAG, None, 0)
        self.assertEqual("child", opened_child.Stat(STATFLAG_DEFAULT).pwcsName)

    def test_RemoteCopyTo(self):
        src_stg = self._create_docfile()
        src_stg.CreateStorage("child", self.CREATE_STG_FLAG, 0, 0)
        dst_stg = self._create_docfile()
        src_stg.RemoteCopyTo(0, None, None, dst_stg)
        src_stg.Commit(STGC_DEFAULT)
        del src_stg
        opened_stg = dst_stg.OpenStorage("child", None, self.OPEN_STG_FLAG, None, 0)
        self.assertEqual("child", opened_stg.Stat(STATFLAG_DEFAULT).pwcsName)

    def test_MoveElementTo(self):
        src_stg = self._create_docfile()
        src_stg.CreateStorage("foo", self.CREATE_STG_FLAG, 0, 0)
        dst_stg = self._create_docfile()
        src_stg.MoveElementTo("foo", dst_stg, "bar", STGMOVE_MOVE)
        opened_stg = dst_stg.OpenStorage("bar", None, self.OPEN_STG_FLAG, None, 0)
        self.assertEqual("bar", opened_stg.Stat(STATFLAG_DEFAULT).pwcsName)
        with self.assertRaises(COMError) as ctx:
            src_stg.OpenStorage("foo", None, self.OPEN_STG_FLAG, None, 0)
        self.assertEqual(ctx.exception.hresult, STG_E_PATHNOTFOUND)

    def test_Revert(self):
        storage = self._create_docfile()
        foo = storage.CreateStorage("foo", self.CREATE_STG_FLAG, 0, 0)
        foo.CreateStorage("bar", self.CREATE_STG_FLAG, 0, 0)
        bar = foo.OpenStorage("bar", None, self.OPEN_STG_FLAG, None, 0)
        self.assertEqual("bar", bar.Stat(STATFLAG_DEFAULT).pwcsName)
        foo.Revert()
        with self.assertRaises(COMError) as ctx:
            foo.OpenStorage("bar", None, self.OPEN_STG_FLAG, None, 0)
        self.assertEqual(ctx.exception.hresult, STG_E_PATHNOTFOUND)

    def test_DestroyElement(self):
        storage = self._create_docfile()
        storage.CreateStorage("example", self.CREATE_STG_FLAG, 0, 0)
        storage.DestroyElement("example")
        with self.assertRaises(COMError) as ctx:
            storage.OpenStorage("example", None, self.OPEN_STG_FLAG, None, 0)
        self.assertEqual(ctx.exception.hresult, STG_E_PATHNOTFOUND)

    def test_RenameElement(self):
        storage = self._create_docfile()
        storage.CreateStorage("example", self.CREATE_STG_FLAG, 0, 0)
        storage.RenameElement("example", "sample")
        sample = storage.OpenStorage("sample", None, self.OPEN_STG_FLAG, None, 0)
        self.assertEqual("sample", sample.Stat(STATFLAG_DEFAULT).pwcsName)
        with self.assertRaises(COMError) as ctx:
            storage.OpenStorage("example", None, self.OPEN_STG_FLAG, None, 0)
        self.assertEqual(ctx.exception.hresult, STG_E_PATHNOTFOUND)
