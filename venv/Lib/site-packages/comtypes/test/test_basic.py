##import ut
import unittest as ut
from ctypes import windll, POINTER, byref, HRESULT
from comtypes import IUnknown, STDMETHOD, GUID

# XXX leaks references!


def method_count(interface):
    return sum([len(base.__dict__.get("_methods_", ())) for base in interface.__mro__])


class BasicTest(ut.TestCase):
    def test_IUnknown(self):
        from comtypes import IUnknown

        self.assertEqual(method_count(IUnknown), 3)

    def test_release(self):
        POINTER(IUnknown)()

    def test_refcounts(self):
        p = POINTER(IUnknown)()
        windll.oleaut32.CreateTypeLib2(1, "blabla", byref(p))
        # initial refcount is 2
        for i in range(2, 10):
            self.assertEqual(p.AddRef(), i)
        for i in range(8, 0, -1):
            self.assertEqual(p.Release(), i)

    def test_qi(self):
        p = POINTER(IUnknown)()
        windll.oleaut32.CreateTypeLib2(1, "blabla", byref(p))
        self.assertEqual(p.AddRef(), 2)
        self.assertEqual(p.Release(), 1)

        other = p.QueryInterface(IUnknown)
        self.assertEqual(other.AddRef(), 3)
        self.assertEqual(p.AddRef(), 4)
        self.assertEqual(p.Release(), 3)
        self.assertEqual(other.Release(), 2)

        del p  # calls p.Release()

        self.assertEqual(other.AddRef(), 2)
        self.assertEqual(other.Release(), 1)

    def test_derived(self):
        # XXX leaks 50 refs
        self.assertEqual(method_count(IUnknown), 3)

        class IMyInterface(IUnknown):
            pass

        self.assertEqual(method_count(IMyInterface), 3)

        # assigning _methods_ does not work until we have an _iid_!
        self.assertRaises(AttributeError, setattr, IMyInterface, "_methods_", [])
        IMyInterface._iid_ = GUID.create_new()
        IMyInterface._methods_ = []
        self.assertEqual(method_count(IMyInterface), 3)

        IMyInterface._methods_ = [STDMETHOD(HRESULT, "Blah", [])]
        self.assertEqual(method_count(IMyInterface), 4)

    def test_heirarchy(self):
        class IMyInterface(IUnknown):
            pass

        self.assertTrue(issubclass(IMyInterface, IUnknown))
        self.assertTrue(issubclass(POINTER(IMyInterface), POINTER(IUnknown)))

    def test_mro(self):
        mro = POINTER(IUnknown).__mro__

        self.assertEqual(mro[0], POINTER(IUnknown))
        self.assertEqual(mro[1], IUnknown)

        # the IUnknown class has the actual methods:
        self.assertTrue(IUnknown.__dict__.get("QueryInterface"))
        # but we can call it on the pointer instance
        POINTER(IUnknown).QueryInterface

    def test_make_methods(self):
        # XXX leaks 53 refs
        class IBase(IUnknown):
            _iid_ = GUID.create_new()

        class IDerived(IBase):
            _iid_ = GUID.create_new()

        # We cannot assign _methods_ to IDerived before IBase has it's _methods_:
        self.assertRaises(TypeError, lambda: setattr(IDerived, "_methods_", []))
        # Make sure that setting _methods_ failed completely.
        self.assertRaises(KeyError, lambda: IDerived.__dict__["_methods_"])
        IBase._methods_ = []
        # Now it works:
        IDerived._methods_ = []

    def test_identity(self):
        # COM indentity rules

        # these should be identical
        a = POINTER(IUnknown)()
        b = POINTER(IUnknown)()
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))

        from comtypes.typeinfo import CreateTypeLib

        # we do not save the lib, so no file will be created.
        # these should NOT be identical
        a = CreateTypeLib("blahblah")
        b = CreateTypeLib("spam")

        self.assertNotEqual(a, b)
        self.assertNotEqual(hash(a), hash(b))

        a = a.QueryInterface(IUnknown)
        b = b.QueryInterface(IUnknown)

        self.assertNotEqual(a, b)
        self.assertNotEqual(hash(a), hash(b))

        # These must be identical
        c = a.QueryInterface(IUnknown)
        self.assertEqual(a, c)
        self.assertEqual(hash(a), hash(c))


def main():
    ut.main()


if __name__ == "__main__":
    main()
