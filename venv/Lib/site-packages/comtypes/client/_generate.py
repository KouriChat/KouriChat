import ctypes
import importlib
import inspect
import logging
import os
import sys
import types
from typing import Any, Tuple, List, Mapping, Optional, Dict, Union as _UnionT
import winreg

from comtypes import GUID, typeinfo
import comtypes.client
from comtypes.tools import codegenerator, tlbparser


logger = logging.getLogger(__name__)

PATH = os.environ["PATH"].split(os.pathsep)


def _my_import(fullname: str) -> types.ModuleType:
    """helper function to import dotted modules"""
    import comtypes.gen as g

    if comtypes.client.gen_dir and comtypes.client.gen_dir not in g.__path__:
        g.__path__.append(comtypes.client.gen_dir)  # type: ignore
    return importlib.import_module(fullname)


def _resolve_filename(tlib_string: str, dirpath: str) -> Tuple[str, bool]:
    """Tries to make sense of a type library specified as a string.

    Args:
        tlib_string: type library designator
        dirpath: a directory to relativize the location

    Returns:
        (abspath, True) or (relpath, False):
            where relpath is an unresolved path.
    """
    assert isinstance(tlib_string, str)
    # pathname of type library
    if os.path.isabs(tlib_string):
        # a specific location
        return tlib_string, True
    elif dirpath:
        abspath = os.path.normpath(os.path.join(dirpath, tlib_string))
        if os.path.exists(abspath):
            return abspath, True
    # try with respect to cwd (if _getmodule executed from command line)
    abspath = os.path.abspath(tlib_string)
    if os.path.exists(abspath):
        return abspath, True
    # Otherwise it may still be that the file is on Windows search
    # path for typelibs, and we leave the pathname alone.
    return tlib_string, False


def GetModule(tlib: _UnionT[Any, typeinfo.ITypeLib]) -> types.ModuleType:
    """Create a module wrapping a COM typelibrary on demand.

    'tlib' must be ...
    - an `ITypeLib` COM pointer instance
    - an absolute pathname of a type library
    - a relative pathname of a type library
      - interpreted as relative to the callers `__file__`, if this exists
    - a COM CLSID `GUID`
    - a `tuple`/`list` specifying the typelib
      - `List[_UnionT[str, int]]`
      - `(libid: str[, wMajorVerNum: int, wMinorVerNum: int[, lcid: int]])`
    - an object with `_reg_libid_: str` and `_reg_version_: Iterable[int]`

    This function determines the module name from the typelib
    attributes, then tries to import it.  If that fails because the
    module doesn't exist, the module is generated into the
    `comtypes.gen` package.

    It is possible to delete the whole `comtypes/gen` directory to
    remove all generated modules, the directory and the `__init__.py`
    file in it will be recreated when needed.

    If `comtypes.gen.__path__` is not a directory (in a frozen
    executable it lives in a zip archive), generated modules are only
    created in memory without writing them to the file system.

    Example:
        GetModule("UIAutomationCore.dll")

    would create modules named

        `comtypes.gen._944DE083_8FB8_45CF_BCB7_C477ACB2F897_L_M_m`
          - typelib wrapper module
          - where L, M, m are numbers of Lcid, Major-ver, minor-ver
        `comtypes.gen.UIAutomationClient`
          - friendly named module

    containing the Python wrapper code for the type library used by
    UIAutomation.  The former module contains all the code, the
    latter is a short stub loading the former.
    """
    if isinstance(tlib, str):
        tlib_string = tlib
        # if a relative pathname is used, we try to interpret it relative to
        # the directory of the calling module (if not from command line)
        frame = sys._getframe(1)
        _file_: Optional[str] = frame.f_globals.get("__file__", None)
        pathname, is_abs = _resolve_filename(
            tlib_string,
            _file_ and os.path.dirname(_file_),  # type: ignore
        )
        logger.debug("GetModule(%s), resolved: %s", pathname, is_abs)
        tlib = _load_tlib(pathname)  # don't register
        if not is_abs:
            # try to get path after loading, but this only works if already registered
            pathname = tlbparser.get_tlib_filename(tlib)
            if pathname is None:
                logger.info("GetModule(%s): could not resolve to a filename", tlib)
                pathname = tlib_string
        # if above path torture resulted in an absolute path, then the file exists (at this point)!
        assert not (os.path.isabs(pathname)) or os.path.exists(pathname)
    else:
        pathname = None
        tlib = _load_tlib(tlib)
    logger.debug("GetModule(%s)", tlib.GetLibAttr())
    mod = _get_existing_module(tlib)
    if mod is not None:
        return mod
    return ModuleGenerator(tlib, pathname).generate()


def _load_tlib(obj: Any) -> typeinfo.ITypeLib:
    """Load a pointer of ITypeLib on demand."""
    # obj is a filepath or a ProgID
    if isinstance(obj, str):
        # in any case, attempt to load and if tlib_string is not valid, then raise
        # as "OSError: [WinError -2147312566] Error loading type library/DLL"
        return typeinfo.LoadTypeLibEx(obj)
    # obj is a tlib GUID contain a clsid
    elif isinstance(obj, GUID):
        clsid = str(obj)
        # lookup associated typelib in registry
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\TypeLib") as key:
            libid = winreg.EnumValue(key, 0)[1]
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\Version") as key:
            ver = winreg.EnumValue(key, 0)[1].split(".")
        return typeinfo.LoadRegTypeLib(GUID(libid), int(ver[0]), int(ver[1]), 0)
    # obj is a sequence containing libid
    elif isinstance(obj, (tuple, list)):
        libid, ver = obj[0], obj[1:]
        if not ver:  # case of version numbers are not containing
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"TypeLib\{libid}") as key:
                ver = [int(v, base=16) for v in winreg.EnumKey(key, 0).split(".")]
        return typeinfo.LoadRegTypeLib(GUID(libid), *ver)
    # obj is a COMObject implementation
    elif hasattr(obj, "_reg_libid_"):
        return typeinfo.LoadRegTypeLib(GUID(obj._reg_libid_), *obj._reg_version_)
    # obj is a pointer of ITypeLib
    elif isinstance(obj, ctypes.POINTER(typeinfo.ITypeLib)):
        return obj  # type: ignore
    raise TypeError(f"'{obj!r}' is not supported type for loading typelib")


def _get_existing_module(tlib: typeinfo.ITypeLib) -> Optional[types.ModuleType]:
    def _get_friendly(name: str) -> Optional[types.ModuleType]:
        try:
            mod = _my_import(name)
        except Exception as details:
            logger.info("Could not import %s: %s", friendly_name, details)
        else:
            return mod

    def _get_wrapper(name: str) -> Optional[types.ModuleType]:
        if name in sys.modules:
            return sys.modules[name]
        try:
            return _my_import(name)
        except Exception as details:
            logger.info("Could not import %s: %s", name, details)

    wrapper_name = codegenerator.name_wrapper_module(tlib)
    friendly_name = codegenerator.name_friendly_module(tlib)
    wrapper_module = _get_wrapper(wrapper_name)
    if wrapper_module is not None:
        if friendly_name is None:
            return wrapper_module
        else:
            friendly_module = _get_friendly(friendly_name)
            if friendly_module is not None:
                return friendly_module
    return None


def _create_module(modulename: str, code: str) -> types.ModuleType:
    """Creates the module, then imports it."""
    # `modulename` is 'comtypes.gen.xxx'
    stem = modulename.split(".")[-1]
    if comtypes.client.gen_dir is None:
        # in memory system
        import comtypes.gen as g

        mod = types.ModuleType(modulename)
        abs_gen_path = os.path.abspath(g.__path__[0])  # type: ignore
        mod.__file__ = os.path.join(abs_gen_path, "<memory>")
        exec(code, mod.__dict__)
        sys.modules[modulename] = mod
        setattr(g, stem, mod)
        return mod
    # in file system
    with open(os.path.join(comtypes.client.gen_dir, f"{stem}.py"), "w") as ofi:
        print(code, file=ofi)
    # clear the import cache to make sure Python sees newly created modules
    importlib.invalidate_caches()
    return _my_import(modulename)


class ModuleGenerator(object):
    def __init__(self, tlib: typeinfo.ITypeLib, pathname: Optional[str]) -> None:
        self.wrapper_name = codegenerator.name_wrapper_module(tlib)
        self.friendly_name = codegenerator.name_friendly_module(tlib)
        if pathname is None:
            self.pathname = tlbparser.get_tlib_filename(tlib)
        else:
            self.pathname = pathname
        self.tlib = tlib

    def generate(self) -> types.ModuleType:
        """Generates wrapper and friendly modules."""
        known_symbols, known_interfaces = _get_known_namespaces()
        codegen = codegenerator.CodeGenerator(known_symbols, known_interfaces)
        codebases: List[Tuple[str, str]] = []
        logger.info("# Generating %s", self.wrapper_name)
        items = list(tlbparser.TypeLibParser(self.tlib).parse().values())
        wrp_code = codegen.generate_wrapper_code(items, filename=self.pathname)
        codebases.append((self.wrapper_name, wrp_code))
        if self.friendly_name is not None:
            logger.info("# Generating %s", self.friendly_name)
            frd_code = codegen.generate_friendly_code(self.wrapper_name)
            codebases.append((self.friendly_name, frd_code))
        for ext_tlib in codegen.externals:  # generates dependency COM-lib modules
            GetModule(ext_tlib)
        return [_create_module(name, code) for (name, code) in codebases][-1]


_SymbolName = str
_ModuleName = str
_ItfName = str
_ItfIid = str


def _get_known_namespaces() -> (
    Tuple[Mapping[_SymbolName, _ModuleName], Mapping[_ItfName, _ItfIid]]
):
    """Returns symbols and interfaces that are already statically defined in `ctypes`
    and `comtypes`.
    From `ctypes`, all the names are obtained.
    From `comtypes`, only the names in each module's `__known_symbols__` are obtained.

    Note:
        The interfaces that should be included in `__known_symbols__` should be limited
        to those that can be said to be bound to the design concept of COM, such as
        `IUnknown`, `IDispatch` and `ITypeInfo`.
        `comtypes` does NOT aim to statically define all COM object interfaces in
        its repository.
    """
    known_symbols: Dict[_SymbolName, _ModuleName] = {}
    known_interfaces: Dict[_ItfName, _ItfIid] = {}
    for mod_name in (
        "comtypes.persist",
        "comtypes.typeinfo",
        "comtypes.automation",
        "comtypes.stream",
        "comtypes",
        "ctypes.wintypes",
        "ctypes",
    ):
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "__known_symbols__"):
            names: List[str] = mod.__known_symbols__
            for name in names:
                tgt = getattr(mod, name)
                if inspect.isclass(tgt) and issubclass(tgt, comtypes.IUnknown):
                    assert name not in known_interfaces
                    known_interfaces[name] = str(tgt._iid_)
        else:
            names = list(mod.__dict__)
        for name in names:
            known_symbols[name] = mod.__name__
    return known_symbols, known_interfaces


################################################################


if __name__ == "__main__":
    # When started as script, generate typelib wrapper from .tlb file.
    GetModule(sys.argv[1])
