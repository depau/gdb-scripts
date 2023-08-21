import re
import warnings

import gdb

from _commons_lib.utils import (
    ExtendedCommand,
    register_command,
    convenience_function,
    ValueOrNative,
)
from docopt import ParsedOptions

_unique_ptr_regex = re.compile(r"[{]\s*get\(\)\s*=\s*(0x[0-9a-fA-F]+)[^0-9a-fA-F]")
_char_array_regex = re.compile(r"char \[(\d+)]")


@convenience_function
def deref(val: gdb.Value, *, recursive=False, from_tty=False) -> ValueOrNative:
    dereferenced = False

    while isinstance(val, gdb.Value) and (recursive or not dereferenced):
        dereferenced = True

        stripped_type = val.type.unqualified().strip_typedefs()
        if stripped_type is None:
            break
        type_name = str(stripped_type.unqualified())

        if _char_array_regex.match(type_name):
            val = val.string()
            continue

        elif stripped_type.code == gdb.TYPE_CODE_PTR:
            if str(stripped_type.target().unqualified()) == "char":
                val = val.string()
            else:
                val = val.dereference()
            continue

        elif type_name.startswith("std::unique_ptr"):
            try:
                val = val["_M_t"]["_M_t"]["_M_head_impl"].dereference()
            except gdb.error:
                # warnings.warn(
                #     "Failed to dereference unique_ptr normally, using str() hack"
                # )
                ptr_type = stripped_type.template_argument(0).pointer()
                as_str = str(val)
                m = _unique_ptr_regex.search(as_str)
                if not m:
                    warnings.warn("Failed to dereference unique_ptr using str() hack")
                    raise
                try:
                    ptr = int(m.group(1), 16)
                except ValueError:
                    warnings.warn("Failed to dereference unique_ptr using str() hack")
                    raise
                val = gdb.Value(ptr).cast(ptr_type).dereference()
            continue

        elif type_name.startswith("std::shared_ptr"):
            val = val["_M_ptr"].dereference()
            continue

        elif type_name.startswith("std::optional"):
            payload = val["_M_payload"]
            if payload["_M_engaged"]:
                val = payload["_M_payload"]["_M_value"]
            else:
                if from_tty:
                    gdb.write("Empty optional\n")
                val = None
            continue

        elif type_name.startswith("llvm::Optional"):
            storage = val["Storage"]
            if storage["hasVal"]:
                try:
                    val = storage["val"]
                except gdb.error as e:
                    if "cannot resolve overloaded method `val'" in str(e):
                        val = storage["value"]
            else:
                if from_tty:
                    gdb.write("Empty optional\n")
                val = None

        elif (
            type_name.startswith("std::basic_string")
            or type_name.startswith("std::__cxx11::basic_string")
            or type_name.startswith("std::string")
        ):
            data = val["_M_dataplus"]["_M_p"]
            length = int(val["_M_string_length"])
            val = data.string(length=length)

        elif type_name.startswith("llvm::StringRef"):
            data = val["Data"]
            length = int(val["Length"])
            val = data.string(length=length)

        elif type_name.startswith("llvm::SmallString"):
            char_star = gdb.lookup_type("char").pointer()
            begin = val["BeginX"]
            val = begin.cast(char_star).string(length=int(val["Size"]))

        elif type_name.startswith("llvm::Error"):
            err = val["Payload"]
            if not err:
                if from_tty:
                    gdb.write("llvm::Error::success()\n")
                val = None
            else:
                if from_tty:
                    gdb.write("llvm::Error contains an error\n")
                val = err.dereference()

        elif type_name.startswith("llvm::Expected"):
            has_error = val["HasError"]
            if not has_error:
                if from_tty:
                    gdb.write("llvm::Expected contains a value\n")
                data_type = stripped_type.template_argument(0)
                val = val["TStorage"].address.cast(data_type.pointer()).dereference()
            else:
                if from_tty:
                    gdb.write("llvm::Expected contains an error\n")
                error_storage = val["ErrorStorage"]
                error_type = (
                    error_storage.type.template_argument(0)
                    .template_argument(0)
                    .pointer()
                )
                val = error_storage.address.cast(error_type).dereference()

        else:
            break

    if val is None:
        return gdb.Value(0)

    return val


@register_command
class DerefCommand(ExtendedCommand):
    """
    Dereference an expression containing a pointer or a C++ pointer-like object and store the result in a convenience
    variable

    Usage: deref [-r] <expression> [<convenience_variable>]

    Options:
        -r --recursive  Dereference recursively until a non-pointer type is reached
    """

    name = "deref"
    completer_class = gdb.COMPLETE_EXPRESSION

    def invoke_with_options(self, opts: ParsedOptions, from_tty: bool):
        var = opts["<convenience_variable>"]
        expr = opts["<expression>"]
        recursive = opts["--recursive"]

        try:
            val = gdb.parse_and_eval(expr)
        except gdb.error as e:
            print(e)
            return

        d = deref(val, recursive=recursive, from_tty=from_tty)
        self.return_value(d, var_name=var, from_tty=from_tty)
