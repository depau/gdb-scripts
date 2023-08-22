import math
import re
import traceback
from functools import cache
from typing import Union, Generator, Tuple, cast, Optional

import gdb

from _commons_lib.deref import deref
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


# The STL iteration functions have been adapted from:
# https://github.com/gcc-mirror/gcc/blob/34c614b7e9dcb52a23063680f3622c842a9712ec/libstdc%2B%2B-v3/python/libstdcxx/v6/printers.py
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


def stdset_iterate(
    val: gdb.Value,
) -> Generator[gdb.Value, None, None]:
    rep_type = find_type(val.type, "_Rep_type")
    node_type = find_type(rep_type, "_Link_type").strip_typedefs()

    for node in rbtree_iterate(val):
        node = node.cast(node_type).dereference()
        yield get_value_from_rb_tree_node(node)


def stdmap_iterate(
    val: gdb.Value,
) -> Generator[Tuple[gdb.Value, gdb.Value], None, None]:
    for pair in stdset_iterate(val):
        yield pair["first"], pair["second"]


def stddeque_iterate(
    val: gdb.Value,
) -> Generator[gdb.Value, None, None]:
    t = val.type.template_argument(0)
    size = t.sizeof
    if size < 512:
        buffer_size = int(512 / size)
    else:
        buffer_size = 1

    start = val["_M_impl"]["_M_start"]
    end = val["_M_impl"]["_M_finish"]

    node = start["_M_node"]
    p = start["_M_cur"]
    last = end["_M_cur"]
    end_of_bucket = start["_M_last"]

    while p != last:
        yield p.dereference()

        # Advance the 'cur' pointer.
        p = p + 1
        if p == end_of_bucket:
            # If we got to the end of this bucket, move to the
            # next bucket.
            node = node + 1
            p = node[0]
            end_of_bucket = p + buffer_size


def lookup_templ_spec(templ: str, *args: str) -> gdb.Type:
    """
    Lookup template specialization templ<args...>
    """
    t = "{}<{}>".format(templ, ", ".join([str(a) for a in args]))
    try:
        return gdb.lookup_type(t)
    except gdb.error as e:
        # Type not found, try again in versioned namespace.
        global _versioned_namespace
        if _versioned_namespace and _versioned_namespace not in templ:
            t = t.replace("::", "::" + _versioned_namespace, 1)
            try:
                return gdb.lookup_type(t)
            except gdb.error:
                # If that also fails, rethrow the original exception
                pass
        raise e


def is_member_of_namespace(typ: Union[str, gdb.Type], *namespaces: str) -> bool:
    """
    Test whether a type is a member of one of the specified namespaces.
    The type can be specified as a string or a gdb.Type object.
    """
    if type(typ) is gdb.Type:
        typ = str(typ)
    typ = strip_versioned_namespace(typ)
    for namespace in namespaces:
        if typ.startswith(namespace + "::"):
            return True
    return False


_versioned_namespace = "__8::"


def is_specialization_of(x: Union[str, gdb.Type], template_name: str) -> bool:
    """
    Test whether a type is a specialization of the named class template.
    The type can be specified as a string or a gdb.Type object.
    The template should be the name of a class template as a string,
    without any 'std' qualification.
    """
    global _versioned_namespace
    if type(x) is gdb.Type:
        x = x.tag
    if _versioned_namespace:
        return (
            re.match("^std::(%s)?%s<.*>$" % (_versioned_namespace, template_name), x)
            is not None
        )
    return re.match("^std::%s<.*>$" % template_name, x) is not None


def strip_versioned_namespace(typename: str) -> str:
    global _versioned_namespace
    if _versioned_namespace:
        return typename.replace(_versioned_namespace, "")
    return typename


# Use this to find container node types instead of find_type,
# see https://gcc.gnu.org/bugzilla/show_bug.cgi?id=91997 for details.
def lookup_node_type(nodename: str, containertype: gdb.Type) -> Optional[gdb.Type]:
    """
    Lookup specialization of template NODENAME corresponding to CONTAINERTYPE.
    e.g. if NODENAME is '_List_node' and CONTAINERTYPE is std::list<int>
    then return the type std::_List_node<int>.
    Returns None if not found.
    """
    # If nodename is unqualified, assume it's in namespace std.
    if "::" not in nodename:
        nodename = "std::" + nodename
    try:
        valtype = find_type(containertype, "value_type")
    except:
        valtype = containertype.template_argument(0)
    valtype = valtype.strip_typedefs()
    try:
        return lookup_templ_spec(nodename, valtype)
    except gdb.error as e:
        # For debug mode containers the node is in std::__cxx1998.
        if is_member_of_namespace(nodename, "std"):
            if is_member_of_namespace(
                containertype, "std::__cxx1998", "std::__debug", "__gnu_debug"
            ):
                nodename = nodename.replace("::", "::__cxx1998::", 1)
                try:
                    return lookup_templ_spec(nodename, valtype)
                except gdb.error:
                    pass
        return None


def get_value_from_aligned_membuf(buf, valtype):
    """Returns the value held in a __gnu_cxx::__aligned_membuf."""
    return buf["_M_storage"].address.cast(valtype.pointer()).dereference()


def get_value_from_list_node(node):
    """Returns the value held in an _List_node<_Val>"""
    try:
        member = node.type.fields()[1].name
        if member == "_M_data":
            # C++03 implementation, node contains the value as a member
            return node["_M_data"]
        elif member == "_M_storage":
            # C++11 implementation, node stores value in __aligned_membuf
            valtype = node.type.template_argument(0)
            return get_value_from_aligned_membuf(node["_M_storage"], valtype)
    except:
        pass
    raise ValueError("Unsupported implementation for %s" % str(node.type))


def stdlist_iterate(val: gdb.Value) -> Generator[gdb.Value, None, None]:
    nodetype = lookup_node_type("_List_node", val.type).pointer()
    head = val["_M_impl"]["_M_node"]
    base = head["_M_next"]

    while base != head.address:
        elt = base.cast(nodetype).dereference()
        base = elt["_M_next"]
        yield get_value_from_list_node(elt)


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
        elif ty.name.startswith("std::set"):
            return True
        elif ty.name.startswith("llvm::SmallSet"):
            return True
        elif (
            ty.name.startswith("std::queue")
            or ty.name.startswith("std::deque")
            or ty.name.startswith("std::stack")
            or ty.name.startswith("std::_Deque_base")
        ):
            return True
        elif ty.name.startswith("std::list") or ty.name.startswith(
            "std::__cxx11::list"
        ):
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

    elif type_name.startswith("std::set"):
        yield from stdset_iterate(container)
        return

    elif type_name.startswith("llvm::SmallSet"):
        stdset_size = int(container["Set"]["_M_t"]["_M_impl"]["_M_node_count"])
        if stdset_size <= 0:
            yield from smallvector_iterate(container["Vector"])
            return
        else:
            yield from stdset_iterate(container["Set"])
            return

    elif type_name.startswith("std::queue") or type_name.startswith("std::stack"):
        deque = container["c"]
        yield from stddeque_iterate(deque)

    elif type_name.startswith("std::_Deque_base") or type_name.startswith("std::deque"):
        yield from stddeque_iterate(container)

    elif type_name.startswith("std::list") or type_name.startswith(
        "std::__cxx11::list"
    ):
        yield from stdlist_iterate(container)

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
                or type_name.startswith("std::__cxx11::basic_string")
            ):
                raise UserError(f"Unsupported key type: {type_name}")
            is_string = True

        if is_string and not isinstance(item, str):
            raise UserError("std::map<std::string, ...> key must be a string")
        elif not is_string and not isinstance(item, int):
            raise UserError("std::map<int, ...> key must be an integer")

        for key, value in stdmap_iterate(container):
            if is_string:
                key = deref(key)
                if isinstance(key, gdb.Value):
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
        try:
            key = gdb.parse_and_eval(key_expr)
        except gdb.error as e:
            if f'No symbol "{key_expr}" in current context.' in str(e):
                # Work around GDB being stupid and not returning strings as strings sometimes
                key = key_expr
            else:
                raise

        value = getitem(container, key)
        self.return_value(value, var_name=convenience_variable, from_tty=from_tty)
