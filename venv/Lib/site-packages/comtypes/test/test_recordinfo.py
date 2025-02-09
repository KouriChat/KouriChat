# coding: utf-8

import unittest

from comtypes import typeinfo
from comtypes.client import GetModule
from ctypes import byref, pointer, sizeof

ComtypesCppTestSrvLib_GUID = "{07D2AEE5-1DF8-4D2C-953A-554ADFD25F99}"

try:
    GetModule((ComtypesCppTestSrvLib_GUID, 1, 0, 0))
    from comtypes.gen.ComtypesCppTestSrvLib import StructRecordParamTest

    IMPORT_FAILED = False
except (ImportError, OSError):
    IMPORT_FAILED = True


def _create_recordinfo() -> typeinfo.IRecordInfo:
    return typeinfo.GetRecordInfoFromGuids(*StructRecordParamTest._recordinfo_)


def _create_record(
    question: str, answer: int, needs_clarification: bool
) -> "StructRecordParamTest":
    record = StructRecordParamTest()
    record.question = question
    record.answer = answer
    record.needs_clarification = needs_clarification
    return record


@unittest.skipIf(IMPORT_FAILED, "This depends on the out of process COM-server.")
class Test_IRecordInfo(unittest.TestCase):
    def test_RecordCopy(self):
        dst_rec = StructRecordParamTest()
        ri = _create_recordinfo()
        ri.RecordCopy(pointer(_create_record("foo", 3, True)), byref(dst_rec))
        self.assertEqual(dst_rec.question, "foo")
        self.assertEqual(dst_rec.answer, 3)
        self.assertEqual(dst_rec.needs_clarification, True)

    def test_GetGuid(self):
        *_, expected_guid = StructRecordParamTest._recordinfo_
        self.assertEqual(str(_create_recordinfo().GetGuid()), expected_guid)

    def test_GetName(self):
        self.assertEqual(
            _create_recordinfo().GetName(),
            StructRecordParamTest.__qualname__,
        )

    def test_GetSize(self):
        self.assertEqual(
            _create_recordinfo().GetSize(),
            sizeof(StructRecordParamTest),
        )

    def test_GetTypeInfo(self):
        ta = _create_recordinfo().GetTypeInfo().GetTypeAttr()
        *_, expected_guid = StructRecordParamTest._recordinfo_
        self.assertEqual(str(ta.guid), expected_guid)

    def test_IsMatchingType(self):
        ri = _create_recordinfo()
        ti = ri.GetTypeInfo()
        self.assertTrue(typeinfo.GetRecordInfoFromTypeInfo(ti).IsMatchingType(ri))

    def test_RecordCreateCopy(self):
        ri = _create_recordinfo()
        actual = ri.RecordCreateCopy(byref(_create_record("foo", 3, True)))
        self.assertIsInstance(actual, int)
        dst_rec = StructRecordParamTest()
        ri.RecordCopy(actual, byref(dst_rec))
        ri.RecordDestroy(actual)
        self.assertEqual(dst_rec.question, "foo")
        self.assertEqual(dst_rec.answer, 3)
        self.assertEqual(dst_rec.needs_clarification, True)
