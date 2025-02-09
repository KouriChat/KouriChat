from typing import Optional

import comtypes
from comtypes import typeinfo


def name_wrapper_module(tlib: typeinfo.ITypeLib) -> str:
    """Determine the name of a typelib wrapper module"""
    libattr = tlib.GetLibAttr()
    guid = str(libattr.guid)[1:-1].replace("-", "_")
    modname = f"_{guid}_{libattr.lcid}_{libattr.wMajorVerNum}_{libattr.wMinorVerNum}"
    return f"comtypes.gen.{modname}"


def name_friendly_module(tlib: typeinfo.ITypeLib) -> Optional[str]:
    """Determine the friendly-name of a typelib module.
    If cannot get friendly-name from typelib, returns `None`.
    """
    try:
        modulename = tlib.GetDocumentation(-1)[0]
    except comtypes.COMError:
        return
    return f"comtypes.gen.{modulename}"
