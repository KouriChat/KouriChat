# This test requires that the Agilent IVI-COM Driver for Agilent546XX
# is installed.  It is not requires to have a physical instrument
# connected, the driver is used in simulation mode.

import unittest
from comtypes.test import ResourceDenied
from comtypes.client import CreateObject
from comtypes import GUID
from comtypes.safearray import _midlSAFEARRAY
from ctypes import c_double, POINTER

try:
    GUID.from_progid("Agilent546XX.Agilent546XX")
except WindowsError:
    pass

else:

    class Test(unittest.TestCase):
        def test(self):
            # The point of this test is the ReadWaveform method below,
            # which takes several [in, out] arguments.
            agDrvr = CreateObject("Agilent546XX.Agilent546XX")

            # XXX XXX XXX The following call crashes hard with an accessviolation when
            # the OANOCACHE environ variable is set.
            import os

            if "OANOCACHE" in os.environ:
                print("Cannot test. buggy COM object?")
                return

            # Initialize the driver in simulation mode.  Resource descriptor is ignored.
            agDrvr.Initialize("", False, False, "Simulate=true")
            # Initialize driver.  Edit resource descriptor for your system.
            # agDrvr.Initialize("GPIB0::7::INSTR", False, False, "QueryInstrStatus=true")

            from comtypes.gen import IviScopeLib

            iviDrvr = agDrvr.QueryInterface(IviScopeLib.IIviScope)

            # Get driver Identity properties.  Driver initialization not required.
            # print "Identifier:", iviDrvr.Identity.Identifier
            # print "   Revision:",  agDrvr.Identity.Revision
            # print "Description:", agDrvr.Identity.Description

            # Get instrument Identity properties.
            # print "InstrumentModel: ", agDrvr.Identity.InstrumentModel
            # print "   FirmwareRevision: ", agDrvr.Identity.InstrumentFirmwareRevision
            # print "   SerialNumber: ", agDrvr.System.SerialNumber

            # Setup for a measurement.  Reset in this case.
            agDrvr.Utility.Reset()

            pMeasurement = agDrvr.Measurements.Item("UserChannel1")
            # ReadWaveform() takes a sweep and reads the data.
            #
            # Definition generated for ReadWaveform():
            # COMMETHOD([helpstring(u'Acquires and returns a waveform on the configured channels.')],
            #          HRESULT, 'ReadWaveform',
            #          ( ['in'], Agilent546XXTimeOutEnum, 'MaxTime' ),
            #          ( ['in', 'out'], POINTER(_midlSAFEARRAY(c_double)), 'pWaveformArray' ),
            #          ( ['in', 'out'], POINTER(c_double), 'pInitialX' ),
            #          ( ['in', 'out'], POINTER(c_double), 'pXIncrement' )),

            # [in, out] arguments are now optional (comtypes
            # constructs an empty default value when nothing is
            # passed).
            psaWaveform = _midlSAFEARRAY(c_double).create([])
            self._check_result(pMeasurement.ReadWaveform(20000))
            self._check_result(pMeasurement.ReadWaveform(20000, pInitialX=9.0))
            self._check_result(
                pMeasurement.ReadWaveform(20000, pXIncrement=9.0, pInitialX=3.0)
            )
            self._check_result(pMeasurement.ReadWaveform(20000))
            self._check_result(pMeasurement.ReadWaveform(20000, []))
            self._check_result(pMeasurement.ReadWaveform(20000, pWaveformArray=[]))
            self._check_result(pMeasurement.ReadWaveform(20000, psaWaveform))
            self._check_result(pMeasurement.ReadWaveform(20000, pXIncrement=9.0))

        def _check_result(self, xxx_todo_changeme):
            # ReadWaveform, in simulation mode, returns three values:
            #
            # - a safearray containing 100 random double values,
            #   unpacked and returned as tuple
            # - the initial_x value: 0.0
            # - the x_increment value: 0.0
            (array, initial_x, x_increment) = xxx_todo_changeme
            self.assertEqual(len(array), 100)
            self.assertFalse([x for x in array if not isinstance(x, float)])
            self.assertEqual(initial_x, 0.0)
            self.assertEqual(x_increment, 0.0)


if __name__ == "__main__":
    unittest.main()
