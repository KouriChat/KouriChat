import sys, os
import logging

logging.basicConfig()
##logging.basicConfig(level=logging.DEBUG)
##logger = logging.getLogger(__name__)

# Add comtypes to sys.path (if this is run from a SVN checkout)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), r"..\..")))

import comtypes
from comtypes.hresult import S_OK
import comtypes.server.connectionpoints

################################################################

# Create the wrapper in the comtypes.gen package, it will be named
# TestComServerLib; the name is derived from the 'library ' statement
# in the IDL file
if not hasattr(sys, "frozen"):
    import comtypes.client

    # pathname of the type library file
    tlbfile = os.path.join(os.path.dirname(__file__), "TestDispServer.tlb")
    # if running as frozen app (dll or exe), the wrapper should be in
    # the library archive, so we don't need to generate it.
    comtypes.client.GetModule(tlbfile)

# Import the wrapper
from comtypes.gen import TestDispServerLib

################################################################


# Implement the CoClass by defining a subclass of the
# TestDispServerLib.TestDispServer class in the wrapper file.  The
# COMObject base class provides default implementations of the
# IUnknown, IDispatch, IPersist, IProvideClassInfo,
# IProvideClassInfo2, and ISupportErrorInfo interfaces.
#
# The ConnectableObjectMixin class provides connectionpoints (events).
class TestDispServer(
    TestDispServerLib.TestDispServer,  # the coclass from the typelib wrapper
    comtypes.server.connectionpoints.ConnectableObjectMixin,
):
    # The default interface from the typelib MUST be the first
    # interface, other interfaces can follow

    _com_interfaces_ = TestDispServerLib.TestDispServer._com_interfaces_ + [
        comtypes.connectionpoints.IConnectionPointContainer
    ]

    # registry entries
    _reg_threading_ = "Both"
    _reg_progid_ = "TestDispServerLib.TestDispServer.1"
    _reg_novers_progid_ = "TestDispServerLib.TestDispServer"
    _reg_desc_ = "comtypes COM server sample for testing"
    _reg_clsctx_ = comtypes.CLSCTX_INPROC_SERVER | comtypes.CLSCTX_LOCAL_SERVER

    ################################
    # DTestDispServer methods

    def DTestDispServer_eval(self, this, expr, presult):
        self.Fire_Event(0, "EvalStarted", expr)
        # The following two are equivalent, but the former is more generic:
        presult[0] = eval(expr)
        ##presult[0].value = eval(expr)
        self.Fire_Event(0, "EvalCompleted", expr, presult[0].value)
        return S_OK

    def DTestDispServer_eval2(self, expr):
        self.Fire_Event(0, "EvalStarted", expr)
        result = eval(expr)
        self.Fire_Event(0, "EvalCompleted", expr, result)
        return result

    def DTestDispServer__get_id(self, this, pid):
        pid[0] = id(self)
        return S_OK

    def DTestDispServer_Exec(self, this, what):
        exec(what)
        return S_OK

    def DTestDispServer_Exec2(self, what):
        exec(what)

    _name = "spam, spam, spam"

    # Implementation of the DTestDispServer::Name propget
    def DTestDispServer__get_name(self, this, pname):
        pname[0] = self._name
        return S_OK

    # Implementation of the DTestDispServer::Name propput
    def DTestDispServer__set_name(self, this, name):
        self._name = name
        return S_OK

    # Implementation of the DTestDispServer::SetName method
    def DTestDispServer_sEtNaMe(self, name):
        self._name = name


if __name__ == "__main__":
    from comtypes.server.register import UseCommandLine

    UseCommandLine(TestDispServer)
