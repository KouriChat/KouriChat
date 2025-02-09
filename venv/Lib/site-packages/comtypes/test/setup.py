# all the unittests can be converted to exe-files.
from distutils.core import setup
import glob
import py2exe

setup(name="test_*", console=glob.glob("test_*.py"))
