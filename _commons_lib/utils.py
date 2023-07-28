import inspect
import sys
import traceback
from functools import wraps
from types import ModuleType
from typing import List, Optional, Union, TypeAlias, Callable, Sequence

import gdb

from docopt import docopt as docopt_orig, ParsedOptions

_in_stacktrace_printer = False

ValueOrNative: TypeAlias = Union[None, bool, float, str, gdb.Value]


def docopt(doc: str, argv: List[str] = None, **kwargs) -> Optional[ParsedOptions]:
    try:
        return docopt_orig(doc, argv, **kwargs)
    except SystemExit as e:
        print(e)
        return None


def register_command(command):
    """
    Registers a gdb.Command class as a command in gdb.

    :param command: The command class to register
    """
    globals()[f"_instance_of_{command.__name__}"] = command()
    return command


class UserError(gdb.GdbError):
    def __str__(self) -> str:
        return "Error: " + super().__str__()


def print_stacktrace(func):
    """
    Decorator that prints a stacktrace when an exception is raised. This is useful for debugging gdb commands, since
    gdb doesn't print stacktraces by default.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        global _in_stacktrace_printer

        if _in_stacktrace_printer:
            return func(*args, **kwargs)

        try:
            _in_stacktrace_printer = True
            return func(*args, **kwargs)
        except UserError as e:
            raise e
        except Exception as e:
            traceback.print_exc()
            raise e
        finally:
            _in_stacktrace_printer = False

    return wrapper


class PrintStacktraceMetaclass(type):
    """
    Metaclass that wraps all methods in a class with print_stacktrace. This is useful for debugging gdb commands, since
    gdb doesn't print stacktraces by default.
    """

    def __new__(cls, name, bases, dct):
        new_dct = {}
        for base in bases[::-1]:
            for attr_name, attr in base.__dict__.items():
                if attr_name in ("__new__",):
                    continue
                if callable(attr):
                    new_dct[attr_name] = print_stacktrace(attr)

        for attr_name, attr in dct.items():
            if attr_name in ("__new__",):
                continue
            if callable(attr):
                new_dct[attr_name] = print_stacktrace(attr)

        dct.update(new_dct)

        return super().__new__(cls, name, bases, dct)


def convenience_function(
    custom_name: Union[str, Callable, None] = None,
    aliases: Sequence[str] = (),
    pass_from_tty: bool = True,
):
    """
    Register a function as a gdb convenience function.
    The function must only take gdb.Value positional arguments; all other arguments must be keyword-only.
    The function must return either a gdb.Value or a native type (None, bool, float, str).
    The function may take a "from_tty" keyword-only argument, which will be set to True when run as a convenience
    function, unless disabled by the "pass_from_tty" argument.

    Usage:

        @convenience_function
        def my_func(arg1: gdb.Value, arg2: gdb.Value, *, from_tty=False) -> ValueOrNative:
            ...

        @convenience_function("custom_name", pass_from_tty=False)
        def my_func(arg1: gdb.Value, arg2: gdb.Value) -> ValueOrNative:
            ...

    :param custom_name: The name of the convenience function. If None, the name of the decorated function is used.
    :param aliases: A list of aliases for the convenience function.
    :param pass_from_tty: Whether to pass the "from_tty" argument to the decorated function.
    """

    # custom_name could be the argument passed to the decorator, or the decorated function passed by the interpreter.
    # We call it custon_name for readability in the user's code.
    if callable(custom_name):
        # noinspection PyShadowingNames
        name = custom_name.__name__
    else:
        name = custom_name

    def actual_decorator(func: Callable):
        assert func is not None

        if name is None:
            func_name = func.__name__
        else:
            func_name = name

        params = inspect.signature(func).parameters
        non_kwonly_params = {
            param
            for param in params.values()
            if param.kind != inspect.Parameter.KEYWORD_ONLY
        }
        kwonly_params = set(params.values()) - non_kwonly_params
        arity = len(non_kwonly_params)

        # Check whether the function takes a "from_tty" argument.
        has_from_tty = False
        if pass_from_tty and any(
            map(lambda param: param.name == "from_tty", kwonly_params)
        ):
            has_from_tty = True

        @wraps(func)
        def wrapper(*args, **kwargs):
            return print_stacktrace(func)(*args, **kwargs)

        class ConvenienceFunction(gdb.Function, metaclass=PrintStacktraceMetaclass):
            @wraps(func)
            def invoke(self, *args):
                if len(args) != arity:
                    raise TypeError(f"Expected {arity} arguments, got {len(args)}")
                kwargs = {}
                if has_from_tty:
                    kwargs["from_tty"] = True
                return func(*args, **kwargs)

        # noinspection PyShadowingNames
        for alias in (func_name, *aliases):
            globals()[f"_convenience_fn_instance_{alias}"] = ConvenienceFunction(alias)

        return wrapper

    if callable(custom_name):
        return actual_decorator(custom_name)

    return actual_decorator


class ExtendedCommand(gdb.Command, metaclass=PrintStacktraceMetaclass):
    """
    Simplified implementation of gdb.Command:

    - Argument parsing and validation using docopt
    - Automatic usage printing
    - Simpler syntax for specifying the command name, completer class, and command class
    """

    name: str
    completer_class: int = gdb.COMPLETE_NONE
    command_class: int = gdb.COMMAND_USER
    prefix: bool = False

    def __init__(
        self,
    ) -> None:
        super().__init__(
            self.name, self.command_class, self.completer_class, self.prefix
        )

    @property
    def docstring(self) -> str:
        doc = self.__class__.__doc__
        if doc is None:
            raise SyntaxError(
                "ExtendedCommand children must provide a docopt docstring"
            )
        return inspect.cleandoc(doc)

    def usage(self) -> None:
        print(self.docstring)

    # noinspection PyMethodMayBeStatic
    def validate_options(self, args: ParsedOptions) -> bool:
        return True

    def invoke(self, arg: str, from_tty: bool):
        argv = gdb.string_to_argv(arg)
        return self.invoke_with_argv(argv, from_tty)

    def invoke_with_argv(self, argv: List[str], from_tty: bool):
        opts = docopt(self.docstring, argv)
        if not opts:
            return
        if not self.validate_options(opts):
            self.usage()
            return

        return self.invoke_with_options(opts, from_tty)

    def invoke_with_options(self, opts: ParsedOptions, from_tty: bool):
        raise NotImplementedError

    # noinspection PyMethodMayBeStatic
    def return_value(
        self, value: gdb.Value, var_name: Optional[str], from_tty: bool = False
    ) -> None:
        """
        Return a value from a CLI command. Since GDB does not support returning values from CLI commands, this function
        allows either to store the value as a convenience variable, or to add it to the value history.

        :param value: The value to return.
        :param var_name: A name for the convenience variable. If None, the value is added to the history instead.
        :param from_tty: Whether the command was invoked from the TTY; if so, the value is printed.
        """
        if var_name:
            if var_name[0] == "$":
                var_name = var_name[1:]
            gdb.set_convenience_variable(var_name, value)
            if from_tty:
                gdb.write(f"${var_name} = {str_repr(value)}\n")
        else:
            add_to_history(value, also_print=from_tty)


@register_command
class EchoCommand(ExtendedCommand):
    name = "echo"

    def invoke_with_argv(self, argv: List[str], from_tty: bool):
        for idx, arg in enumerate(argv):
            print(f"argv[{idx}] = '{arg}'")


# Taken from libstdc++-v3/python/libstdcxx/v6/printers.py
# License: LGPL-3.0
# https://github.com/gcc-mirror/gcc/blob/34c614b7e9dcb52a23063680f3622c842a9712ec/libstdc%2B%2B-v3/python/libstdcxx/v6/printers.py#L101-L117
def find_type(orig, name):
    typ = orig.strip_typedefs()
    while True:
        search = str(typ) + "::" + name
        try:
            return gdb.lookup_type(search)
        except RuntimeError:
            pass
        field = typ.fields()[0]
        if not field.is_base_class:
            raise ValueError("Cannot find type %s::%s" % (str(orig), name))
        typ = field.type


def str_repr(value: ValueOrNative) -> str:
    """
    Return a string representation of a gdb.Value or native type.
    :param value: The value to represent.
    :return: A string representation of the value.
    """
    if value is None:
        return "void"
    elif isinstance(value, gdb.Value):
        return value.format_string(raw=False, pretty_arrays=True, pretty_structs=True)
    elif isinstance(value, bool):
        return str(value).lower()
    elif isinstance(value, str):
        return f'"{value}"'
    else:
        return str(value)


def type_repr(value: ValueOrNative) -> str:
    if isinstance(value, gdb.Value):
        return f"native {str(value.type)}"
    else:
        return f"python {type(value)}"


_HISTORY_VAR_NAME = "__pvt_commons_lib_tmp"


def add_to_history(value: gdb.Value, also_print: bool = False) -> None:
    """
    Add a value to the GDB history, so it can be accessed with $_ or ${num}. Optionally also print the value.
    :param value: The value to add to the history.
    :param also_print: Whether to also print the value.
    """
    cur_convenience = gdb.convenience_variable(_HISTORY_VAR_NAME)
    if cur_convenience is not None:
        raise RuntimeError(
            "History variable already exists - is GDB running multiple threads?"
        )
    gdb.set_convenience_variable(_HISTORY_VAR_NAME, value)
    gdb.execute(f"print ${_HISTORY_VAR_NAME}", from_tty=False, to_string=not also_print)
    gdb.set_convenience_variable(_HISTORY_VAR_NAME, None)


def p(value: gdb.Value) -> None:
    """
    Simulate the behavior of the p (print) GDB CLI command.
    :param value: The value to print.
    """
    add_to_history(value, also_print=True)


def pae(string: str) -> gdb.Value:
    return gdb.parse_and_eval(string)


class GdbCallableModule(ModuleType):
    def __init__(self):
        ModuleType.__init__(self, gdb.__name__)
        self.__dict__.update(sys.modules[gdb.__name__].__dict__)

    def __call__(self, string: str) -> gdb.Value:
        return pae(string)

    __all__ = list(set(vars().keys()) - {"__qualname__"})


sys.modules[gdb.__name__] = GdbCallableModule()
