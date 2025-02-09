import argparse
import contextlib
import os
import sys
from shutil import rmtree  # TESTS ASSUME USE OF RMTREE


# if supporting Py>=3.11 only, this might be `contextlib.chdir`.
# https://docs.python.org/3/library/contextlib.html#contextlib.chdir
@contextlib.contextmanager
def chdir(path):
    """Context manager to change the current working directory."""
    work_dir = os.getcwd()
    os.chdir(path)
    yield
    os.chdir(work_dir)


def main():
    parser = argparse.ArgumentParser(
        prog="py -m comtypes.clear_cache", description="Removes comtypes cache folders."
    )
    parser.add_argument(
        "-y", help="Pre-approve deleting all folders", action="store_true"
    )
    args = parser.parse_args()

    if not args.y:
        confirm = input("Remove comtypes cache directories? (y/n): ")
        if confirm.lower() != "y":
            print("Cache directories NOT removed")
            return

    # change cwd to avoid import from local folder during installation process
    with chdir(os.path.dirname(sys.executable)):
        try:
            import comtypes.client
        except ImportError:
            print("Could not import comtypes", file=sys.stderr)
            sys.exit(1)

    # there are two possible locations for the cache folder (in the comtypes
    # folder in site-packages if that is writable, otherwise in APPDATA)
    # fortunately, by deleting the first location returned by _find_gen_dir()
    # we make it un-writable, so calling it again gives us the APPDATA location
    for _ in range(2):
        dir_path = comtypes.client._find_gen_dir()
        rmtree(dir_path)
        print(f'Removed directory "{dir_path}"')


if __name__ == "__main__":
    main()
