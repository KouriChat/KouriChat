import os
import sys
from typing import Any
from typing import Dict, List, Optional, Tuple
from ctypes import alignment, byref, c_void_p, sizeof, windll

from comtypes import automation, BSTR, COMError, typeinfo
from comtypes.tools import typedesc
from comtypes.client._code_cache import _get_module_filename


# Is the process 64-bit?
is_64bits = sys.maxsize > 2**32


################################


def PTR(typ):
    return typedesc.PointerType(typ, sizeof(c_void_p) * 8, alignment(c_void_p) * 8)


# basic C data types, with size and alignment in bits
char_type = typedesc.FundamentalType("char", 8, 8)
uchar_type = typedesc.FundamentalType("unsigned char", 8, 8)
wchar_t_type = typedesc.FundamentalType("wchar_t", 16, 16)
short_type = typedesc.FundamentalType("short int", 16, 16)
ushort_type = typedesc.FundamentalType("short unsigned int", 16, 16)
int_type = typedesc.FundamentalType("int", 32, 32)
uint_type = typedesc.FundamentalType("unsigned int", 32, 32)
long_type = typedesc.FundamentalType("long int", 32, 32)
ulong_type = typedesc.FundamentalType("long unsigned int", 32, 32)
longlong_type = typedesc.FundamentalType("long long int", 64, 64)
ulonglong_type = typedesc.FundamentalType("long long unsigned int", 64, 64)
float_type = typedesc.FundamentalType("float", 32, 32)
double_type = typedesc.FundamentalType("double", 64, 64)
void_type = typedesc.FundamentalType("void", 0, 0)

# basic COM data types
BSTR_type = typedesc.Typedef("BSTR", PTR(wchar_t_type))
SCODE_type = typedesc.Typedef("SCODE", int_type)
VARIANT_BOOL_type = typedesc.Typedef("VARIANT_BOOL", short_type)
HRESULT_type = typedesc.Typedef("HRESULT", ulong_type)

VARIANT_type = typedesc.Structure(
    "VARIANT",
    align=alignment(automation.VARIANT) * 8,
    members=[],
    bases=[],
    size=sizeof(automation.VARIANT) * 8,
)
IDISPATCH_type = typedesc.Typedef("IDispatch", None)
IUNKNOWN_type = typedesc.Typedef("IUnknown", None)
DECIMAL_type = typedesc.Structure(
    "DECIMAL",
    align=alignment(automation.DECIMAL) * 8,
    members=[],
    bases=[],
    size=sizeof(automation.DECIMAL) * 8,
)


def midlSAFEARRAY(typ):
    return typedesc.SAFEARRAYType(typ)


# faked COM data types
CURRENCY_type = longlong_type  # slightly wrong; should be scaled by 10000 - use subclass of longlong?
DATE_type = double_type  # not *that* wrong...

COMTYPES = {
    automation.VT_I2: short_type,  # 2
    automation.VT_I4: int_type,  # 3
    automation.VT_R4: float_type,  # 4
    automation.VT_R8: double_type,  # 5
    automation.VT_CY: CURRENCY_type,  # 6
    automation.VT_DATE: DATE_type,  # 7
    automation.VT_BSTR: BSTR_type,  # 8
    automation.VT_DISPATCH: PTR(IDISPATCH_type),  # 9
    automation.VT_ERROR: SCODE_type,  # 10
    automation.VT_BOOL: VARIANT_BOOL_type,  # 11
    automation.VT_VARIANT: VARIANT_type,  # 12
    automation.VT_UNKNOWN: PTR(IUNKNOWN_type),  # 13
    automation.VT_DECIMAL: DECIMAL_type,  # 14
    automation.VT_I1: char_type,  # 16
    automation.VT_UI1: uchar_type,  # 17
    automation.VT_UI2: ushort_type,  # 18
    automation.VT_UI4: ulong_type,  # 19
    automation.VT_I8: longlong_type,  # 20
    automation.VT_UI8: ulonglong_type,  # 21
    automation.VT_INT: int_type,  # 22
    automation.VT_UINT: uint_type,  # 23
    automation.VT_VOID: void_type,  # 24
    automation.VT_HRESULT: HRESULT_type,  # 25
    automation.VT_LPSTR: PTR(char_type),  # 30
    automation.VT_LPWSTR: PTR(wchar_t_type),  # 31
}

# automation.VT_PTR = 26 # below
# automation.VT_SAFEARRAY = 27
# automation.VT_CARRAY = 28 # below
# automation.VT_USERDEFINED = 29 # below

# automation.VT_RECORD = 36

# automation.VT_ARRAY = 8192
# automation.VT_BYREF = 16384

################################################################


class Parser(object):
    tlib: typeinfo.ITypeLib
    items: Dict[str, Any]

    def make_type(self, tdesc: typeinfo.TYPEDESC, tinfo: typeinfo.ITypeInfo) -> Any:
        if tdesc.vt in COMTYPES:
            return COMTYPES[tdesc.vt]
        if tdesc.vt == automation.VT_CARRAY:
            arraydesc: typeinfo.tagARRAYDESC = tdesc._.lpadesc[0]
            typ = self.make_type(arraydesc.tdescElem, tinfo)
            for i in range(arraydesc.cDims):
                typ = typedesc.ArrayType(
                    typ,
                    arraydesc.rgbounds[i].lLbound,
                    arraydesc.rgbounds[i].cElements - 1,
                )
            return typ
        elif tdesc.vt == automation.VT_PTR:
            return PTR(self.make_type(tdesc._.lptdesc[0], tinfo))
        elif tdesc.vt == automation.VT_USERDEFINED:
            try:
                ti = tinfo.GetRefTypeInfo(tdesc._.hreftype)
            except COMError as details:
                type_name = f"__error_hreftype_{tdesc._.hreftype:d}__"
                tlib_name = get_tlib_filename(self.tlib)
                if tlib_name is None:
                    tlib_name = "unknown typelib"
                message = (
                    f"\n\tGetRefTypeInfo failed in {tlib_name}: {details}"
                    f"\n\tgenerating type '{type_name}' instead"
                )
                import warnings

                warnings.warn(message, UserWarning)
                result = typedesc.Structure(
                    type_name, align=8, members=[], bases=[], size=0
                )
                return result
            result = self.parse_typeinfo(ti)
            assert result is not None, ti.GetDocumentation(-1)[0]
            return result
        elif tdesc.vt == automation.VT_SAFEARRAY:
            # SAFEARRAY(<type>), see Don Box pp.331f
            return midlSAFEARRAY(self.make_type(tdesc._.lptdesc[0], tinfo))
        raise NotImplementedError(tdesc.vt)

    ################################################################

    # TKIND_ENUM = 0
    def ParseEnum(
        self, tinfo: typeinfo.ITypeInfo, ta: typeinfo.TYPEATTR
    ) -> typedesc.Enumeration:
        ta = tinfo.GetTypeAttr()
        enum_name = tinfo.GetDocumentation(-1)[0]
        enum = typedesc.Enumeration(enum_name, 32, 32)
        self._register(enum_name, enum)

        for i in range(ta.cVars):
            vd = tinfo.GetVarDesc(i)
            name = tinfo.GetDocumentation(vd.memid)[0]
            assert vd.varkind == typeinfo.VAR_CONST
            num_val: int = vd._.lpvarValue[0].value
            v = typedesc.EnumValue(name, num_val, enum)
            enum.add_value(v)
        return enum

    # TKIND_RECORD = 1
    def ParseRecord(
        self, tinfo: typeinfo.ITypeInfo, ta: typeinfo.TYPEATTR
    ) -> typedesc.Structure:
        members = []  # will be filled later
        struct_name, doc, helpcntext, helpfile = tinfo.GetDocumentation(-1)
        struct = typedesc.Structure(
            struct_name,
            align=ta.cbAlignment * 8,
            members=members,
            bases=[],
            size=ta.cbSizeInstance * 8,
        )
        self._register(struct_name, struct)

        tlib, _ = tinfo.GetContainingTypeLib()
        tlib_ta = tlib.GetLibAttr()
        # If this is a 32-bit typlib being loaded in a 64-bit process, then the
        # size and alignment are incorrect. Set the size to None to disable
        # size checks and correct the alignment.
        if is_64bits and tlib_ta.syskind == typeinfo.SYS_WIN32:
            struct.size = None
            struct.align = 64

        if ta.guid:
            struct._recordinfo_ = (
                str(tlib_ta.guid),
                tlib_ta.wMajorVerNum,
                tlib_ta.wMinorVerNum,
                tlib_ta.lcid,
                str(ta.guid),
            )

        for i in range(ta.cVars):
            vd = tinfo.GetVarDesc(i)
            name = tinfo.GetDocumentation(vd.memid)[0]
            offset = vd._.oInst * 8
            assert vd.varkind == typeinfo.VAR_PERINSTANCE
            typ = self.make_type(vd.elemdescVar.tdesc, tinfo)
            field = typedesc.Field(name, typ, None, offset)  # bits
            members.append(field)
        return struct

    # TKIND_MODULE = 2
    def ParseModule(self, tinfo: typeinfo.ITypeInfo, ta: typeinfo.TYPEATTR) -> None:
        assert 0 == ta.cImplTypes
        # functions
        for i in range(ta.cFuncs):
            # We skip all function definitions.  There are several
            # problems with these, and we can, for comtypes, ignore them.
            continue
            fd = tinfo.GetFuncDesc(i)
            dllname, func_name, ordinal = tinfo.GetDllEntry(fd.memid, fd.invkind)
            func_doc = tinfo.GetDocumentation(fd.memid)[1]
            assert 0 == fd.cParamsOpt  # XXX
            returns = self.make_type(fd.elemdescFunc.tdesc, tinfo)

            if fd.callconv == typeinfo.CC_CDECL:
                attributes = "__cdecl__"
            elif fd.callconv == typeinfo.CC_STDCALL:
                attributes = "__stdcall__"
            else:
                raise ValueError("calling convention %d" % fd.callconv)

            func = typedesc.Function(func_name, returns, attributes, extern=1)
            if func_doc is not None:
                func.doc = func_doc.encode("mbcs")
            func.dllname = dllname
            self._register(func_name, func)
            for i in range(fd.cParams):
                argtype = self.make_type(fd.lprgelemdescParam[i].tdesc, tinfo)
                func.add_argument(argtype)

        # constants
        for i in range(ta.cVars):
            vd = tinfo.GetVarDesc(i)
            name, var_doc = tinfo.GetDocumentation(vd.memid)[0:2]
            assert vd.varkind == typeinfo.VAR_CONST
            typ = self.make_type(vd.elemdescVar.tdesc, tinfo)
            var_value = vd._.lpvarValue[0].value
            v = typedesc.Constant(name, typ, var_value, var_doc)
            self._register(name, v)

    # TKIND_INTERFACE = 3
    def ParseInterface(
        self, tinfo: typeinfo.ITypeInfo, ta: typeinfo.TYPEATTR
    ) -> Optional[typedesc.ComInterface]:
        itf_name, itf_doc = tinfo.GetDocumentation(-1)[0:2]
        assert ta.cImplTypes <= 1
        if ta.cImplTypes == 0 and itf_name != "IUnknown":
            # Windows defines an interface IOleControlTypes in ocidl.idl.
            # Don't known what artefact that is - we ignore it.
            # It's an interface without methods anyway.
            if itf_name != "IOleControlTypes":
                message = f"Ignoring interface {itf_name} which has no base interface"
                import warnings

                warnings.warn(message, UserWarning)
            return None

        iid = str(ta.guid)
        idlflags = self.interface_type_flags(ta.wTypeFlags)
        itf = typedesc.ComInterface(itf_name, None, iid, idlflags, itf_doc)
        self._register(itf_name, itf)

        if ta.cImplTypes:
            hr = tinfo.GetRefTypeOfImplType(0)
            tibase = tinfo.GetRefTypeInfo(hr)
            itf.base = self.parse_typeinfo(tibase)

        assert ta.cVars == 0, "vars on an Interface?"

        members: List[Tuple[int, typedesc.ComMethod]] = []
        for i in range(ta.cFuncs):
            fd = tinfo.GetFuncDesc(i)
            func_name, func_doc = tinfo.GetDocumentation(fd.memid)[:2]
            assert fd.funckind == typeinfo.FUNC_PUREVIRTUAL
            returns = self.make_type(fd.elemdescFunc.tdesc, tinfo)
            names = tinfo.GetNames(fd.memid, fd.cParams + 1)
            names.append("rhs")
            names = names[: fd.cParams + 1]
            # function name first, then parameter names
            assert len(names) == fd.cParams + 1
            flags = self.func_flags(fd.wFuncFlags)
            flags += self.inv_kind(fd.invkind)
            mth = typedesc.ComMethod(
                fd.invkind, fd.memid, func_name, returns, flags, func_doc
            )
            for j in range(fd.cParams):
                elemdesc = fd.lprgelemdescParam[j]
                typ = self.make_type(elemdesc.tdesc, tinfo)
                name = names[j + 1]
                paramdesc = elemdesc._.paramdesc
                if paramdesc.wParamFlags & typeinfo.PARAMFLAG_FHASDEFAULT:
                    # XXX should be handled by VARIANT itself
                    default: Any = paramdesc.pparamdescex[0].varDefaultValue.value
                else:
                    default = None
                param_flags = self.param_flags(paramdesc.wParamFlags)
                mth.add_argument(typ, name, param_flags, default)
            members.append((fd.oVft, mth))
        # Sort the methods by oVft (VTable offset): Some typeinfo
        # don't list methods in VTable order.
        members.sort()
        itf.extend_members([m for _, m in members])

        return itf

    # TKIND_DISPATCH = 4
    def ParseDispatch(
        self, tinfo: typeinfo.ITypeInfo, ta: typeinfo.TYPEATTR
    ) -> typedesc.DispInterface:
        itf_name, doc = tinfo.GetDocumentation(-1)[0:2]
        assert ta.cImplTypes == 1
        hr = tinfo.GetRefTypeOfImplType(0)
        tibase = tinfo.GetRefTypeInfo(hr)
        base = self.parse_typeinfo(tibase)
        iid = str(ta.guid)
        idlflags = self.interface_type_flags(ta.wTypeFlags)
        doc = str(doc.split("\0")[0]) if doc is not None else doc
        itf = typedesc.DispInterface(itf_name, base, iid, idlflags, doc)
        self._register(itf_name, itf)

        # This code can only handle pure dispinterfaces.  Dual
        # interfaces are parsed in ParseInterface().
        assert ta.wTypeFlags & typeinfo.TYPEFLAG_FDUAL == 0

        for i in range(ta.cVars):
            vd = tinfo.GetVarDesc(i)
            assert vd.varkind == typeinfo.VAR_DISPATCH
            var_name, var_doc = tinfo.GetDocumentation(vd.memid)[0:2]
            typ = self.make_type(vd.elemdescVar.tdesc, tinfo)
            mth = typedesc.DispProperty(
                vd.memid, var_name, typ, self.var_flags(vd.wVarFlags), var_doc
            )
            itf.add_member(mth)

        # At least the EXCEL typelib lists the IUnknown and IDispatch
        # methods even for this kind of interface.  I didn't find any
        # indication about these methods in the various flags, so we
        # have to exclude them by name.
        # CLF: 12/14/2012 Do this in a way that does not exclude other methods.
        #      I have encountered typlibs where only "QueryInterface", "AddRef"
        #      and "Release" are to be skipped.
        ignored_names = set(
            [
                "QueryInterface",
                "AddRef",
                "Release",
                "GetTypeInfoCount",
                "GetTypeInfo",
                "GetIDsOfNames",
                "Invoke",
            ]
        )

        for i in range(ta.cFuncs):
            fd = tinfo.GetFuncDesc(i)
            func_name, func_doc = tinfo.GetDocumentation(fd.memid)[:2]
            if func_name in ignored_names:
                continue
            assert fd.funckind == typeinfo.FUNC_DISPATCH

            returns = self.make_type(fd.elemdescFunc.tdesc, tinfo)
            names = tinfo.GetNames(fd.memid, fd.cParams + 1)
            names.append("rhs")
            names = names[: fd.cParams + 1]
            # function name first, then parameter names
            assert len(names) == fd.cParams + 1
            flags = self.func_flags(fd.wFuncFlags)
            flags += self.inv_kind(fd.invkind)
            mth = typedesc.DispMethod(
                fd.memid, fd.invkind, func_name, returns, flags, func_doc
            )
            for j in range(fd.cParams):
                elemdesc = fd.lprgelemdescParam[j]
                typ = self.make_type(elemdesc.tdesc, tinfo)
                name = names[j + 1]
                paramdesc = elemdesc._.paramdesc
                if paramdesc.wParamFlags & typeinfo.PARAMFLAG_FHASDEFAULT:
                    # XXX should be handled by VARIANT itself
                    default: Any = paramdesc.pparamdescex[0].varDefaultValue.value
                else:
                    default = None
                param_flags = self.param_flags(paramdesc.wParamFlags)
                mth.add_argument(typ, name, param_flags, default)
            itf.add_member(mth)
        return itf

    def inv_kind(self, invkind: int) -> List[str]:
        NAMES = {
            automation.DISPATCH_METHOD: [],
            automation.DISPATCH_PROPERTYPUT: ["propput"],
            automation.DISPATCH_PROPERTYPUTREF: ["propputref"],
            automation.DISPATCH_PROPERTYGET: ["propget"],
        }
        return NAMES[invkind]

    def func_flags(self, flags: int) -> List[str]:
        # map FUNCFLAGS values to idl attributes
        NAMES = {
            typeinfo.FUNCFLAG_FRESTRICTED: "restricted",
            typeinfo.FUNCFLAG_FSOURCE: "source",
            typeinfo.FUNCFLAG_FBINDABLE: "bindable",
            typeinfo.FUNCFLAG_FREQUESTEDIT: "requestedit",
            typeinfo.FUNCFLAG_FDISPLAYBIND: "displaybind",
            typeinfo.FUNCFLAG_FDEFAULTBIND: "defaultbind",
            typeinfo.FUNCFLAG_FHIDDEN: "hidden",
            typeinfo.FUNCFLAG_FUSESGETLASTERROR: "usesgetlasterror",
            typeinfo.FUNCFLAG_FDEFAULTCOLLELEM: "defaultcollelem",
            typeinfo.FUNCFLAG_FUIDEFAULT: "uidefault",
            typeinfo.FUNCFLAG_FNONBROWSABLE: "nonbrowsable",
            # typeinfo.FUNCFLAG_FREPLACEABLE: "???",
            typeinfo.FUNCFLAG_FIMMEDIATEBIND: "immediatebind",
        }
        return [NAMES[bit] for bit in NAMES if bit & flags]

    def param_flags(self, flags: int) -> List[str]:
        # map PARAMFLAGS values to idl attributes
        NAMES = {
            typeinfo.PARAMFLAG_FIN: "in",
            typeinfo.PARAMFLAG_FOUT: "out",
            typeinfo.PARAMFLAG_FLCID: "lcid",
            typeinfo.PARAMFLAG_FRETVAL: "retval",
            typeinfo.PARAMFLAG_FOPT: "optional",
            # typeinfo.PARAMFLAG_FHASDEFAULT: "",
            # typeinfo.PARAMFLAG_FHASCUSTDATA: "",
        }
        return [NAMES[bit] for bit in NAMES if bit & flags]

    def coclass_type_flags(self, flags: int) -> List[str]:
        # map TYPEFLAGS values to idl attributes
        NAMES = {
            typeinfo.TYPEFLAG_FAPPOBJECT: "appobject",
            # typeinfo.TYPEFLAG_FCANCREATE:
            typeinfo.TYPEFLAG_FLICENSED: "licensed",
            # typeinfo.TYPEFLAG_FPREDECLID:
            typeinfo.TYPEFLAG_FHIDDEN: "hidden",
            typeinfo.TYPEFLAG_FCONTROL: "control",
            typeinfo.TYPEFLAG_FDUAL: "dual",
            typeinfo.TYPEFLAG_FNONEXTENSIBLE: "nonextensible",
            typeinfo.TYPEFLAG_FOLEAUTOMATION: "oleautomation",
            typeinfo.TYPEFLAG_FRESTRICTED: "restricted",
            typeinfo.TYPEFLAG_FAGGREGATABLE: "aggregatable",
            # typeinfo.TYPEFLAG_FREPLACEABLE:
            # typeinfo.TYPEFLAG_FDISPATCHABLE # computed, no flag for this
            typeinfo.TYPEFLAG_FREVERSEBIND: "reversebind",
            typeinfo.TYPEFLAG_FPROXY: "proxy",
        }
        NEGATIVE_NAMES = {typeinfo.TYPEFLAG_FCANCREATE: "noncreatable"}
        return [NAMES[bit] for bit in NAMES if bit & flags] + [
            NEGATIVE_NAMES[bit] for bit in NEGATIVE_NAMES if not (bit & flags)
        ]

    def interface_type_flags(self, flags: int) -> List[str]:
        # map TYPEFLAGS values to idl attributes
        NAMES = {
            typeinfo.TYPEFLAG_FAPPOBJECT: "appobject",
            # typeinfo.TYPEFLAG_FCANCREATE:
            typeinfo.TYPEFLAG_FLICENSED: "licensed",
            # typeinfo.TYPEFLAG_FPREDECLID:
            typeinfo.TYPEFLAG_FHIDDEN: "hidden",
            typeinfo.TYPEFLAG_FCONTROL: "control",
            typeinfo.TYPEFLAG_FDUAL: "dual",
            typeinfo.TYPEFLAG_FNONEXTENSIBLE: "nonextensible",
            typeinfo.TYPEFLAG_FOLEAUTOMATION: "oleautomation",
            typeinfo.TYPEFLAG_FRESTRICTED: "restricted",
            typeinfo.TYPEFLAG_FAGGREGATABLE: "aggregatable",
            # typeinfo.TYPEFLAG_FREPLACEABLE:
            # typeinfo.TYPEFLAG_FDISPATCHABLE # computed, no flag for this
            typeinfo.TYPEFLAG_FREVERSEBIND: "reversebind",
            typeinfo.TYPEFLAG_FPROXY: "proxy",
        }
        NEGATIVE_NAMES = {}
        return [NAMES[bit] for bit in NAMES if bit & flags] + [
            NEGATIVE_NAMES[bit] for bit in NEGATIVE_NAMES if not (bit & flags)
        ]

    def var_flags(self, flags: int) -> List[str]:
        NAMES = {
            typeinfo.VARFLAG_FREADONLY: "readonly",
            typeinfo.VARFLAG_FSOURCE: "source",
            typeinfo.VARFLAG_FBINDABLE: "bindable",
            typeinfo.VARFLAG_FREQUESTEDIT: "requestedit",
            typeinfo.VARFLAG_FDISPLAYBIND: "displaybind",
            typeinfo.VARFLAG_FDEFAULTBIND: "defaultbind",
            typeinfo.VARFLAG_FHIDDEN: "hidden",
            typeinfo.VARFLAG_FRESTRICTED: "restricted",
            typeinfo.VARFLAG_FDEFAULTCOLLELEM: "defaultcollelem",
            typeinfo.VARFLAG_FUIDEFAULT: "uidefault",
            typeinfo.VARFLAG_FNONBROWSABLE: "nonbrowsable",
            typeinfo.VARFLAG_FREPLACEABLE: "replaceable",
            typeinfo.VARFLAG_FIMMEDIATEBIND: "immediatebind",
        }
        return [NAMES[bit] for bit in NAMES if bit & flags]

    # TKIND_COCLASS = 5
    def ParseCoClass(
        self, tinfo: typeinfo.ITypeInfo, ta: typeinfo.TYPEATTR
    ) -> typedesc.CoClass:
        # possible ta.wTypeFlags: helpstring, helpcontext, licensed,
        #        version, control, hidden, and appobject
        coclass_name, doc = tinfo.GetDocumentation(-1)[0:2]
        tlibattr = tinfo.GetContainingTypeLib()[0].GetLibAttr()
        clsid = str(ta.guid)
        idlflags = self.coclass_type_flags(ta.wTypeFlags)
        coclass = typedesc.CoClass(coclass_name, clsid, idlflags, tlibattr, doc)
        self._register(coclass_name, coclass)

        for i in range(ta.cImplTypes):
            hr = tinfo.GetRefTypeOfImplType(i)
            ti = tinfo.GetRefTypeInfo(hr)
            itf = self.parse_typeinfo(ti)
            flags = tinfo.GetImplTypeFlags(i)
            coclass.add_interface(itf, flags)
        return coclass

    # TKIND_ALIAS = 6
    def ParseAlias(
        self, tinfo: typeinfo.ITypeInfo, ta: typeinfo.TYPEATTR
    ) -> typedesc.Typedef:
        name = tinfo.GetDocumentation(-1)[0]
        typ = self.make_type(ta.tdescAlias, tinfo)
        alias = typedesc.Typedef(name, typ)
        self._register(name, alias)
        return alias

    # TKIND_UNION = 7
    def ParseUnion(
        self, tinfo: typeinfo.ITypeInfo, ta: typeinfo.TYPEATTR
    ) -> typedesc.Union:
        union_name, doc, helpcntext, helpfile = tinfo.GetDocumentation(-1)
        members = []
        union = typedesc.Union(
            union_name,
            align=ta.cbAlignment * 8,
            members=members,
            bases=[],
            size=ta.cbSizeInstance * 8,
        )
        self._register(union_name, union)

        tlib, _ = tinfo.GetContainingTypeLib()
        tlib_ta = tlib.GetLibAttr()
        # If this is a 32-bit typlib being loaded in a 64-bit process, then the
        # size and alignment are incorrect. Set the size to None to disable
        # size checks and correct the alignment.
        if is_64bits and tlib_ta.syskind == typeinfo.SYS_WIN32:
            union.size = None
            union.align = 64

        for i in range(ta.cVars):
            vd = tinfo.GetVarDesc(i)
            name = tinfo.GetDocumentation(vd.memid)[0]
            offset = vd._.oInst * 8
            assert vd.varkind == typeinfo.VAR_PERINSTANCE
            typ = self.make_type(vd.elemdescVar.tdesc, tinfo)
            field = typedesc.Field(name, typ, None, offset)  # bits
            members.append(field)
        return union

    ################################################################

    def _typelib_module(self, tlib: Optional[typeinfo.ITypeLib] = None) -> str:
        if tlib is None:
            tlib = self.tlib
        # return a string that uniquely identifies a typelib.
        # The string doesn't have any meaning outside this instance.
        return str(tlib.GetLibAttr())

    def _register(
        self, name: Optional[str], value: Any, tlib: Optional[typeinfo.ITypeLib] = None
    ) -> None:
        modname = self._typelib_module(tlib)
        fullname = f"{modname}.{name}"
        if fullname in self.items:
            # XXX Can we really allow this? It happens, at least.
            if isinstance(value, typedesc.External):
                return
            # BUG: We try to register an item that's already registered.
            raise ValueError(f"Bug: Multiple registered name '{name}': {value!r}")
        self.items[fullname] = value

    def parse_typeinfo(self, tinfo: typeinfo.ITypeInfo) -> Any:
        name = tinfo.GetDocumentation(-1)[0]
        modname = self._typelib_module()
        try:
            return self.items[f"{modname}.{name}"]
        except KeyError:
            pass

        tlib = tinfo.GetContainingTypeLib()[0]
        if tlib != self.tlib:
            return self._parse_External(name, tlib, tinfo)

        ta = tinfo.GetTypeAttr()
        tkind = ta.typekind

        if tkind == typeinfo.TKIND_ENUM:  # 0
            return self.ParseEnum(tinfo, ta)
        elif tkind == typeinfo.TKIND_RECORD:  # 1
            return self.ParseRecord(tinfo, ta)
        elif tkind == typeinfo.TKIND_MODULE:  # 2
            return self.ParseModule(tinfo, ta)
        elif tkind == typeinfo.TKIND_INTERFACE:  # 3
            return self.ParseInterface(tinfo, ta)
        elif tkind == typeinfo.TKIND_DISPATCH:  # 4
            try:
                # GetRefTypeOfImplType(-1) returns the custom portion
                # of a dispinterface, if it is dual
                href = tinfo.GetRefTypeOfImplType(-1)
            except COMError:
                # no dual interface
                return self.ParseDispatch(tinfo, ta)
            return self._parse_DualInterface(tinfo.GetRefTypeInfo(href))
        elif tkind == typeinfo.TKIND_COCLASS:  # 5
            return self.ParseCoClass(tinfo, ta)
        elif tkind == typeinfo.TKIND_ALIAS:  # 6
            return self.ParseAlias(tinfo, ta)
        elif tkind == typeinfo.TKIND_UNION:  # 7
            return self.ParseUnion(tinfo, ta)
        else:
            print("NYI", tkind)
            # raise "NYI", tkind

    def _parse_DualInterface(
        self, tinfo: typeinfo.ITypeInfo
    ) -> Optional[typedesc.ComInterface]:
        ta = tinfo.GetTypeAttr()
        assert ta.typekind == typeinfo.TKIND_INTERFACE
        return self.ParseInterface(tinfo, ta)

    def _parse_External(
        self, name: str, tlib: typeinfo.ITypeLib, tinfo: typeinfo.ITypeInfo
    ) -> typedesc.External:
        ta = tinfo.GetTypeAttr()
        size = ta.cbSizeInstance * 8
        align = ta.cbAlignment * 8
        docs = tlib.GetDocumentation(-1)[:2]
        typ = typedesc.External(tlib, name, size, align, docs)
        self._register(name, typ, tlib)
        return typ

    def parse_LibraryDescription(self):
        la = self.tlib.GetLibAttr()
        name, doc = self.tlib.GetDocumentation(-1)[:2]
        desc = typedesc.TypeLib(
            name, str(la.guid), la.wMajorVerNum, la.wMinorVerNum, doc
        )
        self._register(None, desc)

    ################################################################

    def parse(self):
        self.parse_LibraryDescription()

        for i in range(self.tlib.GetTypeInfoCount()):
            tinfo = self.tlib.GetTypeInfo(i)
            self.parse_typeinfo(tinfo)
        return self.items


class TlbFileParser(Parser):
    "Parses a type library from a file"

    def __init__(self, path):
        # XXX DOESN'T LOOK CORRECT: We should NOT register the typelib.
        self.tlib = typeinfo.LoadTypeLibEx(path)  # , regkind=typeinfo.REGKIND_REGISTER)
        self.items = {}


class TypeLibParser(Parser):
    def __init__(self, tlib):
        self.tlib = tlib
        self.items = {}


################################################################
# some interesting typelibs

# these do NOT work:
# XXX infinite loop?
# path = r"mshtml.tlb" # has propputref

# has SAFEARRAY
# HRESULT Run(BSTR, SAFEARRAY(VARIANT)*, VARIANT*)
# path = "msscript.ocx"

# has SAFEARRAY
# HRESULT AddAddress(SAFEARRAY(BSTR)*, SAFEARRAY(BSTR)*)
# path = r"c:\Programme\Microsoft Office\Office\MSWORD8.OLB" # has propputref

# has SAFEARRAY:
# SAFEARRAY(unsigned char) FileSignatureInfo(BSTR, long, MsiSignatureInfo)
# path = r"msi.dll" # DispProperty

# fails packing IDLDESC
# path = r"C:\Dokumente und Einstellungen\thomas\Desktop\tlb\win.tlb"
# fails packing WIN32_FIND_DATA
# path = r"C:\Dokumente und Einstellungen\thomas\Desktop\tlb\win32.tlb"
# has a POINTER(IUnknown) as default parameter value
# path = r"c:\Programme\Gemeinsame Dateien\Microsoft Shared\Speech\sapi.dll"


# path = r"hnetcfg.dll"
# path = r"simpdata.tlb"
# path = r"nscompat.tlb"
# path = r"stdole32.tlb"

# path = r"shdocvw.dll"

# path = r"c:\Programme\Microsoft Office\Office\MSO97.DLL"
# path = r"PICCLP32.OCX" # DispProperty
# path = r"MSHFLXGD.OCX" # DispProperty, propputref
# path = r"scrrun.dll" # propput AND propputref on IDictionary::Item
# path = r"C:\Dokumente und Einstellungen\thomas\Desktop\tlb\threadapi.tlb"

# path = r"..\samples\BITS\bits2_0.tlb"

# path = r"c:\vc98\include\activscp.tlb"


def get_tlib_filename(tlib: typeinfo.ITypeLib) -> Optional[str]:
    # seems if the typelib is not registered, there's no way to
    # determine the filename.
    la = tlib.GetLibAttr()
    name = BSTR()
    if 0 == windll.oleaut32.QueryPathOfRegTypeLib(
        byref(la.guid), la.wMajorVerNum, la.wMinorVerNum, 0, byref(name)
    ):
        full_filename = name.value.split("\0")[0]
        if not os.path.isabs(full_filename):
            # workaround Windows 7 bug in QueryPathOfRegTypeLib returning relative path
            try:
                dll = windll.LoadLibrary(full_filename)
                full_filename = _get_module_filename(dll._handle)
                del dll
            except OSError:
                return None
        return full_filename
    return None


def _py2exe_hint():
    # If the tlbparser is frozen, we need to include these
    import comtypes.persist
    import comtypes.typeinfo
    import comtypes.automation


# -eof-
