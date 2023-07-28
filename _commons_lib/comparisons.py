import gdb

from _commons_lib.collections import is_sequence, seq_iterate, is_map, map_iterate
from _commons_lib.deref import deref
from _commons_lib.utils import (
    convenience_function,
    ValueOrNative,
    UserError,
    str_repr,
    type_repr,
)


@convenience_function(aliases=["eq"])
def equals(lhs: gdb.Value, rhs: gdb.Value, *, from_tty=False) -> ValueOrNative:
    v1 = deref(lhs, from_tty=from_tty)
    v2 = deref(rhs, from_tty=from_tty)

    return v1 == v2


@convenience_function(aliases=["ne"])
def not_equals(lhs: gdb.Value, rhs: gdb.Value, *, from_tty=False) -> ValueOrNative:
    return not equals(lhs, rhs, from_tty=from_tty)


@convenience_function(aliases=["lt"])
def less_than(lhs: gdb.Value, rhs: gdb.Value, *, from_tty=False) -> ValueOrNative:
    v1 = deref(lhs, from_tty=from_tty)
    v2 = deref(rhs, from_tty=from_tty)

    return v1 < v2


@convenience_function(aliases=["le"])
def less_than_or_equal(
    lhs: gdb.Value, rhs: gdb.Value, *, from_tty=False
) -> ValueOrNative:
    v1 = deref(lhs, from_tty=from_tty)
    v2 = deref(rhs, from_tty=from_tty)

    return v1 <= v2


@convenience_function(aliases=["gt"])
def greater_than(lhs: gdb.Value, rhs: gdb.Value, *, from_tty=False) -> ValueOrNative:
    return not less_than_or_equal(lhs, rhs, from_tty=from_tty)


@convenience_function(aliases=["ge"])
def greater_than_or_equal(
    lhs: gdb.Value, rhs: gdb.Value, *, from_tty=False
) -> ValueOrNative:
    return not less_than(lhs, rhs, from_tty=from_tty)


@convenience_function
def contains(container: gdb.Value, item: gdb.Value, *, from_tty=False) -> ValueOrNative:
    _container = deref(container, from_tty=from_tty)
    _item = deref(item, from_tty=from_tty)

    if is_sequence(_container):
        for item in seq_iterate(_container):
            if item == _item:
                return True
        return False

    elif is_map(_container):
        for key, _ in map_iterate(_container):
            if key == _item:
                return True

    if not isinstance(_container, str):
        raise UserError(
            f"Cannot check if {str_repr(_item)} ({type_repr(_item)}) is in {str_repr(_container)} ({type_repr(_container)})"
        )

    return _item in _container


@convenience_function("in")
def in_(item: gdb.Value, container: gdb.Value, *, from_tty=False) -> ValueOrNative:
    return contains(container, item, from_tty=from_tty)


@convenience_function
def values_contain(
    container: gdb.Value, item: gdb.Value, *, from_tty=False
) -> ValueOrNative:
    _container = deref(container, from_tty=from_tty)
    _item = deref(item, from_tty=from_tty)

    if not is_map(_container):
        raise UserError(
            f"Cannot check if {str_repr(_item)} ({type_repr(_item)}) is in the values of a non-map {str_repr(_container)} ({type_repr(_container)})"
        )

    for _, value in map_iterate(_container):
        if value == _item:
            return True

    return False


@convenience_function
def in_values(
    item: gdb.Value, container: gdb.Value, *, from_tty=False
) -> ValueOrNative:
    return values_contain(container, item, from_tty=from_tty)
