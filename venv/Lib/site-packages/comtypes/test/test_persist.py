from pathlib import Path
import tempfile
import unittest as ut

from comtypes import CoCreateInstance, GUID, IPersist
from comtypes import persist


CLSID_ShellLink = GUID("{00021401-0000-0000-C000-000000000046}")


class Test_IPersist(ut.TestCase):
    def test_GetClassID(self):
        p = CoCreateInstance(CLSID_ShellLink).QueryInterface(IPersist)
        self.assertEqual(p.GetClassID(), CLSID_ShellLink)


class Test_IPersistFile(ut.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.tmp_dir = Path(td.name)

    def _create_pf(self) -> persist.IPersistFile:
        return CoCreateInstance(CLSID_ShellLink).QueryInterface(persist.IPersistFile)

    def test_load(self):
        pf = self._create_pf()
        tgt_file = (self.tmp_dir / "tgt.txt").resolve()
        tgt_file.touch()
        pf.Load(str(tgt_file), persist.STGM_DIRECT)
        self.assertEqual(pf.GetCurFile(), str(tgt_file))

    def test_save(self):
        pf = self._create_pf()
        tgt_file = self.tmp_dir / "tgt.txt"
        self.assertFalse(tgt_file.exists())
        pf.Save(str(tgt_file), True)
        self.assertEqual(pf.GetCurFile(), str(tgt_file))
        self.assertTrue(tgt_file.exists())
