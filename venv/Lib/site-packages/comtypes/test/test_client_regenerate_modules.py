import contextlib
import importlib
from pathlib import Path
import shutil
import sys
import tempfile
import types
from typing import Iterator
import unittest as ut
from unittest import mock

import comtypes
import comtypes.client
import comtypes.gen

comtypes.client.GetModule("scrrun.dll")
from comtypes.gen import Scripting  # noqa
from comtypes.gen import stdole  # noqa


SCRRUN_FRIENDLY = Path(Scripting.__file__)
SCRRUN_WRAPPER = Path(Scripting.__wrapper_module__.__file__)
STDOLE_FRIENDLY = Path(stdole.__file__)
STDOLE_WRAPPER = Path(stdole.__wrapper_module__.__file__)


@contextlib.contextmanager
def _mkdtmp_gen_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as t:
        tmp_dir = Path(t)
        tmp_comtypes_dir = tmp_dir / "comtypes"
        tmp_comtypes_dir.mkdir()
        (tmp_comtypes_dir / "__init__.py").touch()
        tmp_comtypes_gen_dir = tmp_comtypes_dir / "gen"
        tmp_comtypes_gen_dir.mkdir()
        (tmp_comtypes_gen_dir / "__init__.py").touch()
        yield tmp_comtypes_gen_dir


@contextlib.contextmanager
def _patch_gen_pkg(new_path: Path) -> Iterator[types.ModuleType]:
    new_comtypes_init = (new_path / "comtypes" / "__init__.py").resolve()
    assert new_comtypes_init.exists()
    new_comtypes_gen_init = (new_path / "comtypes" / "gen" / "__init__.py").resolve()
    assert new_comtypes_gen_init.exists()
    orig_comtypes = sys.modules["comtypes"]
    orig_gen_names = list(filter(lambda k: k.startswith("comtypes.gen"), sys.modules))
    tmp_sys_path = list(sys.path)  # copy
    with mock.patch.object(sys, "path", tmp_sys_path):
        sys.path.insert(0, str(new_path))
        with mock.patch.dict(sys.modules):
            # The reason for removing the parent module (in this case, `comtypes`)
            # from `sys.modules` is because the child module (in this case,
            # `comtypes.gen`) refers to the namespace of the parent module.
            # If the parent module exists in `sys.modules`, Python uses that cache
            # to import the child module. Therefore, in order to import a new version
            # of the child module, it is necessary to temporarily remove the parent
            # module from `sys.modules`.
            del sys.modules["comtypes"]
            for k in orig_gen_names:
                del sys.modules[k]
            # The module that is imported here is not the one cached in `sys.modules`
            # before the patch, but the module that is newly loaded from
            # `new_path / 'comtypes' / 'gen' / '__init__.py'`.
            new_comtypes_gen = importlib.import_module("comtypes.gen")
            assert new_comtypes_gen.__file__ is not None
            assert Path(new_comtypes_gen.__file__).resolve() == new_comtypes_gen_init
            # The `comtypes` module cached in `sys.modules` as a side effect of
            # executing the above line is empty because it is the one loaded from
            # `new_path / 'comtypes' / '__init__.py'`.
            # If we call the test target as it is, an error will occur due to
            # referencing an empty module, so we restore the original `comtypes`
            # to `sys.modules`.
            sys.modules["comtypes"] = orig_comtypes
            assert sys.modules["comtypes.gen"] is new_comtypes_gen
            # By making the empty `comtypes.gen` package we created earlier to be
            # referenced as the `gen` attribute of `comtypes`, the original
            # `comtypes.gen` will not be referenced within the context.
            with mock.patch.object(orig_comtypes, "gen", new_comtypes_gen):
                yield new_comtypes_gen


@contextlib.contextmanager
def patch_gen_dir() -> Iterator[Path]:
    with _mkdtmp_gen_dir() as tmp_gen_dir:
        with mock.patch.object(comtypes.client, "gen_dir", str(tmp_gen_dir)):
            try:
                with _patch_gen_pkg(tmp_gen_dir.parent.parent):
                    yield tmp_gen_dir
            finally:
                importlib.invalidate_caches()
                importlib.reload(comtypes.gen)
                importlib.reload(stdole)
                importlib.reload(Scripting)


class Test(ut.TestCase):
    def test_all_modules_are_missing(self):
        with patch_gen_dir() as gen_dir:
            # ensure `gen_dir` and `sys.modules` are patched.
            with self.assertRaises(ImportError):
                from comtypes.gen import Scripting as _  # noqa
            self.assertFalse((gen_dir / SCRRUN_FRIENDLY.name).exists())
            self.assertFalse((gen_dir / SCRRUN_WRAPPER.name).exists())
            self.assertFalse((gen_dir / STDOLE_FRIENDLY.name).exists())
            self.assertFalse((gen_dir / STDOLE_WRAPPER.name).exists())
            # generate new files and modules.
            comtypes.client.GetModule("scrrun.dll")
            self.assertTrue((gen_dir / SCRRUN_FRIENDLY.name).exists())
            self.assertTrue((gen_dir / SCRRUN_WRAPPER.name).exists())
            self.assertTrue((gen_dir / STDOLE_FRIENDLY.name).exists())
            self.assertTrue((gen_dir / STDOLE_WRAPPER.name).exists())

    def test_friendly_module_is_missing(self):
        with patch_gen_dir() as gen_dir:
            shutil.copy2(SCRRUN_WRAPPER, gen_dir / SCRRUN_WRAPPER.name)
            wrp_mtime = (gen_dir / SCRRUN_WRAPPER.name).stat().st_mtime_ns
            shutil.copy2(STDOLE_FRIENDLY, gen_dir / STDOLE_FRIENDLY.name)
            shutil.copy2(STDOLE_WRAPPER, gen_dir / STDOLE_WRAPPER.name)
            comtypes.client.GetModule("scrrun.dll")
            self.assertTrue((gen_dir / SCRRUN_FRIENDLY.name).exists())
            # Check the most recent content modification time to confirm whether
            # the module file has been regenerated.
            self.assertGreater(
                (gen_dir / SCRRUN_WRAPPER.name).stat().st_mtime_ns, wrp_mtime
            )

    def test_wrapper_module_is_missing(self):
        with patch_gen_dir() as gen_dir:
            shutil.copy2(SCRRUN_WRAPPER, gen_dir / SCRRUN_FRIENDLY.name)
            frd_mtime = (gen_dir / SCRRUN_FRIENDLY.name).stat().st_mtime_ns
            shutil.copy2(STDOLE_FRIENDLY, gen_dir / STDOLE_FRIENDLY.name)
            shutil.copy2(STDOLE_WRAPPER, gen_dir / STDOLE_WRAPPER.name)
            comtypes.client.GetModule("scrrun.dll")
            self.assertTrue((gen_dir / SCRRUN_WRAPPER.name).exists())
            self.assertGreater(
                (gen_dir / SCRRUN_FRIENDLY.name).stat().st_mtime_ns, frd_mtime
            )

    def test_dependency_modules_are_missing(self):
        with patch_gen_dir() as gen_dir:
            shutil.copy2(SCRRUN_WRAPPER, gen_dir / SCRRUN_FRIENDLY.name)
            frd_mtime = (gen_dir / SCRRUN_FRIENDLY.name).stat().st_mtime_ns
            shutil.copy2(SCRRUN_WRAPPER, gen_dir / SCRRUN_WRAPPER.name)
            wrp_mtime = (gen_dir / SCRRUN_WRAPPER.name).stat().st_mtime_ns
            comtypes.client.GetModule("scrrun.dll")
            self.assertTrue((gen_dir / STDOLE_FRIENDLY.name).exists())
            self.assertTrue((gen_dir / STDOLE_WRAPPER.name).exists())
            self.assertGreater(
                (gen_dir / SCRRUN_FRIENDLY.name).stat().st_mtime_ns, frd_mtime
            )
            self.assertGreater(
                (gen_dir / SCRRUN_WRAPPER.name).stat().st_mtime_ns, wrp_mtime
            )


if __name__ == "__main__":
    ut.main()
