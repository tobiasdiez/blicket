"""The one check of a function that blicket calls with one argument, shared by the definition API
and ``bk.expect``."""

import annotationlib
import inspect
from collections.abc import Callable


def one_argument_problem(function: Callable[..., object]) -> str | None:
    """The signature of ``function`` when it cannot be called with one positional argument, else
    ``None``. A function without a signature, as some builtins are, is taken as it is."""
    try:
        # A name bound only under TYPE_CHECKING stays a ForwardRef instead of raising.
        signature = inspect.signature(function, annotation_format=annotationlib.Format.FORWARDREF)
    except ValueError:
        return None
    try:
        signature.bind(None)
    except TypeError:
        return str(signature)
    return None
