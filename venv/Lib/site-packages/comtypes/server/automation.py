import logging

from ctypes import *
from comtypes.hresult import *

from comtypes import COMObject, IUnknown
from comtypes.automation import IDispatch, IEnumVARIANT

logger = logging.getLogger(__name__)

# XXX When the COMCollection class is ready, insert it into __all__
__all__ = ["VARIANTEnumerator"]


class VARIANTEnumerator(COMObject):
    """A universal VARIANTEnumerator class.  Instantiate it with a
    collection of items that support the IDispatch interface."""

    _com_interfaces_ = [IEnumVARIANT]

    def __init__(self, items):
        self.items = (
            items  # keep, so that we can restore our iterator (in Reset, and Clone).
        )
        self.seq = iter(self.items)
        super(VARIANTEnumerator, self).__init__()

    def Next(self, this, celt, rgVar, pCeltFetched):
        if not rgVar:
            return E_POINTER
        if not pCeltFetched:
            pCeltFetched = [None]
        pCeltFetched[0] = 0
        try:
            for index in range(celt):
                item = next(self.seq)
                p = item.QueryInterface(IDispatch)
                rgVar[index].value = p
                pCeltFetched[0] += 1
        except StopIteration:
            pass
        # except:
        #     # ReportException? return E_FAIL?
        #     import traceback
        #     traceback.print_exc()

        if pCeltFetched[0] == celt:
            return S_OK
        return S_FALSE

    def Skip(self, this, celt):
        # skip some elements.
        try:
            for _ in range(celt):
                next(self.seq)
        except StopIteration:
            return S_FALSE
        return S_OK

    def Reset(self, this):
        self.seq = iter(self.items)
        return S_OK

    # Clone not implemented


################################################################

# XXX Shouldn't this be a mixin class?
# And isn't this class borked anyway?


class COMCollection(COMObject):
    """Abstract base class which implements Count, Item, and _NewEnum."""

    def __init__(self, itemtype, collection):
        self.collection = collection
        self.itemtype = itemtype
        super(COMCollection, self).__init__()

    def _get_Item(self, this, pathname, pitem):
        if not pitem:
            return E_POINTER
        item = self.itemtype(pathname)
        return item.IUnknown_QueryInterface(None, pointer(pitem[0]._iid_), pitem)

    def _get_Count(self, this, pcount):
        if not pcount:
            return E_POINTER
        pcount[0] = len(self.collection)
        return S_OK

    def _get__NewEnum(self, this, penum):
        if not penum:
            return E_POINTER
        enum = VARIANTEnumerator(self.itemtype, self.collection)
        return enum.IUnknown_QueryInterface(None, pointer(IUnknown._iid_), penum)
