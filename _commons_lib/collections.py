import math
import traceback
from functools import cache
from typing import Union, Generator, Tuple, cast

import gdb

from _commons_lib.utils import (
    find_type,
    ValueOrNative,
    convenience_function,
    UserError,
    ExtendedCommand,
    register_command,
)
from docopt import ParsedOptions


def get_value_from_rb_tree_node(node):
    """Returns the value held in an _Rb_tree_node<_Val>"""
    try:
        member = node.type.fields()[1].name
        if member == "_M_value_field":
            # C++03 implementation, node contains the value as a member
            return node["_M_value_field"]
        elif member == "_M_storage":
            # C++11 implementation, node stores value in __aligned_membuf
            p = node["_M_storage"]["_M_storage"].address
            p = p.cast(node.type.template_argument(0).pointer())
            return p.dereference()
    except gdb.error:
        traceback.print_exc()
        pass
    raise ValueError("Unsupported implementation for %s" % str(node.type))


@cache
def stringmap_tombstone() -> int:
    pointer_alignment = 8
    num_low_bits_available = int(math.log2(pointer_alignment))
    tombstone_int_val = (-1 << num_low_bits_available) & ((1 << 64) - 1)
    return tombstone_int_val


def stringmap_iterate(val: gdb.Value) -> Generator[Tuple[str, gdb.Value], None, None]:
    it = val["TheTable"]
    end = it + val["NumBuckets"]
    value_ty = val.type.template_argument(0)
    entry_base_ty = gdb.lookup_type("llvm::StringMapEntryBase")
    tombstone = stringmap_tombstone()

    while it != end:
        it_deref = it.dereference()
        if it_deref == 0 or it_deref == tombstone:
            it = it + 1
            continue

        entry_ptr = it_deref.cast(entry_base_ty.pointer())
        entry = entry_ptr.dereference()

        str_len = int(entry["keyLength"])
        value_ptr = (entry_ptr + 1).cast(value_ty.pointer())
        str_data = (entry_ptr + 1).cast(gdb.lookup_type("uintptr_t")) + max(
            value_ty.sizeof, entry_base_ty.alignof
        )
        str_data = str_data.cast(gdb.lookup_type("char").const().pointer())
        value = value_ptr.dereference()
        yield str_data.string(length=str_len), value

        it = it + 1


def rbtree_iterate(rbtree: gdb.Value) -> Generator[gdb.Value, None, None]:
    size = rbtree["_M_t"]["_M_impl"]["_M_node_count"]
    node = rbtree["_M_t"]["_M_impl"]["_M_header"]["_M_left"]
    count = 0

    while count < size:
        result = node
        count += 1

        if count < size:
            # Compute the next node.
            if node.dereference()["_M_right"]:
                node = node.dereference()["_M_right"]
                while node.dereference()["_M_left"]:
                    node = node.dereference()["_M_left"]
            else:
                parent = node.dereference()["_M_parent"]
                while node == parent.dereference()["_M_right"]:
                    node = parent
                    parent = parent.dereference()["_M_parent"]
                if node.dereference()["_M_right"] != parent:
                    node = parent
        yield result


def stdmap_iterate(
    val: gdb.Value,
) -> Generator[Tuple[gdb.Value, gdb.Value], None, None]:
    rep_type = find_type(val.type, "_Rep_type")
    node_type = find_type(rep_type, "_Link_type").strip_typedefs()

    for node in rbtree_iterate(val):
        node = node.cast(node_type).dereference()
        pair = get_value_from_rb_tree_node(node)
        yield pair["first"], pair["second"]


def smallvector_iterate(val: gdb.Value) -> Generator[gdb.Value, None, None]:
    t = val.type.template_argument(0).pointer()
    begin = val["BeginX"].cast(t)
    size = int(val["Size"])

    for i in range(size):
        yield begin[i]


def is_sequence(container: gdb.Value) -> bool:
    ty = container.type.strip_typedefs()
    if ty is None:
        return False

    if ty.name is not None:
        if ty.name.startswith("llvm::SmallVector"):
            return True
        elif ty.name.startswith("std::vector"):
            return True
        elif ty.name.startswith("llvm::ArrayRef"):
            return True
        elif ty.name.startswith("std::array"):
            return True

    if ty.code == gdb.TYPE_CODE_ARRAY:
        return True
    elif ty.code == gdb.TYPE_CODE_PTR:
        return True

    return False


def is_map(container: gdb.Value) -> bool:
    ty = container.type.strip_typedefs()
    if ty is None:
        return False

    if ty.name is None:
        return False

    if ty.name.startswith("llvm::StringMap"):
        return True
    elif ty.name.startswith("std::map"):
        return True
    else:
        return False


def seq_iterate(container: gdb.Value) -> Generator[gdb.Value, None, None]:
    if container.type is None:
        raise UserError("Value has unknown type")

    ptr = None
    size = -1

    type_name = container.type.strip_typedefs().name or ""

    if type_name.startswith("llvm::SmallVector"):
        yield from smallvector_iterate(container)
        return

    if type_name.startswith("std::vector"):
        t = container.type.template_argument(0).pointer()
        impl = container["_M_impl"]
        start = impl["_M_start"].cast(t)
        finish = impl["_M_finish"].cast(t)

        ptr = start
        size = finish - start

    elif type_name.startswith("llvm::ArrayRef"):
        t = container.type.template_argument(0).pointer()

        ptr = container["Data"].cast(t)
        size = int(container["Length"])

    elif type_name.startswith("std::array"):
        t = container.type.template_argument(0).pointer()
        size_param = cast(gdb.Value, container.type.template_argument(1))

        ptr = container["_M_elems"].cast(t)
        size = int(size_param)

    elif container.type.code == gdb.TYPE_CODE_ARRAY:
        ptr = container
        size = container.type.range()[1] + 1

    else:
        raise UserError(f"Unsupported container type: {container.type}")

    for i in range(size):
        yield ptr[i]


def map_iterate(
    container: gdb.Value,
) -> Generator[Tuple[gdb.Value, gdb.Value], None, None]:
    if container.type.name.startswith("llvm::StringMap"):
        yield from stringmap_iterate(container)
        return

    elif container.type.name.startswith("std::map"):
        yield from stdmap_iterate(container)
        return

    else:
        raise UserError(f"Unsupported container type: {container.type.name}")


@convenience_function
def getitem(container: gdb.Value, item: Union[gdb.Value, int, str]) -> ValueOrNative:
    if isinstance(item, gdb.Value):
        try:
            item = int(item)
        except gdb.error as e:
            if "Cannot convert value to long." in str(e):
                item = item.string()

    assert isinstance(item, int) or isinstance(item, str)

    type_name = container.type.strip_typedefs().name or ""

    if type_name.startswith("llvm::SmallVector"):
        if not isinstance(item, int):
            raise UserError("SmallVector index must be an integer")

        size = int(container["Size"])
        if item < 0:
            item += size

        if not (0 <= item < size):
            raise UserError(f"SmallVector index {item} out of range (size={size})")

        t = container.type.template_argument(0).pointer()
        begin = container["BeginX"].cast(t)
        return begin[item]

    elif type_name.startswith("std::vector"):
        if not isinstance(item, int):
            raise UserError("std::vector index must be an integer")

        t = container.type.template_argument(0).pointer()
        impl = container["_M_impl"]
        start = impl["_M_start"].cast(t)
        finish = impl["_M_finish"].cast(t)
        size = finish - start

        if item < 0:
            item += size

        if not (0 <= item < size):
            raise UserError(f"std::vector index {item} out of range (size={size})")

        return start[item]

    elif type_name.startswith("llvm::ArrayRef"):
        if not isinstance(item, int):
            raise UserError("ArrayRef index must be an integer")
        size = int(container["Length"])

        if item < 0:
            item += size

        if not (0 <= item < size):
            raise UserError(f"ArrayRef index {item} out of range (size={size})")

        return container["Data"][item]

    elif type_name.startswith("std::array"):
        if not isinstance(item, int):
            raise UserError("std::array index must be an integer")
        size_param = cast(gdb.Value, container.type.template_argument(1))
        size = int(size_param)

        if item < 0:
            item += size

        if not (0 <= item < size):
            raise UserError(f"std::array index {item} out of range (size={size})")

        return container["_M_elems"][item]

    elif type_name.startswith("llvm::StringMap"):
        if not isinstance(item, str):
            raise UserError("StringMap key must be a string")

        for key, value in stringmap_iterate(container):
            if key == item:
                return value

        raise UserError(f"StringMap key '{item}' not found")

    elif type_name.startswith("std::map"):
        key_type = container.type.template_argument(0)
        # Ensure that the key type is either a string or an integer.
        is_string = False
        if key_type.code != gdb.TYPE_CODE_INT:
            type_name = key_type.strip_typedefs().name
            if not (
                type_name.startswith("std::string")
                or type_name.startswith("llvm::StringRef")
                or type_name.startswith("std::basic_string")
            ):
                raise UserError(f"Unsupported key type: {type_name}")
            is_string = True

        if is_string and not isinstance(item, str):
            raise UserError("std::map<std::string, ...> key must be a string")
        elif not is_string and not isinstance(item, int):
            raise UserError("std::map<int, ...> key must be an integer")

        for key, value in stdmap_iterate(container):
            if is_string:
                key = key.string()
            else:
                key = int(key)

            if key == item:
                return value

        raise UserError(f"std::map key '{item}' not found")

    elif (
        container.type.code == gdb.TYPE_CODE_ARRAY
        or container.type.code == gdb.TYPE_CODE_PTR
    ):
        if not isinstance(item, int):
            raise UserError("C array index must be an integer")

        if item < 0:
            raise UserError("C array index must be positive")

        t = container.type.target()
        return container[item].cast(t)

    else:
        raise UserError(f"Unsupported container type: {container.type}")


@register_command
class GetItemCommand(ExtendedCommand):
    """
    Get a value from a container, optionally storing it to a convenience variable. Most STL and LLVM sequential and map
    containers are supported, as long as the keys are integers, strings or pointers.

    Usage: getitem <container> <key> [<convenience_variable>]
    """

    name = "getitem"
    completer_class = gdb.COMPLETE_EXPRESSION

    def invoke_with_options(self, opts: ParsedOptions, from_tty: bool):
        container_expr = opts["<container>"]
        key_expr = opts["<key>"]
        convenience_variable = opts["<convenience_variable>"]

        container = gdb.parse_and_eval(container_expr)
        key = gdb.parse_and_eval(key_expr)

        value = getitem(container, key)
        self.return_value(value, var_name=convenience_variable, from_tty=from_tty)
