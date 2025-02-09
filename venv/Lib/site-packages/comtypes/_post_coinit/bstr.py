from ctypes import _SimpleCData, windll
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from comtypes import hints  # type: ignore


class BSTR(_SimpleCData):
    """The windows BSTR data type"""

    _type_ = "X"
    _needsfree = False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.value!r})"

    def __ctypes_from_outparam__(self) -> Any:
        self._needsfree = True
        return self.value

    def __del__(
        self, _free: Callable[["BSTR"], Any] = windll.oleaut32.SysFreeString
    ) -> None:
        # Free the string if self owns the memory
        # or if instructed by __ctypes_from_outparam__.
        if self._b_base_ is None or self._needsfree:
            _free(self)

    @classmethod
    def from_param(cls, value: Any) -> "hints.Self":
        """Convert into a foreign function call parameter."""
        if isinstance(value, cls):
            return value
        # Although the builtin SimpleCData.from_param call does the
        # right thing, it doesn't ensure that SysFreeString is called
        # on destruction.
        return cls(value)
