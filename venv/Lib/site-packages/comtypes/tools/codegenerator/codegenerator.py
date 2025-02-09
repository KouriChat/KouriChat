# Code generator to generate code for everything contained in COM type
# libraries.
import keyword
import logging
import os
import textwrap
from typing import Any
from typing import Dict, List, Tuple
from typing import Sequence
from typing import Optional, Union as _UnionT
import io

import comtypes
from comtypes import typeinfo
from comtypes.tools import tlbparser, typedesc
from comtypes.tools.codegenerator import namespaces
from comtypes.tools.codegenerator import packing
from comtypes.tools.codegenerator.modulenamer import name_wrapper_module
from comtypes.tools.codegenerator.helpers import (
    get_real_type,
    ASSUME_STRINGS,
    ComMethodGenerator,
    DispMethodGenerator,
    DispPropertyGenerator,
    TypeNamer,
)
from comtypes.tools.codegenerator import typeannotator


version = comtypes.__version__

logger = logging.getLogger(__name__)

__warn_on_munge__ = __debug__


_InterfaceTypeDesc = _UnionT[
    typedesc.ComInterface,
    typedesc.ComInterfaceHead,
    typedesc.ComInterfaceBody,
    typedesc.DispInterface,
    typedesc.DispInterfaceHead,
    typedesc.DispInterfaceBody,
]


class CodeGenerator(object):
    def __init__(self, known_symbols=None, known_interfaces=None) -> None:
        self.stream = io.StringIO()
        self.imports = namespaces.ImportedNamespaces()
        self.declarations = namespaces.DeclaredNamespaces()
        self.enums = namespaces.EnumerationNamespaces()
        self.unnamed_enum_members: List[Tuple[str, int]] = []
        self._to_type_name = TypeNamer()
        self.known_symbols = known_symbols or {}
        self.known_interfaces = known_interfaces or {}

        self.done = set()  # type descriptions that have been generated
        self.names = set()  # names that have been generated
        self.externals = []  # typelibs imported to generated module
        self.enum_aliases: Dict[str, str] = {}
        self.last_item_class = False

    def generate(self, item):
        if item in self.done:
            return
        if self._is_interface_typedesc(item):
            self._define_interface(item)
            return
        if isinstance(item, typedesc.StructureHead):
            name = getattr(item.struct, "name", None)
        else:
            name = getattr(item, "name", None)
        if name in self.known_symbols:
            self.imports.add(name, symbols=self.known_symbols)
            self.done.add(item)
            if isinstance(item, typedesc.Structure):
                self.done.add(item.get_head())
                self.done.add(item.get_body())
            return
        mth = getattr(self, type(item).__name__)
        # to avoid infinite recursion, we have to mark it as done
        # before actually generating the code.
        self.done.add(item)
        mth(item)

    def generate_all(self, items):
        for item in items:
            self.generate(item)

    def _make_relative_path(self, path1, path2):
        """path1 and path2 are pathnames.
        Return path1 as a relative path to path2, if possible.
        """
        path1 = os.path.abspath(path1)
        path2 = os.path.abspath(path2)
        common = os.path.commonprefix(
            [os.path.normcase(path1), os.path.normcase(path2)]
        )
        if not os.path.isdir(common):
            return path1
        if not common.endswith("\\"):
            return path1
        if not os.path.isdir(path2):
            path2 = os.path.dirname(path2)
        # strip the common prefix
        path1 = path1[len(common) :]
        path2 = path2[len(common) :]

        parts2 = path2.split("\\")
        return "..\\" * len(parts2) + path1

    def _generate_typelib_path(self, filename):
        # NOTE: the logic in this function appears completely different from that
        # of the handling of tlib (given as a string) in GetModule. There, relative
        # references are resolved wrt to the directory of the calling module. Here,
        # resolution is with respect to current working directory -- later to be
        # relativized to comtypes.gen.
        if filename is not None:
            if os.path.isabs(filename):
                # absolute path
                self.declarations.add("typelib_path", repr(filename))
            elif not os.path.dirname(filename) and not os.path.isfile(filename):
                # no directory given, and not in current directory.
                self.declarations.add("typelib_path", repr(filename))
            else:
                # relative path; make relative to comtypes.gen.
                path = self._make_relative_path(filename, comtypes.gen.__path__[0])
                self.imports.add("os")
                definition = (
                    f"os.path.normpath(\n"
                    f"    os.path.abspath(os.path.join(os.path.dirname(__file__),\n"
                    f"                                 {path!r})))"
                )
                self.declarations.add("typelib_path", definition)
                p = os.path.normpath(
                    os.path.abspath(os.path.join(comtypes.gen.__path__[0], path))
                )
                assert os.path.isfile(p)
            self.names.add("typelib_path")

    def generate_wrapper_code(
        self, tdescs: Sequence[Any], filename: Optional[str]
    ) -> str:
        """Returns the code for the COM type library wrapper module.

        The returned `Python` code string is containing definitions of interfaces,
        coclasses, constants, and structures.

        The module will have long name that is derived from the type library guid, lcid
        and version numbers.
        Such as `comtypes.gen._xxxxxxxx_xxxx_xxxx_xxxx_xxxxxxxxxxxx_l_M_m`.
        """
        tlib_mtime = None

        if filename is not None:
            # get full path to DLL first (os.stat can't work with relative DLL paths properly)
            loaded_typelib = typeinfo.LoadTypeLib(filename)
            full_filename = tlbparser.get_tlib_filename(loaded_typelib)

            while full_filename and not os.path.exists(full_filename):
                full_filename = os.path.split(full_filename)[0]

            if full_filename and os.path.isfile(full_filename):
                # get DLL timestamp at the moment of wrapper generation

                tlib_mtime = os.stat(full_filename).st_mtime

                if not full_filename.endswith(filename):
                    filename = full_filename

        self.filename = filename
        self.declarations.add("_lcid", "0", "change this if required")
        self._generate_typelib_path(filename)

        items = set(tdescs)
        loops = 0
        while items:
            loops += 1
            self.more = set()
            self.generate_all(items)

            items |= self.more
            items -= self.done

        self.imports.add("ctypes", "*")  # HACK: wildcard import is so ugly.
        if tlib_mtime is not None:
            logger.debug('filename: "%s": tlib_mtime: %s', filename, tlib_mtime)
            self.imports.add("comtypes", "_check_version")
        output = io.StringIO()
        if filename is not None:
            # Hm, what is the CORRECT encoding?
            print("# -*- coding: mbcs -*-", file=output)
            print(file=output)
        print(self.imports.getvalue(), file=output)
        print("from typing import TYPE_CHECKING", file=output)
        print(file=output)
        print("if TYPE_CHECKING:", file=output)
        print("    from comtypes import hints", file=output)
        print(file=output)
        print(file=output)
        print(self.declarations.getvalue(), file=output)
        print(file=output)
        if self.unnamed_enum_members:
            print("# values for unnamed enumeration", file=output)
            for n, v in self.unnamed_enum_members:
                print(f"{n} = {v}", file=output)
            print(file=output)
        if self.enums:
            print(self.enums.to_constants(), file=output)
            print(file=output)
        if self.enum_aliases:
            print("# aliases for enums", file=output)
            for k, v in self.enum_aliases.items():
                print(f"{k} = {v}", file=output)
            print(file=output)
        print(self.stream.getvalue(), file=output)
        print(self._make_dunder_all_part(), file=output)
        print(file=output)
        if tlib_mtime is not None:
            print("_check_version(%r, %f)" % (version, tlib_mtime), file=output)
        return output.getvalue()

    def generate_friendly_code(self, modname: str) -> str:
        """Returns the code for the COM type library friendly module.

        The returned `Python` code string is containing `from {modname} import
        DefinedInWrapper, ...` and `__all__ = ['DefinedInWrapper', ...]`
        The `modname` is the wrapper module name like `comtypes.gen._xxxx..._x_x_x`.

        The module will have shorter name that is derived from the type library name.
        Such as "comtypes.gen.stdole" and "comtypes.gen.Excel".
        """
        output = io.StringIO()
        print("from enum import IntFlag", file=output)
        print(file=output)
        print(f"import {modname} as __wrapper_module__", file=output)
        print(self._make_friendly_module_import_part(modname), file=output)
        print(file=output)
        print(file=output)
        if self.enums:
            print(self.enums.to_intflags(), file=output)
            print(file=output)
            print(file=output)
        if self.enum_aliases:
            for k, v in self.enum_aliases.items():
                print(f"{k} = {v}", file=output)
            print(file=output)
            print(file=output)
        print(self._make_dunder_all_part(), file=output)
        return output.getvalue()

    def _make_dunder_all_part(self) -> str:
        joined_names = ", ".join(repr(str(n)) for n in self.names)
        dunder_all = f"__all__ = [{joined_names}]"
        if len(dunder_all) > 80:
            txtwrapper = textwrap.TextWrapper(
                subsequent_indent="    ", initial_indent="    ", break_long_words=False
            )
            joined_names = "\n".join(txtwrapper.wrap(joined_names))
            dunder_all = f"__all__ = [\n{joined_names}\n]"
        return dunder_all

    def _make_friendly_module_import_part(self, modname: str) -> str:
        # The `modname` is the wrapper module name like `comtypes.gen._xxxx..._x_x_x`
        txtwrapper = textwrap.TextWrapper(
            subsequent_indent="    ", initial_indent="    ", break_long_words=False
        )
        symbols = set(self.names)
        symbols.update(self.imports.get_symbols())
        symbols.update(self.declarations.get_symbols())
        symbols -= set(self.enums.get_symbols())
        symbols -= set(self.enum_aliases)
        joined_names = ", ".join(str(n) for n in symbols)
        part = f"from {modname} import {joined_names}"
        if len(part) > 80:
            txtwrapper = textwrap.TextWrapper(
                subsequent_indent="    ", initial_indent="    ", break_long_words=False
            )
            joined_names = "\n".join(txtwrapper.wrap(joined_names))
            part = f"from {modname} import (\n{joined_names}\n)"
        return part

    def need_VARIANT_imports(self, value):
        text = repr(value)
        if "Decimal(" in text:
            self.imports.add("decimal", "Decimal")
        if "datetime.datetime(" in text:
            self.imports.add("datetime")

    def _to_docstring(self, orig: str, depth: int = 1) -> str:
        # increasing `depth` by one increases indentation by one
        indent = "    " * depth
        # some chars are replaced to avoid causing a `SyntaxError`
        repled = orig.replace("\\", r"\\").replace('"', r"'")
        return f'{indent}"""{repled}"""'

    def ArrayType(self, tp: typedesc.ArrayType) -> None:
        self.generate(get_real_type(tp.typ))
        self.generate(tp.typ)

    def EnumValue(self, tp: typedesc.EnumValue) -> None:
        self.last_item_class = False
        value = int(tp.value)
        if keyword.iskeyword(tp.name):
            # XXX use logging!
            if __warn_on_munge__:
                print(f"# Fixing keyword as EnumValue for {tp.name}")
        tp_name = self._to_type_name(tp)
        if tp.enumeration.name:
            self.enums.add(tp.enumeration.name, tp_name, value)
        else:
            self.unnamed_enum_members.append((tp_name, value))
        self.names.add(tp_name)

    def Enumeration(self, tp: typedesc.Enumeration) -> None:
        self.last_item_class = False
        for item in tp.values:
            self.generate(item)
        if tp.name:
            self.names.add(tp.name)

    def Typedef(self, tp: typedesc.Typedef) -> None:
        if isinstance(tp.typ, (typedesc.Structure, typedesc.Union)):
            self.generate(tp.typ.get_head())
            self.more.add(tp.typ)
        else:
            self.generate(tp.typ)
        definition = self._to_type_name(tp.typ)
        if tp.name != definition:
            if definition in self.known_symbols:
                self.declarations.add(tp.name, definition)
            else:
                if isinstance(tp.typ, typedesc.Enumeration):
                    self.enum_aliases[tp.name] = definition
                else:
                    print(f"{tp.name} = {definition}", file=self.stream)
                    self.last_item_class = False
        self.names.add(tp.name)

    def FundamentalType(self, item: typedesc.FundamentalType) -> None:
        pass  # we should check if this is known somewhere

    def StructureHead(self, head: typedesc.StructureHead) -> None:
        for struct in head.struct.bases:
            self.generate(struct.get_head())
            self.more.add(struct)
        if head.struct.location:
            self.last_item_class = False
            print(f"# {head.struct.location}", file=self.stream)
        basenames = [self._to_type_name(b) for b in head.struct.bases]
        if basenames:
            self.imports.add("comtypes", "GUID")

            if not self.last_item_class:
                print(file=self.stream)
                print(file=self.stream)

            self.last_item_class = True

            method_names = [
                m.name for m in head.struct.members if type(m) is typedesc.Method
            ]
            print(
                f"class {head.struct.name}({', '.join(basenames)}):",
                file=self.stream,
            )
            print(
                "    _iid_ = GUID('{}') # please look up iid and fill in!",
                file=self.stream,
            )
            if "Enum" in method_names:
                print("    def __iter__(self):", file=self.stream)
                print("        return self.Enum()", file=self.stream)
            elif method_names == "Next Skip Reset Clone".split():
                print("    def __iter__(self):", file=self.stream)
                print("        return self", file=self.stream)
                print(file=self.stream)
                print("    def next(self):", file=self.stream)
                print("         arr, fetched = self.Next(1)", file=self.stream)
                print("         if fetched == 0:", file=self.stream)
                print("             raise StopIteration", file=self.stream)
                print("         return arr[0]", file=self.stream)

            print(file=self.stream)
            print(file=self.stream)

        else:
            methods = [m for m in head.struct.members if type(m) is typedesc.Method]

            if methods:
                # Hm. We cannot generate code for IUnknown...
                if not self.last_item_class:
                    print(file=self.stream)

                self.last_item_class = True
                print("assert 0, 'cannot generate code for IUnknown'", file=self.stream)
                print(file=self.stream)
                print(file=self.stream)
                print(f"class {head.struct.name}(_com_interface):", file=self.stream)
                print("    pass", file=self.stream)
                print(file=self.stream)
                print(file=self.stream)
            elif type(head.struct) == typedesc.Structure:
                if not self.last_item_class:
                    print(file=self.stream)
                    print(file=self.stream)

                self.last_item_class = True

                print(f"class {head.struct.name}(Structure):", file=self.stream)
                if hasattr(head.struct, "_recordinfo_"):
                    print(
                        f"    _recordinfo_ = {head.struct._recordinfo_!r}",
                        file=self.stream,
                    )
                else:
                    print("    pass", file=self.stream)
                print(file=self.stream)
                print(file=self.stream)
            elif type(head.struct) == typedesc.Union:
                if not self.last_item_class:
                    print(file=self.stream)
                    print(file=self.stream)

                self.last_item_class = True

                print(f"class {head.struct.name}(Union):", file=self.stream)
                print("    pass", file=self.stream)
                print(file=self.stream)
                print(file=self.stream)
        self.names.add(head.struct.name)

    def Structure(self, struct: typedesc.Structure) -> None:
        self.generate(struct.get_head())
        self.generate(struct.get_body())

    def Union(self, union: typedesc.Union) -> None:
        self.generate(union.get_head())
        self.generate(union.get_body())

    def StructureBody(self, body: typedesc.StructureBody) -> None:
        fields: List[typedesc.Field] = []
        methods: List[typedesc.Method] = []
        for m in body.struct.members:
            if type(m) is typedesc.Field:
                fields.append(m)
                if type(m.typ) is typedesc.Typedef:
                    self.generate(get_real_type(m.typ))
                self.generate(m.typ)
            elif type(m) is typedesc.Method:
                methods.append(m)
                self.generate(m.returns)
                self.generate_all(m.iterArgTypes())
            elif type(m) is typedesc.Constructor:
                pass

        # we don't need _pack_ on Unions (I hope, at least), and not
        # on COM interfaces:
        if not methods:
            try:
                pack = packing.calc_packing(body.struct, fields)
                if pack is not None:
                    self.last_item_class = False
                    print(f"{body.struct.name}._pack_ = {pack}", file=self.stream)
            except packing.PackingError as details:
                # if packing fails, write a warning comment to the output.
                import warnings

                message = "Structure %s: %s" % (body.struct.name, details)
                warnings.warn(message, UserWarning)
                print(f"# WARNING: {details}", file=self.stream)
                self.last_item_class = False

        if fields:
            if body.struct.bases:
                assert len(body.struct.bases) == 1
                self.generate(body.struct.bases[0].get_body())

            if not self.last_item_class:
                print(file=self.stream)

            self.last_item_class = False

            print(f"{body.struct.name}._fields_ = [", file=self.stream)
            if body.struct.location:
                print(f"    # {body.struct.location}", file=self.stream)
            # unnamed fields will get autogenerated names "_", "_1". "_2", "_3", ...
            unnamed_index = 0
            for f in fields:
                if not f.name:
                    if unnamed_index:
                        fieldname = "_%d" % unnamed_index
                    else:
                        fieldname = "_"
                    unnamed_index += 1
                    print(
                        f"    # Unnamed field renamed to '{fieldname}'",
                        file=self.stream,
                    )
                else:
                    fieldname = f.name
                if f.bits is None:
                    print(
                        f"    ('{fieldname}', {self._to_type_name(f.typ)}),",
                        file=self.stream,
                    )
                else:
                    print(
                        f"    ('{fieldname}', {self._to_type_name(f.typ)}, {f.bits}),",
                        file=self.stream,
                    )
            print("]", file=self.stream)

            if body.struct.size is None:
                print(file=self.stream)
                msg = (
                    "# The size provided by the typelib is incorrect.\n"
                    "# The size and alignment check for %s is skipped."
                )
                print(msg % body.struct.name, file=self.stream)
            elif body.struct.name not in packing.dont_assert_size:
                print(file=self.stream)
                size = body.struct.size // 8
                print(
                    f"assert sizeof({body.struct.name}) == {size}, sizeof({body.struct.name})",
                    file=self.stream,
                )
                align = body.struct.align // 8
                print(
                    f"assert alignment({body.struct.name}) == {align}, alignment({body.struct.name})",
                    file=self.stream,
                )

        if methods:
            self.imports.add("comtypes", "COMMETHOD")

            if not self.last_item_class:
                print(file=self.stream)

            self.last_item_class = False
            print(f"{body.struct.name}._methods_ = [", file=self.stream)
            if body.struct.location:
                print(f"# {body.struct.location}", file=self.stream)

            for m in methods:
                if m.location:
                    print(f"    # {m.location}", file=self.stream)
                print(
                    (
                        f"    COMMETHOD(\n"
                        f"        [], \n"
                        f"        {self._to_type_name(m.returns)},\n"
                        f"        '{m.name}',\n"
                    ),
                    file=self.stream,
                )
                for a in m.iterArgTypes():
                    print(f"        ([], {self._to_type_name(a)}),\n", file=self.stream)
                    print("    ),", file=self.stream)
            print("]", file=self.stream)

    ################################################################
    # top-level typedesc generators
    #
    def TypeLib(self, lib: typedesc.TypeLib) -> None:
        # Hm, in user code we have to write:
        # class MyServer(COMObject, ...):
        #     _com_interfaces_ = [MyTypeLib.IInterface]
        #     _reg_typelib_ = MyTypeLib.Library._reg_typelib_
        #                               ^^^^^^^
        # Should the '_reg_typelib_' attribute be at top-level in the
        # generated code, instead as being an attribute of the
        # 'Library' symbol?
        if not self.last_item_class:
            print(file=self.stream)
            print(file=self.stream)

        self.last_item_class = True

        print("class Library(object):", file=self.stream)
        if lib.doc:
            print(self._to_docstring(lib.doc), file=self.stream)

        if lib.name:
            print(f"    name = {lib.name!r}", file=self.stream)

        print(
            f"    _reg_typelib_ = ({lib.guid!r}, {lib.major!r}, {lib.minor!r})",
            file=self.stream,
        )
        print(file=self.stream)
        print(file=self.stream)
        self.names.add("Library")

    def External(self, ext: typedesc.External) -> None:
        modname = name_wrapper_module(ext.tlib)
        if modname not in self.imports:
            self.externals.append(ext.tlib)
            self.imports.add(modname)

    def Constant(self, tp: typedesc.Constant) -> None:
        self.last_item_class = False
        print(
            f"{tp.name} = {tp.value!r}  # Constant {self._to_type_name(tp.typ)}",
            file=self.stream,
        )
        self.names.add(tp.name)

    def SAFEARRAYType(self, sa: typedesc.SAFEARRAYType) -> None:
        self.generate(sa.typ)
        self.imports.add("comtypes.automation", "_midlSAFEARRAY")

    def PointerType(self, tp: typedesc.PointerType) -> None:
        if type(tp.typ) is typedesc.ComInterface:
            # this defines the class
            self.generate(tp.typ.get_head())
            # this defines the _methods_
            self.more.add(tp.typ)
        elif type(tp.typ) is typedesc.PointerType:
            self.generate(tp.typ)
        elif type(tp.typ) in (typedesc.Union, typedesc.Structure):
            self.generate(tp.typ.get_head())
            self.more.add(tp.typ)
        elif type(tp.typ) is typedesc.Typedef:
            self.generate(tp.typ)
        else:
            self.generate(tp.typ)
        if not ASSUME_STRINGS:
            return
        real_type = get_real_type(tp.typ)
        if isinstance(real_type, typedesc.FundamentalType):
            if real_type.name == "char":
                self.declarations.add("STRING", "c_char_p")
            elif real_type.name == "wchar_t":
                self.declarations.add("WSTRING", "c_wchar_p")

    def CoClass(self, coclass: typedesc.CoClass) -> None:
        self.imports.add("comtypes", "GUID")
        self.imports.add("comtypes", "CoClass")
        if not self.last_item_class:
            print(file=self.stream)
            print(file=self.stream)

        self.last_item_class = True

        print(f"class {coclass.name}(CoClass):", file=self.stream)
        if coclass.doc:
            print(self._to_docstring(coclass.doc), file=self.stream)
        print(f"    _reg_clsid_ = GUID({coclass.clsid!r})", file=self.stream)
        print(f"    _idlflags_ = {coclass.idlflags}", file=self.stream)
        if self.filename is not None:
            print("    _typelib_path_ = typelib_path", file=self.stream)
        # X print
        # >> self.stream, "POINTER(%s).__ctypes_from_outparam__ = wrap" % coclass.name

        libid = coclass.tlibattr.guid
        wMajor, wMinor = coclass.tlibattr.wMajorVerNum, coclass.tlibattr.wMinorVerNum
        print(
            f"    _reg_typelib_ = ({str(libid)!r}, {wMajor}, {wMinor})",
            file=self.stream,
        )
        print(file=self.stream)
        print(file=self.stream)

        for itf, _ in coclass.interfaces:
            self.generate(itf.get_head())
        impl, src = typedesc.groupby_impltypeflags(coclass.interfaces)
        implemented = [self._to_type_name(itf) for itf in impl]
        sources = [self._to_type_name(itf) for itf in src]

        if implemented:
            self.last_item_class = False
            print(
                f"{coclass.name}._com_interfaces_ = [{', '.join(implemented)}]",
                file=self.stream,
            )
        if sources:
            self.last_item_class = False
            print(
                f"{coclass.name}._outgoing_interfaces_ = [{', '.join(sources)}]",
                file=self.stream,
            )

        self.names.add(coclass.name)

    def _is_interface_typedesc(
        self, item: Any
    ) -> "comtypes.hints.TypeGuard[_InterfaceTypeDesc]":
        return isinstance(
            item,
            (
                typedesc.ComInterface,
                typedesc.ComInterfaceHead,
                typedesc.ComInterfaceBody,
                typedesc.DispInterface,
                typedesc.DispInterfaceHead,
                typedesc.DispInterfaceBody,
            ),
        )

    def _define_interface(self, item: _InterfaceTypeDesc) -> None:
        if isinstance(
            item,
            (
                typedesc.ComInterfaceHead,
                typedesc.ComInterfaceBody,
                typedesc.DispInterfaceHead,
                typedesc.DispInterfaceBody,
            ),
        ):
            if self._is_known_interface(item.itf):
                self.imports.add(item.itf.name, symbols=self.known_symbols)
                self.done.add(item)
                return
        elif isinstance(item, (typedesc.ComInterface, typedesc.DispInterface)):
            if self._is_known_interface(item):
                self.imports.add(item.name, symbols=self.known_symbols)
                self.done.add(item)
                self.done.add(item.get_head())
                self.done.add(item.get_body())
                return
        else:
            raise TypeError
        self.done.add(item)  # to avoid infinite recursion.
        mth = getattr(self, type(item).__name__)
        mth(item)

    def ComInterface(self, itf: typedesc.ComInterface) -> None:
        self.generate(itf.get_head())
        self.generate(itf.get_body())
        self.names.add(itf.name)

    def _is_known_interface(
        self, item: _UnionT[typedesc.ComInterface, typedesc.DispInterface]
    ) -> bool:
        """Returns whether an interface is statically defined in `comtypes`,
        based on its name and iid.
        """
        if item.name in self.known_interfaces:
            return self.known_interfaces[item.name] == item.iid
        return False

    def _is_enuminterface(self, itf: typedesc.ComInterface) -> bool:
        # Check if this is an IEnumXXX interface
        if not itf.name.startswith("IEnum"):
            return False
        member_names = [mth.name for mth in itf.members]
        for name in ("Next", "Skip", "Reset", "Clone"):
            if name not in member_names:
                return False
        return True

    def ComInterfaceHead(self, head: typedesc.ComInterfaceHead) -> None:
        if head.itf.base is None:
            # we don't beed to generate IUnknown
            return
        self.generate(head.itf.base.get_head())
        self.more.add(head.itf.base)
        basename = self._to_type_name(head.itf.base)

        self.imports.add("comtypes", "GUID")

        if not self.last_item_class:
            print(file=self.stream)
            print(file=self.stream)

        self.last_item_class = True

        print(f"class {head.itf.name}({basename}):", file=self.stream)
        if head.itf.doc:
            print(self._to_docstring(head.itf.doc), file=self.stream)

        print("    _case_insensitive_ = True", file=self.stream)
        print(f"    _iid_ = GUID({head.itf.iid!r})", file=self.stream)
        print(f"    _idlflags_ = {head.itf.idlflags}", file=self.stream)

        if self._is_enuminterface(head.itf):
            print(file=self.stream)
            print("    def __iter__(self):", file=self.stream)
            print("        return self", file=self.stream)
            print(file=self.stream)

            print("    def __next__(self):", file=self.stream)
            print("        item, fetched = self.Next(1)", file=self.stream)
            print("        if fetched:", file=self.stream)
            print("            return item", file=self.stream)
            print("        raise StopIteration", file=self.stream)
            print(file=self.stream)

            print("    def __getitem__(self, index):", file=self.stream)
            print("        self.Reset()", file=self.stream)
            print("        self.Skip(index)", file=self.stream)
            print("        item, fetched = self.Next(1)", file=self.stream)
            print("        if fetched:", file=self.stream)
            print("            return item", file=self.stream)
            print("        raise IndexError(index)", file=self.stream)

        annotations = typeannotator.ComInterfaceMembersAnnotator(head.itf).generate()
        if annotations:
            print(file=self.stream)
            print("    if TYPE_CHECKING:  # commembers", file=self.stream)
            print(annotations, file=self.stream)

        print(file=self.stream)
        print(file=self.stream)

    def ComInterfaceBody(self, body: typedesc.ComInterfaceBody) -> None:
        # The base class must be fully generated, including the
        # _methods_ list.
        self.generate(body.itf.base)

        # make sure we can generate the body
        for m in body.itf.members:
            for a in m.arguments:
                self.generate(a[0])
            self.generate(m.returns)

        if not self.last_item_class:
            print(file=self.stream)

        self.last_item_class = False
        print(f"{body.itf.name}._methods_ = [", file=self.stream)
        for m in body.itf.members:
            if isinstance(m, typedesc.ComMethod):
                self.make_ComMethod(m, "dual" in body.itf.idlflags)
            else:
                raise TypeError("what's this?")

        print("]", file=self.stream)
        print(file=self.stream)
        print(
            "################################################################",
            file=self.stream,
        )
        print(f"# code template for {body.itf.name} implementation", file=self.stream)
        print(f"# class {body.itf.name}_Impl(object):", file=self.stream)

        methods = {}
        for m in body.itf.members:
            if isinstance(m, typedesc.ComMethod):
                # m.arguments is a sequence of tuples:
                # (argtype, argname, idlflags, docstring)
                # Some typelibs have unnamed method parameters!
                inargs = [a[1] or "<unnamed>" for a in m.arguments if not "out" in a[2]]
                outargs = [a[1] or "<unnamed>" for a in m.arguments if "out" in a[2]]
                if "propget" in m.idlflags:
                    methods.setdefault(m.name, [0, inargs, outargs, m.doc])[0] |= 1
                elif "propput" in m.idlflags:
                    methods.setdefault(m.name, [0, inargs[:-1], inargs[-1:], m.doc])[
                        0
                    ] |= 2
                else:
                    methods[m.name] = [0, inargs, outargs, m.doc]

        for name, (typ, inargs, outargs, doc) in methods.items():
            if typ == 0:  # method
                print(
                    f"#     def {name}({', '.join(['self'] + inargs)}):",
                    file=self.stream,
                )
                print(f"#         {(doc or '-no docstring-')!r}", file=self.stream)
                print(f"#         #return {', '.join(outargs)}", file=self.stream)
            elif typ == 1:  # propget
                print("#     @property", file=self.stream)
                print(
                    f"#     def {name}({', '.join(['self'] + inargs)}):",
                    file=self.stream,
                )
                print(f"#         {(doc or '-no docstring-')!r}", file=self.stream)
                print(f"#         #return {', '.join(outargs)}", file=self.stream)
            elif typ == 2:  # propput
                print(
                    f"#     def _set({', '.join(['self'] + inargs + outargs)}):",
                    file=self.stream,
                )
                print(f"#         {(doc or '-no docstring-')!r}", file=self.stream)
                print(
                    f"#     {name} = property(fset = _set, doc = _set.__doc__)",
                    file=self.stream,
                )
            elif typ == 3:  # propget + propput
                print(
                    f"#     def _get({', '.join(['self'] + inargs)}):",
                    file=self.stream,
                )
                print(f"#         {(doc or '-no docstring-')!r}", file=self.stream)
                print(f"#         #return {', '.join(outargs)}", file=self.stream)
                print(
                    f"#     def _set({', '.join(['self'] + inargs + outargs)}):",
                    file=self.stream,
                )
                print(f"#         {(doc or '-no docstring-')!r}", file=self.stream)
                print(
                    f"#     {name} = property(_get, _set, doc = _set.__doc__)",
                    file=self.stream,
                )
            else:
                raise RuntimeError("BUG")
            print("#", file=self.stream)

    def DispInterface(self, itf: typedesc.DispInterface) -> None:
        self.generate(itf.get_head())
        self.generate(itf.get_body())
        self.names.add(itf.name)

    def DispInterfaceHead(self, head: typedesc.DispInterfaceHead) -> None:
        self.generate(head.itf.base)
        basename = self._to_type_name(head.itf.base)

        self.imports.add("comtypes", "GUID")
        if not self.last_item_class:
            print(file=self.stream)
            print(file=self.stream)

        self.last_item_class = True

        print(f"class {head.itf.name}({basename}):", file=self.stream)
        if head.itf.doc:
            print(self._to_docstring(head.itf.doc), file=self.stream)
        print("    _case_insensitive_ = True", file=self.stream)
        print(f"    _iid_ = GUID({head.itf.iid!r})", file=self.stream)
        print(f"    _idlflags_ = {head.itf.idlflags}", file=self.stream)
        print("    _methods_ = []", file=self.stream)

        annotations = typeannotator.DispInterfaceMembersAnnotator(head.itf).generate()
        if annotations:
            print(file=self.stream)
            print("    if TYPE_CHECKING:  # dispmembers", file=self.stream)
            print(annotations, file=self.stream)

        print(file=self.stream)
        print(file=self.stream)

    def DispInterfaceBody(self, body: typedesc.DispInterfaceBody) -> None:
        # make sure we can generate the body
        for m in body.itf.members:
            if isinstance(m, typedesc.DispMethod):
                for a in m.arguments:
                    self.generate(a[0])
                self.generate(m.returns)
            elif isinstance(m, typedesc.DispProperty):
                self.generate(m.typ)
            else:
                raise TypeError(m)

        if not self.last_item_class:
            print(file=self.stream)

        self.last_item_class = False

        print(f"{body.itf.name}._disp_methods_ = [", file=self.stream)
        for m in body.itf.members:
            if isinstance(m, typedesc.DispMethod):
                self.make_DispMethod(m)
            elif isinstance(m, typedesc.DispProperty):
                self.make_DispProperty(m)
            else:
                raise TypeError(m)
        print("]", file=self.stream)

    ################################################################
    # non-toplevel method generators
    #
    def make_ComMethod(self, m: typedesc.ComMethod, isdual: bool) -> None:
        self.imports.add("comtypes", "COMMETHOD")
        if isdual:
            self.imports.add("comtypes", "dispid")
        if __debug__ and m.doc:
            self.imports.add("comtypes", "helpstring")
        gen = ComMethodGenerator(m, isdual)
        print(gen.generate(), file=self.stream)
        self.last_item_class = False
        for typ, _, _, default in m.arguments:
            if isinstance(typ, typedesc.ComInterface):
                self.declarations.add(
                    "OPENARRAY",
                    "POINTER(c_ubyte)",
                    "hack, see comtypes/tools/codegenerator.py",
                )
            if default is not None:
                self.need_VARIANT_imports(default)

    def make_DispMethod(self, m: typedesc.DispMethod) -> None:
        self.imports.add("comtypes", "DISPMETHOD")
        self.imports.add("comtypes", "dispid")
        if __debug__ and m.doc:
            self.imports.add("comtypes", "helpstring")
        gen = DispMethodGenerator(m)
        print(gen.generate(), file=self.stream)
        self.last_item_class = False
        for _, _, _, default in m.arguments:
            if default is not None:
                self.need_VARIANT_imports(default)

    def make_DispProperty(self, prop: typedesc.DispProperty) -> None:
        self.imports.add("comtypes", "DISPPROPERTY")
        self.imports.add("comtypes", "dispid")
        if __debug__ and prop.doc:
            self.imports.add("comtypes", "helpstring")
        gen = DispPropertyGenerator(prop)
        print(gen.generate(), file=self.stream)
        self.last_item_class = False
