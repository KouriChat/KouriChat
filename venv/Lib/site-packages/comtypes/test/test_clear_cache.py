"""
Test for the ``comtypes.clear_cache`` module.
"""

import contextlib
import runpy
from unittest.mock import patch, call
from unittest import TestCase

from comtypes.client import _find_gen_dir


class ClearCacheTestCase(TestCase):
    # we patch sys.stdout so unittest doesn't show the print statements

    @patch("sys.argv", ["clear_cache.py", "-y"])
    @patch("shutil.rmtree")
    def test_clear_cache(self, mock_rmtree):
        with contextlib.redirect_stdout(None):
            runpy.run_module("comtypes.clear_cache", {}, "__main__")

        # because we don't actually delete anything, _find_gen_dir() will
        # give the same answer every time we call it
        self.assertEqual(
            mock_rmtree.call_args_list, [call(_find_gen_dir()) for _ in range(2)]
        )
