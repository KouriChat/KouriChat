import keyword
from typing import Any
from typing import List, Tuple
from typing import Iterator
from typing import Union as _UnionT

import comtypes
from comtypes.tools import typedesc
from comtypes.tools.codegenerator.modulenamer import name_wrapper_module


class lcid(object):
    def __repr__(self):
        return "_lcid"


lcid = lcid()


class dispid(object):
    def __init__(self, memid):
        self.memid = memid

    def __repr__(self):
        return f"dispid({self.memid})"


class helpstring(object):
    def __init__(self, text):
        self.text = text

    def __repr__(self):
        return f"helpstring({self.text!r})"


# XXX Should this be in ctypes itself?
ctypes_names = {
    "unsigned char": "c_ubyte",
    "signed char": "c_byte",
    "char": "c_char",
    "wchar_t": "c_wchar",
    "short unsigned int": "c_ushort",
    "short int": "c_short",
    "long unsigned int": "c_ulong",
    "long int": "c_long",
    "long signed int": "c_long",
    "unsigned int": "c_uint",
    "int": "c_int",
    "long long unsigned int": "c_ulonglong",
    "long long int": "c_longlong",
    "double": "c_double",
    "float": "c_float",
    # Hm...
    "void": "None",
}


def get_real_type(tp):
    if type(tp) is typedesc.Typedef:
        return get_real_type(tp.typ)
    elif isinstance(tp, typedesc.CvQualifiedType):
        return get_real_type(tp.typ)
    return tp


ASSUME_STRINGS = True


################################################################


_DefValType = _UnionT["lcid", Any, None]
_IdlFlagType = _UnionT[str, dispid, helpstring]


def _to_arg_definition(
    type_name: str,
    arg_name: str,
    idlflags: List[str],
    default: _DefValType,
) -> str:
    if default is not None:
        code = f"        ({idlflags!r}, {type_name}, '{arg_name}', {default!r})"
        if len(code) > 80:
            code = (
                "        (\n"
                f"            {idlflags!r},\n"
                f"            {type_name},\n"
                f"            '{arg_name}',\n"
                f"            {default!r}\n"
                "        )"
            )
    else:
        code = f"        ({idlflags!r}, {type_name}, '{arg_name}')"
        if len(code) > 80:
            code = (
                "        (\n"
                f"            {idlflags!r},\n"
                f"            {type_name},\n"
                f"            '{arg_name}',\n"
                "        )"
            )
    return code


class ComMethodGenerator(object):
    def __init__(self, m: typedesc.ComMethod, isdual: bool) -> None:
        self._m = m
        self._isdual = isdual
        self.data: List[str] = []
        self._to_type_name = TypeNamer()

    def generate(self) -> str:
        if not self._m.arguments:
            self._make_noargs()
        else:
            self._make_withargs()
        return "\n".join(self.data)

    def _get_common_elms(self) -> Tuple[List[_IdlFlagType], str, str]:
        idlflags: List[_IdlFlagType] = []
        if self._isdual:
            idlflags.append(dispid(self._m.memid))
            idlflags.extend(self._m.idlflags)
        else:  # We don't include the dispid for non-dispatch COM interfaces
            idlflags.extend(self._m.idlflags)
        if __debug__ and self._m.doc:
            idlflags.insert(1, helpstring(self._m.doc))
        type_name = self._to_type_name(self._m.returns)
        return (idlflags, type_name, self._m.name)

    def _make_noargs(self) -> None:
        flags, type_name, member_name = self._get_common_elms()
        code = f"    COMMETHOD({flags!r}, {type_name}, '{member_name}'),"
        if len(code) > 80:
            code = (
                "    COMMETHOD(\n"
                f"        {flags!r},\n"
                f"        {type_name},\n"
                f"        '{member_name}',\n"
                "    ),"
            )
        self.data.append(code)

    def _make_withargs(self) -> None:
        flags, type_name, member_name = self._get_common_elms()
        code = (
            "    COMMETHOD(\n"
            f"        {flags!r},\n"
            f"        {type_name},\n"
            f"        '{member_name}',"
        )
        self.data.append(code)
        arglist = [_to_arg_definition(*i) for i in self._iter_args()]
        self.data.append(",\n".join(arglist))
        self.data.append("    ),")

    def _iter_args(self) -> Iterator[Tuple[str, str, List[str], _DefValType]]:
        for typ, arg_name, _f, _defval in self._m.arguments:
            ###########################################################
            # IDL files that contain 'open arrays' or 'conformant
            # varying arrays' method parameters are strange.
            # These arrays have both a 'size_is()' and
            # 'length_is()' attribute, like this example from
            # dia2.idl (in the DIA SDK):
            #
            # interface IDiaSymbol: IUnknown {
            # ...
            #     HRESULT get_dataBytes(
            #         [in] DWORD cbData,
            #         [out] DWORD *pcbData,
            #         [out, size_is(cbData),
            #          length_is(*pcbData)] BYTE data[]
            #     );
            #
            # The really strange thing is that the decompiled type
            # library then contains this declaration, which declares
            # the interface itself as [out] method parameter:
            #
            # interface IDiaSymbol: IUnknown {
            # ...
            #     HRESULT _stdcall get_dataBytes(
            #         [in] unsigned long cbData,
            #         [out] unsigned long* pcbData,
            #         [out] IDiaSymbol data);
            #
            # Of course, comtypes does not accept a COM interface
            # as method parameter; so replace the parameter type
            # with the comtypes spelling of 'unsigned char *', and
            # mark the parameter as [in, out], so the IDL
            # equivalent would be like this:
            #
            # interface IDiaSymbol: IUnknown {
            # ...
            #     HRESULT _stdcall get_dataBytes(
            #         [in] unsigned long cbData,
            #         [out] unsigned long* pcbData,
            #         [in, out] BYTE data[]);
            ###########################################################
            idlflags = list(_f)  # shallow copy to avoid side effects
            if isinstance(typ, typedesc.ComInterface):
                type_name = "OPENARRAY"
                if "in" not in idlflags:
                    idlflags.append("in")
            else:
                type_name = self._to_type_name(typ)
            if "lcid" in idlflags:  # and 'in' in idlflags:
                default = lcid
            else:
                default = _defval
            yield (type_name, arg_name, idlflags, default)


class DispMethodGenerator(object):
    def __init__(self, m: typedesc.DispMethod) -> None:
        self._m = m
        self.data: List[str] = []
        self._to_type_name = TypeNamer()

    def generate(self) -> str:
        if not self._m.arguments:
            self._make_noargs()
        else:
            self._make_withargs()
        return "\n".join(self.data)

    def _get_common_elms(self) -> Tuple[List[_IdlFlagType], str, str]:
        idlflags: List[_IdlFlagType] = []
        idlflags.append(dispid(self._m.dispid))
        idlflags.extend(self._m.idlflags)
        if __debug__ and self._m.doc:
            idlflags.insert(1, helpstring(self._m.doc))
        type_name = self._to_type_name(self._m.returns)
        return (idlflags, type_name, self._m.name)

    def _make_noargs(self) -> None:
        flags, type_name, member_name = self._get_common_elms()
        code = f"    DISPMETHOD({flags!r}, {type_name}, '{member_name}'),"
        if len(code) > 80:
            code = (
                "    DISPMETHOD(\n"
                f"        {flags!r},\n"
                f"        {type_name},\n"
                f"        '{member_name}',\n"
                "    ),"
            )
        self.data.append(code)

    def _make_withargs(self) -> None:
        flags, type_name, member_name = self._get_common_elms()
        code = (
            "    DISPMETHOD(\n"
            f"        {flags!r},\n"
            f"        {type_name},\n"
            f"        '{member_name}',"
        )
        self.data.append(code)
        arglist = [_to_arg_definition(*i) for i in self._iter_args()]
        self.data.append(",\n".join(arglist))
        self.data.append("    ),")

    def _iter_args(self) -> Iterator[Tuple[str, str, List[str], _DefValType]]:
        for typ, arg_name, idlflags, default in self._m.arguments:
            type_name = self._to_type_name(typ)
            yield (type_name, arg_name, idlflags, default)


class DispPropertyGenerator(object):
    def __init__(self, m: typedesc.DispProperty) -> None:
        self._m = m
        self._to_type_name = TypeNamer()

    def generate(self) -> str:
        flags, type_name, member_name = self._get_common_elms()
        code = f"    DISPPROPERTY({flags!r}, {type_name}, '{member_name}'),"
        if len(code) > 80:
            code = (
                "    DISPPROPERTY(\n"
                f"        {flags!r},\n"
                f"        {type_name},\n"
                f"        '{member_name}'\n"
                "    ),"
            )
        return code

    def _get_common_elms(self) -> Tuple[List[_IdlFlagType], str, str]:
        idlflags: List[_IdlFlagType] = []
        idlflags.append(dispid(self._m.dispid))
        idlflags.extend(self._m.idlflags)
        if __debug__ and self._m.doc:
            idlflags.insert(1, helpstring(self._m.doc))
        type_name = self._to_type_name(self._m.typ)
        return (idlflags, type_name, self._m.name)


class TypeNamer(object):
    def __call__(self, t: Any) -> str:
        # Return a string, containing an expression which can be used
        # to refer to the type. Assumes the 'from ctypes import *'
        # namespace is available.
        if isinstance(t, typedesc.SAFEARRAYType):
            return f"_midlSAFEARRAY({self(t.typ)})"
        # if isinstance(t, typedesc.CoClass):
        #     return "%s._com_interfaces_[0]" % t.name
        if isinstance(t, typedesc.Typedef):
            return t.name
        if isinstance(t, typedesc.PointerType):
            _t, pcnt = self._inspect_PointerType(t)
            return f"{'POINTER(' * pcnt}{self(_t)}{')' * pcnt}"
        elif isinstance(t, typedesc.ArrayType):
            return f"{self(t.typ)} * {int(t.max) + 1}"
        elif isinstance(t, typedesc.FunctionType):
            args = [self(x) for x in [t.returns] + list(t.iterArgTypes())]
            if "__stdcall__" in t.attributes:
                return f"WINFUNCTYPE({', '.join(args)})"
            else:
                return f"CFUNCTYPE({', '.join(args)})"
        elif isinstance(t, typedesc.CvQualifiedType):
            # const and volatile are ignored
            return "%s" % self(t.typ)
        elif isinstance(t, typedesc.FundamentalType):
            return ctypes_names[t.name]
        elif isinstance(t, typedesc.Structure):
            return t.name
        elif isinstance(t, typedesc.Enumeration):
            if t.name:
                return t.name
            return "c_int"  # enums are integers
        elif isinstance(t, typedesc.EnumValue):
            if keyword.iskeyword(t.name):
                return t.name + "_"
            return t.name
        elif isinstance(t, typedesc.External):
            # t.symbol_name - symbol to generate
            # t.tlib - the ITypeLib pointer to the typelibrary containing the symbols definition
            modname = name_wrapper_module(t.tlib)
            return f"{modname}.{t.symbol_name}"
        return t.name

    def _inspect_PointerType(
        self, t: typedesc.PointerType, count: int = 0
    ) -> Tuple[Any, int]:
        if ASSUME_STRINGS:
            x = get_real_type(t.typ)
            if isinstance(x, typedesc.FundamentalType):
                if x.name == "char":
                    return typedesc.Typedef("STRING", x), count
                elif x.name == "wchar_t":
                    return typedesc.Typedef("WSTRING", x), count
        if isinstance(t.typ, typedesc.FunctionType):
            return t.typ, count
        if isinstance(t.typ, typedesc.FundamentalType):
            if t.typ.name == "void":
                return typedesc.Typedef("c_void_p", t.typ), count
        if isinstance(t.typ, typedesc.PointerType):
            return self._inspect_PointerType(t.typ, count + 1)
        return t.typ, count + 1
