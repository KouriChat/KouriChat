import unittest as ut

from ctypes import POINTER, byref, c_bool, c_ubyte, c_ulonglong, oledll, pointer
import comtypes
import comtypes.client

comtypes.client.GetModule("portabledeviceapi.dll")
from comtypes.gen.PortableDeviceApiLib import IStream


STGC_DEFAULT = 0
STREAM_SEEK_SET = 0
STREAM_SEEK_CUR = 1
STREAM_SEEK_END = 2


def _create_stream() -> IStream:
    # Create an IStream
    stream = POINTER(IStream)()  # type: ignore
    comtypes._ole32.CreateStreamOnHGlobal(None, c_bool(True), byref(stream))
    return stream  # type: ignore


class Test_RemoteWrite(ut.TestCase):
    def test_RemoteWrite(self):
        stream = _create_stream()
        test_data = "Some data".encode("utf-8")
        pv = (c_ubyte * len(test_data)).from_buffer(bytearray(test_data))

        written = stream.RemoteWrite(pv, len(test_data))

        # Verification
        self.assertEqual(written, len(test_data))


class Test_RemoteRead(ut.TestCase):
    def test_RemoteRead(self):
        stream = _create_stream()
        test_data = "Some data".encode("utf-8")
        pv = (c_ubyte * len(test_data)).from_buffer(bytearray(test_data))
        stream.RemoteWrite(pv, len(test_data))

        # Make sure the data actually gets written before trying to read back
        stream.Commit(STGC_DEFAULT)
        # Move the stream back to the beginning
        stream.RemoteSeek(0, STREAM_SEEK_SET)

        buffer_size = 1024

        read_buffer, data_read = stream.RemoteRead(buffer_size)

        # Verification
        self.assertEqual(data_read, len(test_data))
        self.assertEqual(bytearray(read_buffer)[0:data_read], test_data)


class Test_RemoteSeek(ut.TestCase):
    def _create_sample_stream(self) -> IStream:
        stream = _create_stream()
        test_data = b"spam egg bacon ham"
        pv = (c_ubyte * len(test_data)).from_buffer(bytearray(test_data))
        stream.RemoteWrite(pv, len(test_data))
        stream.Commit(STGC_DEFAULT)
        return stream

    def test_takes_STREAM_SEEK_SET_as_origin(self):
        stream = self._create_sample_stream()
        newpos = stream.RemoteSeek(9, STREAM_SEEK_SET)
        self.assertEqual(newpos, 9)
        buf, read = stream.RemoteRead(1024)
        self.assertEqual(bytearray(buf)[0:read], b"bacon ham")

    def test_takes_STREAM_SEEK_CUR_as_origin(self):
        stream = self._create_sample_stream()
        stream.RemoteSeek(8, STREAM_SEEK_SET)
        newpos = stream.RemoteSeek(7, STREAM_SEEK_CUR)
        self.assertEqual(newpos, 15)
        buf, read = stream.RemoteRead(1024)
        self.assertEqual(bytearray(buf)[0:read], b"ham")

    def test_takes_STREAM_SEEK_END_as_origin(self):
        stream = self._create_sample_stream()
        stream.RemoteSeek(8, STREAM_SEEK_SET)
        newpos = stream.RemoteSeek(-13, STREAM_SEEK_END)
        self.assertEqual(newpos, 5)
        buf, read = stream.RemoteRead(1024)
        self.assertEqual(bytearray(buf)[0:read], b"egg bacon ham")


class Test_SetSize(ut.TestCase):
    def test_SetSize(self):
        stream = _create_stream()
        stream.SetSize(42)
        pui = pointer(c_ulonglong())
        oledll.shlwapi.IStream_Size(stream, pui)
        self.assertEqual(pui.contents.value, 42)


class Test_RemoteCopyTo(ut.TestCase):
    def test_RemoteCopyTo(self):
        src = _create_stream()
        dst = _create_stream()
        test_data = b"parrot"
        pv = (c_ubyte * len(test_data)).from_buffer(bytearray(test_data))
        src_written = src.RemoteWrite(pv, len(test_data))
        src.Commit(STGC_DEFAULT)
        src.RemoteSeek(0, STREAM_SEEK_SET)
        cpy_read, cpy_written = src.RemoteCopyTo(dst, src_written)
        self.assertEqual(cpy_read, len(test_data))
        self.assertEqual(cpy_written, len(test_data))
        dst.Commit(STGC_DEFAULT)
        dst.RemoteSeek(0, STREAM_SEEK_SET)
        dst_buf, dst_read = dst.RemoteRead(1024)
        self.assertEqual(bytearray(dst_buf)[0:dst_read], test_data)


class Test_Clone(ut.TestCase):
    def test_Clone(self):
        orig = _create_stream()
        test_data = b"spam egg bacon ham"
        pv = (c_ubyte * len(test_data)).from_buffer(bytearray(test_data))
        orig.RemoteWrite(pv, len(test_data))
        orig.Commit(STGC_DEFAULT)
        orig.RemoteSeek(0, STREAM_SEEK_SET)
        new_stm = orig.Clone()
        buf, read = new_stm.RemoteRead(1024)
        self.assertEqual(bytearray(buf)[0:read], test_data)


if __name__ == "__main__":
    ut.main()
