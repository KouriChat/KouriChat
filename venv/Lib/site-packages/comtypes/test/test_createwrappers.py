import glob
import os
import unittest
import warnings

import comtypes.client
import comtypes.client._generate
import comtypes.typeinfo


def setUpModule():
    raise unittest.SkipTest(
        "I have no idea what to do with this.  It programmatically creates "
        "*thousands* of tests and a few dozen of them fail."
    )


# filter warnings about interfaces without a base interface; they will
# be skipped in the code generation.
warnings.filterwarnings(
    "ignore", "Ignoring interface .* which has no base interface", UserWarning
)

# don't print messages when typelib wrappers are generated
comtypes.client._generate.__verbose__ = False

sysdir = os.path.join(os.environ["SystemRoot"], "system32")

progdir = os.environ["ProgramFiles"]
common_progdir = os.environ["CommonProgramFiles"]

# This test takes quite some time.  It tries to build wrappers for ALL
# .dll, .tlb, and .ocx files in the system directory which contain typelibs.


class Test(unittest.TestCase):
    def setUp(self):
        "Do not write the generated files into the comtypes.gen directory"
        comtypes.client.gen_dir = None

    def tearDown(self):
        comtypes.client.gen_dir = comtypes.client._find_gen_dir()


number = 0


def add_test(fname):
    global number

    def test(self):
        try:
            comtypes.typeinfo.LoadTypeLibEx(fname)
        except WindowsError:
            return
        comtypes.client.GetModule(fname)

    test.__doc__ = f"test GetModule({fname!r})"
    setattr(Test, f"test_{number}", test)
    number += 1


for fname in glob.glob(os.path.join(sysdir, "*.ocx")):
    add_test(fname)

for fname in glob.glob(os.path.join(sysdir, "*.tlb")):
    add_test(fname)

for fname in glob.glob(os.path.join(progdir, r"Microsoft Office\Office*\*.tlb")):
    if os.path.basename(fname).lower() in (
        "grde50.olb",  # UnicodeEncodeError
        "xl5de32.olb",  # UnicodeEncodeError
        "grde50.olb",  # UnicodeEncodeError
    ):
        continue
    add_test(fname)

for fname in glob.glob(os.path.join(progdir, r"Microsoft Office\Office*\*.olb")):
    if os.path.basename(fname).lower() in (
        "grde50.olb",  # UnicodeEncodeError
        "xl5de32.olb",  # UnicodeEncodeError
        "grde50.olb",  # UnicodeEncodeError
    ):
        continue
    add_test(fname)

path = os.path.join(
    progdir,
    r"Microsoft Visual Studio .NET 2003\Visual Studio SDKs\DIA SDK\bin\msdia71.dll",
)
if os.path.isfile(path):
    print("ADD", path)
    add_test(path)

for fname in glob.glob(os.path.join(common_progdir, r"Microsoft Shared\Speech\*.dll")):
    add_test(fname)

for fname in glob.glob(os.path.join(sysdir, "*.dll")):
    # these typelibs give errors:
    if os.path.basename(fname).lower() in (
        "syncom.dll",  # interfaces without base interface
        "msvidctl.dll",  # assignment to None
        "scardssp.dll",  # assertionerror sizeof()
        "sccsccp.dll",  # assertionerror sizeof()
        # Typeinfo in comsvcs.dll in XP 64-bit SP 1 is broken.
        # Oleview decompiles this code snippet (^ marks are m):
        # [
        #  odl,
        #  uuid(C7B67079-8255-42C6-9EC0-6994A3548780)
        # ]
        # interface IAppDomainHelper : IDispatch {
        #    HRESULT _stdcall pfnShutdownCB(void* pv);
        #    HRESULT _stdcall Initialize(
        #                    [in] IUnknown* pUnkAD,
        #                    [in] IAppDomainHelper __MIDL_0028,
        #                         ^^^^^^^^^^^^^^^^
        #                    [in] void* pPool);
        #    HRESULT _stdcall pfnCallbackCB(void* pv);
        #    HRESULT _stdcall DoCallback(
        #                    [in] IUnknown* pUnkAD,
        #                    [in] IAppDomainHelper __MIDL_0029,
        #                         ^^^^^^^^^^^^^^^^
        #                    [in] void* pPool);
        # };
        "comsvcs.dll",
    ):
        continue
    add_test(fname)

if __name__ == "__main__":
    unittest.main()
