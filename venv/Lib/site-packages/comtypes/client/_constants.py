################################################################
#
# Typelib constants
#
################################################################
import keyword
import sys

import comtypes
import comtypes.automation
import comtypes.typeinfo


class _frozen_attr_dict(dict):
    __slots__ = ()

    def __getattr__(self, name):
        if name not in self:
            raise AttributeError
        return self[name]

    def __setitem__(self, key, value):
        raise TypeError

    def __delitem__(self, name):
        raise TypeError

    def __ior__(self, other):
        # `dict |= other` is New in version 3.9,
        # but this class does not support it.
        raise TypeError

    def clear(self):
        raise TypeError

    def pop(self, key, default=None):
        raise TypeError

    def popitem(self, last=True):
        raise TypeError

    def setdefault(self, key, default=None):
        raise TypeError


class Constants(object):
    """This class loads the type library from the supplied object,
    then exposes constants and enumerations in the type library
    as attributes.

    Examples:
        >>> c = Constants('scrrun.dll')  # load `Scripting` consts, enums, and alias
        >>> c.IOMode.ForReading  # returns enumeration member value
        1
        >>> c.ForReading  # returns constant value
        1
        >>> c.FileAttribute.Normal
        0
        >>> c.Normal
        0
        >>> 'ForReading' in c.consts  # as is `key in dict`
        True
        >>> 'IOMode' in c.enums  # as is `key in dict`
        True
        >>> 'ForReading' in c.IOMode  # as is `key in dict`
        True
        >>> 'FileAttribute' in c.enums  # It's alias of `__MIDL___MIDL...`
        False
        >>> 'FileAttribute' in c.alias  # as is `key in dict`
        True
    """

    __slots__ = ("alias", "consts", "enums", "tcomp")

    def __init__(self, obj):
        if isinstance(obj, str):
            tlib = comtypes.typeinfo.LoadTypeLibEx(obj)
        else:
            obj = obj.QueryInterface(comtypes.automation.IDispatch)
            tlib, index = obj.GetTypeInfo(0).GetContainingTypeLib()
        consts, enums, alias = self._get_bound_namespaces(tlib)
        self.consts = _frozen_attr_dict(consts)
        self.enums = _frozen_attr_dict(enums)
        self.alias = _frozen_attr_dict(alias)
        self.tcomp = tlib.GetTypeComp()

    def _get_bound_namespaces(self, tlib):
        consts, enums, alias = {}, {}, {}
        for i in range(tlib.GetTypeInfoCount()):
            tinfo = tlib.GetTypeInfo(i)
            ta = tinfo.GetTypeAttr()
            if ta.typekind == comtypes.typeinfo.TKIND_ALIAS:
                alias.update(self._get_ref_names(tinfo, ta))
            members = self._get_members(tinfo, ta)
            if ta.typekind == comtypes.typeinfo.TKIND_ENUM:
                enums[tinfo.GetDocumentation(-1)[0]] = members
            consts.update(members)
        return consts, enums, alias

    def _get_ref_names(self, tinfo, ta):
        try:
            refinfo = tinfo.GetRefTypeInfo(ta.tdescAlias._.hreftype)
        except comtypes.COMError:
            return {}
        if refinfo.GetTypeAttr().typekind != comtypes.typeinfo.TKIND_ENUM:
            return {}
        friendly_name = tinfo.GetDocumentation(-1)[0]
        real_name = refinfo.GetDocumentation(-1)[0]
        return {friendly_name: real_name}

    def _get_members(self, tinfo, ta):
        members = {}
        for i in range(ta.cVars):
            vdesc = tinfo.GetVarDesc(i)
            if vdesc.varkind == comtypes.typeinfo.VAR_CONST:
                name = tinfo.GetDocumentation(vdesc.memid)[0]
                if keyword.iskeyword(name):  # same as `tools.codegenerator`
                    # XXX is necessary warning? should use logging?
                    # import comtypes.tools
                    # if comtypes.tools.__warn_on_munge__:
                    #     print(f"# Fixing keyword as VAR_CONST for {name}")
                    name += "_"
                members[name] = vdesc._.lpvarValue[0].value
        return _frozen_attr_dict(members)

    def __getattr__(self, name):
        name = self.alias.get(name, name)
        if name in self.enums:
            return self.enums[name]
        elif name in self.consts:
            return self.consts[name]
        else:
            raise AttributeError(name)

    def _bind_type(self, name):
        return self.tcomp.BindType(name)
