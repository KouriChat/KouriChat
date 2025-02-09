# comtypes.test package.

import ctypes
import getopt
import os
import sys
import time
import unittest

use_resources = ["*"]


def register_server(source_dir):
    """Register testing server appropriate for the python architecture.

    ``source_dir`` gives the absolute path to the comtype source in which the
    32- and 64-bit testing server, "AvmcIfc.dll" is defined.

    If the server is already registered, do nothing.

    """
    # The 64-bitness of the python interpreter determines the testing dll to
    # use.
    dll_name = "AvmcIfc_x64.dll" if sys.maxsize > 2**32 else "AvmcIfc.dll"
    dll_path = os.path.join(source_dir, "Debug", dll_name)
    # Register our ATL COM tester dll
    dll = ctypes.OleDLL(dll_path)
    dll.DllRegisterServer()
    return


class ResourceDenied(Exception):
    """Test skipped because it requested a disallowed resource.

    This is raised when a test calls requires() for a resource that
    has not be enabled.  Resources are defined by test modules.
    """


def is_resource_enabled(resource):
    """Test whether a resource is enabled.

    If the caller's module is __main__ then automatically return True."""
    if sys._getframe().f_back.f_globals.get("__name__") == "__main__":
        return True
    result = use_resources is not None and (
        resource in use_resources or "*" in use_resources
    )
    if not result:
        _unavail[resource] = None
    return result


_unavail = {}


def requires(resource, msg=None):
    """Raise ResourceDenied if the specified resource is not available.

    If the caller's module is __main__ then automatically return True."""
    # see if the caller's module is __main__ - if so, treat as if
    # the resource was set
    if sys._getframe().f_back.f_globals.get("__name__") == "__main__":
        return
    if not is_resource_enabled(resource):
        if msg is None:
            msg = f"Use of the `{resource}` resource not enabled"
        raise ResourceDenied(msg)


def find_package_modules(package, mask):
    import fnmatch

    if hasattr(package, "__loader__"):
        path = package.__name__.replace(".", os.path.sep)
        mask = os.path.join(path, mask)
        for fnm in package.__loader__._files.keys():
            if fnmatch.fnmatchcase(fnm, mask):
                yield os.path.splitext(fnm)[0].replace(os.path.sep, ".")
    else:
        path = package.__path__[0]
        for fnm in os.listdir(path):
            if fnmatch.fnmatchcase(fnm, mask):
                yield "%s.%s" % (package.__name__, os.path.splitext(fnm)[0])


def get_tests(package, mask, verbosity):
    """Return a list of skipped test modules, and a list of test cases."""
    tests = []
    skipped = []
    for modname in find_package_modules(package, mask):
        try:
            mod = __import__(modname, globals(), locals(), ["*"])
        except ResourceDenied as detail:
            skipped.append(modname)
            if verbosity > 1:
                print(f"Skipped {modname}: {detail}", file=sys.stderr)
            continue
        except Exception as detail:
            print(f"Warning: could not import {modname}: {detail}", file=sys.stderr)
            continue
        for name in dir(mod):
            if name.startswith("_"):
                continue
            o = getattr(mod, name)
            try:
                is_test = issubclass(o, unittest.TestCase)
            except TypeError:
                continue
            if is_test:
                tests.append(o)
    return skipped, tests


def usage():
    print(__doc__)
    return 1


def test_with_refcounts(runner, verbosity, testcase):
    """Run testcase several times, tracking reference counts."""
    import gc
    import ctypes

    ptc = ctypes._pointer_type_cache.copy()
    cfc = ctypes._c_functype_cache.copy()
    wfc = ctypes._win_functype_cache.copy()

    # when searching for refcount leaks, we have to manually reset any
    # caches that ctypes has.
    def cleanup():
        ctypes._pointer_type_cache = ptc.copy()
        ctypes._c_functype_cache = cfc.copy()
        ctypes._win_functype_cache = wfc.copy()
        gc.collect()

    test = unittest.makeSuite(testcase)
    for i in range(5):
        rc = sys.gettotalrefcount()
        runner.run(test)
        cleanup()
    COUNT = 5
    refcounts = [None] * COUNT
    for i in range(COUNT):
        rc = sys.gettotalrefcount()
        runner.run(test)
        cleanup()
        refcounts[i] = sys.gettotalrefcount() - rc
    if [_f for _f in refcounts if _f]:
        print(f"{testcase} leaks:\n\t", refcounts)
    elif verbosity:
        print(f"{testcase}: ok.")


class TestRunner(unittest.TextTestRunner):
    def run(self, test, skipped):
        "Run the given test case or test suite."
        # Same as unittest.TextTestRunner.run, except that it reports
        # skipped tests.
        result = self._makeResult()
        startTime = time.time()
        test(result)
        stopTime = time.time()
        timeTaken = stopTime - startTime
        result.printErrors()
        self.stream.writeln(result.separator2)
        run = result.testsRun
        if _unavail:  # skipped:
            requested = list(_unavail.keys())
            requested.sort()
            self.stream.writeln(
                "Ran %d test%s in %.3fs (%s module%s skipped)"
                % (
                    run,
                    run != 1 and "s" or "",
                    timeTaken,
                    len(skipped),
                    len(skipped) != 1 and "s" or "",
                )
            )
            self.stream.writeln(f"Unavailable resources: {', '.join(requested)}")
        else:
            self.stream.writeln(
                f"Ran {run} test{'s' if run != 1 else ''} in {timeTaken:.3f}s"
            )
        self.stream.writeln()
        if not result.wasSuccessful():
            self.stream.write("FAILED (")
            failed, errored = list(map(len, (result.failures, result.errors)))
            if failed:
                self.stream.write(f"failures={failed}")
            if errored:
                if failed:
                    self.stream.write(", ")
                self.stream.write(f"errors={errored}")
            self.stream.writeln(")")
        else:
            self.stream.writeln("OK")
        return result


def run_tests(package, mask, verbosity, search_leaks):
    """Run tests for package and return True on failure, False otherwise"""
    skipped, testcases = get_tests(package, mask, verbosity)
    runner = TestRunner(verbosity=verbosity)

    suites = [unittest.makeSuite(o) for o in testcases]
    suite = unittest.TestSuite(suites)
    result = runner.run(suite, skipped)

    if search_leaks:
        # hunt for refcount leaks
        runner = BasicTestRunner()
        for t in testcases:
            test_with_refcounts(runner, verbosity, t)

    return bool(result.errors) or bool(result.failures)


class BasicTestRunner:
    def run(self, test):
        result = unittest.TestResult()
        test(result)
        return result


def run(args=[]):
    """Run tests and return True on failure, False otherwise"""
    try:
        opts, args = getopt.getopt(args, "rqvu:")
    except getopt.error:
        return usage()

    verbosity = 1
    search_leaks = False
    for flag, value in opts:
        if flag == "-q":
            verbosity -= 1
        elif flag == "-v":
            verbosity += 1
        elif flag == "-r":
            try:
                sys.gettotalrefcount
            except AttributeError:
                print("-r flag requires Python debug build", file=sys.stderr)
                return -1
            search_leaks = True
        elif flag == "-u":
            use_resources.extend(value.split(","))

    mask = "test_*.py*"
    if args:
        mask = args[0]

    import comtypes.test

    return run_tests(comtypes.test, mask, verbosity, search_leaks)
