from pathlib import Path
import tempfile
import unittest as ut

from comtypes import CoCreateInstance, GUID, shelllink
import comtypes.hresult
from comtypes.persist import IPersistFile


CLSID_ShellLink = GUID("{00021401-0000-0000-C000-000000000046}")


class Test_IShellLinkA(ut.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.tmp_dir = Path(td.name)
        self.src_file = (self.tmp_dir / "src.txt").resolve()
        self.src_file.touch()

    def _create_shortcut(self) -> shelllink.IShellLinkA:
        return CoCreateInstance(CLSID_ShellLink, interface=shelllink.IShellLinkA)

    def test_set_and_get_path(self):
        shortcut = self._create_shortcut()
        pf = shortcut.QueryInterface(IPersistFile)
        self.assertEqual(pf.IsDirty(), comtypes.hresult.S_FALSE)
        shortcut.SetPath(str(self.src_file).encode("utf-8"))
        self.assertEqual(pf.IsDirty(), comtypes.hresult.S_OK)
        self.assertEqual(
            shortcut.GetPath(shelllink.SLGP_UNCPRIORITY),
            str(self.src_file).encode("utf-8"),
        )
        lnk_file = (self.tmp_dir / "new.lnk").resolve()
        self.assertFalse(lnk_file.exists())
        pf.Save(str(lnk_file), True)
        self.assertTrue(lnk_file.exists())
        self.assertEqual(pf.GetCurFile(), str(lnk_file))

    def test_set_and_get_working_directory(self):
        shortcut = self._create_shortcut()
        shortcut.SetWorkingDirectory(str(self.tmp_dir).encode("utf-8"))
        self.assertEqual(
            shortcut.GetWorkingDirectory(), str(self.tmp_dir).encode("utf-8")
        )

    def test_set_and_get_arguments(self):
        shortcut = self._create_shortcut()
        shortcut.SetArguments(b"-f")
        self.assertEqual(shortcut.GetArguments(), b"-f")

    def test_set_and_get_hotkey(self):
        hotkey = shelllink.HOTKEYF_ALT | shelllink.HOTKEYF_CONTROL
        shortcut = self._create_shortcut()
        shortcut.Hotkey = hotkey
        self.assertEqual(shortcut.Hotkey, hotkey)

    def test_set_and_get_showcmd(self):
        shortcut = self._create_shortcut()
        shortcut.ShowCmd = shelllink.SW_SHOWMAXIMIZED
        self.assertEqual(shortcut.ShowCmd, shelllink.SW_SHOWMAXIMIZED)

    def test_set_and_get_icon_location(self):
        shortcut = self._create_shortcut()
        shortcut.SetIconLocation(str(self.src_file).encode("utf-8"), 1)
        icon_path, index = shortcut.GetIconLocation()
        self.assertEqual(icon_path, str(self.src_file).encode("utf-8"))
        self.assertEqual(index, 1)


class Test_IShellLinkW(ut.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.tmp_dir = Path(td.name)
        self.src_file = (self.tmp_dir / "src.txt").resolve()
        self.src_file.touch()

    def _create_shortcut(self) -> shelllink.IShellLinkW:
        return CoCreateInstance(CLSID_ShellLink, interface=shelllink.IShellLinkW)

    def test_set_and_get_path(self):
        shortcut = self._create_shortcut()
        pf = shortcut.QueryInterface(IPersistFile)
        self.assertEqual(pf.IsDirty(), comtypes.hresult.S_FALSE)
        shortcut.SetPath(str(self.src_file))
        self.assertEqual(pf.IsDirty(), comtypes.hresult.S_OK)
        self.assertEqual(
            shortcut.GetPath(shelllink.SLGP_UNCPRIORITY),
            str(self.src_file),
        )
        lnk_file = (self.tmp_dir / "new.lnk").resolve()
        self.assertFalse(lnk_file.exists())
        pf.Save(str(lnk_file), True)
        self.assertTrue(lnk_file.exists())
        self.assertEqual(pf.GetCurFile(), str(lnk_file))

    def test_set_and_get_description(self):
        shortcut = self._create_shortcut()
        shortcut.SetDescription("sample")
        self.assertEqual(shortcut.GetDescription(), "sample")

    def test_set_and_get_working_directory(self):
        shortcut = self._create_shortcut()
        shortcut.SetWorkingDirectory(str(self.tmp_dir))
        self.assertEqual(shortcut.GetWorkingDirectory(), str(self.tmp_dir))

    def test_set_and_get_arguments(self):
        shortcut = self._create_shortcut()
        shortcut.SetArguments("-f")
        self.assertEqual(shortcut.GetArguments(), "-f")

    def test_set_and_get_hotkey(self):
        hotkey = shelllink.HOTKEYF_ALT | shelllink.HOTKEYF_CONTROL
        shortcut = self._create_shortcut()
        shortcut.Hotkey = hotkey
        self.assertEqual(shortcut.Hotkey, hotkey)

    def test_set_and_get_showcmd(self):
        shortcut = self._create_shortcut()
        shortcut.ShowCmd = shelllink.SW_SHOWMAXIMIZED
        self.assertEqual(shortcut.ShowCmd, shelllink.SW_SHOWMAXIMIZED)

    def test_set_and_get_icon_location(self):
        shortcut = self._create_shortcut()
        shortcut.SetIconLocation(str(self.src_file), 1)
        icon_path, index = shortcut.GetIconLocation()
        self.assertEqual(icon_path, str(self.src_file))
        self.assertEqual(index, 1)
