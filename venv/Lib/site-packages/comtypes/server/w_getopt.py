from typing import Sequence, Tuple


class GetoptError(Exception):
    pass


def w_getopt(
    args: Sequence[str], options: str
) -> Tuple[Sequence[Tuple[str, str]], Sequence[str]]:
    """A getopt for Windows.

    Options may start with either '-' or '/', the option names may
    have more than one letter (/tlb or -RegServer), and option names
    are case insensitive.

    Returns two elements, just as getopt.getopt.  The first is a list
    of (option, value) pairs in the same way getopt.getopt does, but
    there is no '-' or '/' prefix to the option name, and the option
    name is always lower case.  The second is the list of arguments
    which do not belong to an option.

    Different from getopt.getopt, a single argument not belonging to an option
    does not terminate parsing.
    """
    opts = []
    arguments = []
    while args:
        if args[0][:1] in "/-":
            arg = args[0][1:]  # strip the '-' or '/'
            arg = arg.lower()

            if arg + ":" in options:
                try:
                    opts.append((arg, args[1]))
                except IndexError:
                    raise GetoptError(f"option '{args[0]}' requires an argument")
                args = args[1:]
            elif arg in options:
                opts.append((arg, ""))
            else:
                raise GetoptError(f"invalid option '{args[0]}'")
            args = args[1:]
        else:
            arguments.append(args[0])
            args = args[1:]

    return opts, arguments
