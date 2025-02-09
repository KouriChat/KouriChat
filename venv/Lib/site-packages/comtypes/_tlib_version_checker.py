import os
import sys


def _check_version(actual, tlib_cached_mtime=None):
    from comtypes.tools.codegenerator import version as required

    if actual != required:
        raise ImportError("Wrong version")
    if not hasattr(sys, "frozen"):
        g = sys._getframe(1).f_globals
        tlb_path = g.get("typelib_path")
        try:
            tlib_curr_mtime = os.stat(tlb_path).st_mtime
        except (OSError, TypeError):
            return
        if not tlib_cached_mtime or abs(tlib_curr_mtime - tlib_cached_mtime) >= 1:
            raise ImportError("Typelib different than module")
