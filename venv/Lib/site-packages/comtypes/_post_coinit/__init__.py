"""comtypes._post_coinit

This subpackage contains symbols that should be imported into `comtypes/__init__.py`
after `CoInitializeEx` is defined and called, and symbols that can be defined in
any order during the initialization of the `comtypes` package.

These were previously defined in `comtypes/__init__.py`, but due to the codebase
of the file becoming bloated, reducing the ease of changes and increasing
cognitive load, they have been moved here.

This subpackage is called simultaneously with the initialization of `comtypes`.
So it is necessary to maintain minimal settings to keep the lightweight action
when the package is initialized.
"""

from comtypes._post_coinit.unknwn import _shutdown  # noqa
