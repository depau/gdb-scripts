# Copyright 2018 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Helper library for defining XMethod implementations on C++ classes.
Include this library and then define python implementations of C++ methods
using the Class and member_function decorator functions.
"""

import operator
import re
from typing import TypeAlias, Union

import gdb
import gdb.xmethod

from _commons_lib.utils import ValueOrNative


class MemberFunction(object):
    def __init__(self, return_type, name, arguments, wrapped_function):
        self.return_type = return_type
        self.name = name
        self.arguments = arguments
        self.function_ = wrapped_function

    def __call__(self, *args):
        self.function_(*args)


def member_function(return_type, name, arguments=()):
    """Decorate a member function.
    See Class decorator for example usage within a class.
    Args:
      return_type: The return type of the function (e.g. 'int')
      name: The function name (e.g. 'sum')
      arguments: The argument types for this function (e.g. ['int', 'int'])
      Each type can be a string (e.g. 'int', 'std::string', 'T*') or a
      function which constructs the return type. See CreateTypeResolver
      for details about type resolution.
    """

    def define_member(fn):
        return MemberFunction(return_type, name, arguments, fn)

    return define_member


def cpp_class(class_name, template_types=()):
    """Decorate a python class with its corresponding C++ type.
    Args:
      class_name: The canonical string identifier for the class (e.g. base::Foo)
      template_types: An array of names for each templated type (e.g. ['K',
      'V'])
    Example:
      As an example, the following is an implementation of size() and operator[]
      on std::__1::vector, functions which are normally inlined and not
      normally callable from gdb.
      @class_methods.Class('std::__1::vector', template_types=['T'])
      class LibcppVector(object):
        @class_methods.member_function('T&', 'operator[]', ['int'])
        def element(obj, i):
          return obj['__begin_'][i]
        @class_methods.member_function('size_t', 'size', [])
        def size(obj):
          return obj['__end_'] - obj['__begin_']
    Note:
      Note that functions are looked up by the function name, which means that
      functions cannot currently have overloaded implementations for different
      arguments.
    """

    class MethodWorkerWrapper(gdb.xmethod.XMethod):
        """Wrapper of an XMethodWorker class as an XMethod."""

        def __init__(self, name, worker_class):
            super(MethodWorkerWrapper, self).__init__(name)
            self.name = name
            self.worker_class = worker_class

    class ClassMatcher(gdb.xmethod.XMethodMatcher):
        """Matches member functions of one class template."""

        def __init__(self, obj):
            super(ClassMatcher, self).__init__(class_name)
            # Constructs a regular expression to match this type.
            self._class_regex = re.compile(
                "^"
                + re.escape(class_name)
                + ("<.*>" if len(template_types) > 0 else "")
                + "$"
            )
            # Construct a dictionary and array of methods
            self.dict = {}
            self.methods = []
            for name in dir(obj):
                attr = getattr(obj, name)
                if not isinstance(attr, MemberFunction):
                    continue
                name = attr.name
                return_type = create_type_resolver(attr.return_type)
                arguments = [create_type_resolver(arg) for arg in attr.arguments]
                method = MethodWorkerWrapper(
                    attr.name,
                    create_templated_method_worker(
                        return_type, arguments, attr.function_
                    ),
                )
                self.methods.append(method)

        def match(self, class_type: gdb.Type, method_name: str):
            if not re.match(self._class_regex, class_type.tag):
                return None
            templates = [
                class_type.template_argument(i) for i in range(len(template_types))
            ]
            return [
                method.worker_class(templates)
                for method in self.methods
                if method.name == method_name and method.enabled
            ]

    def create_type_resolver(type_desc):
        """Creates a callback which resolves to the appropriate type when
        invoked.
        This is a helper to allow specifying simple types as strings when
        writing function descriptions. For complex cases, a callback can be
        passed which will be invoked when template instantiation is known.
        Args:
          type_desc: A callback generating the type or a string description of
              the type to lookup. Supported types are classes in the
              template_classes array (e.g. T) which will be looked up when those
              templated classes are known, or globally visible type names (e.g.
              int, base::Foo).
              Types can be modified by appending a '*' or '&' to denote a
              pointer or reference.
              If a callback is used, the callback will be passed an array of the
              instantiated template types.
        Note:
          This does not parse complex types such as std::vector<T>::iterator,
          to refer to types like these you must currently write a callback
          which constructs the appropriate type.
        """
        if callable(type_desc):
            return type_desc
        if type_desc == "void":
            return lambda T: None
        if type_desc[-1] == "&":
            inner_resolver = create_type_resolver(type_desc[:-1])
            return lambda template_types: inner_resolver(template_types).reference()
        if type_desc[-1] == "*":
            inner_resolver = create_type_resolver(type_desc[:-1])
            return lambda template_types: inner_resolver(template_types).pointer()
        try:
            template_index = template_types.index(type_desc)
            return operator.itemgetter(template_index)
        except ValueError:
            return lambda template_types: gdb.lookup_type(type_desc)

    def create_templated_method_worker(
        return_callback, args_callbacks, method_callback
    ):
        class TemplatedMethodWorker(gdb.xmethod.XMethodWorker):
            def __init__(self, templates):
                super(TemplatedMethodWorker, self).__init__()
                self._templates = templates

            def get_arg_types(self):
                return [cb(self._templates) for cb in args_callbacks]

            def get_result_type(self, obj):
                return return_callback(self._templates)

            def __call__(self, *args):
                return method_callback(*args)

        return TemplatedMethodWorker

    def define_class(obj):
        matcher = ClassMatcher(obj)
        gdb.xmethod.register_xmethod_matcher(None, matcher)  # type: ignore
        return matcher

    return define_class


ValueOrInt: TypeAlias = Union[gdb.Value, int]


class LazyString:
    def value(self) -> gdb.Value:
        ...

    address: gdb.Value
    length: int
    encoding: str
    type: gdb.Type


class CppClass:
    # Fool the type checker
    address: gdb.Value
    is_optimized_out: bool
    type: gdb.Type
    dynamic_type: gdb.Type
    is_lazy: bool

    def __index__(self) -> int:
        ...

    def __int__(self) -> int:
        ...

    def __float__(self) -> float:
        ...

    def __add__(self, other: ValueOrInt) -> gdb.Value:
        ...

    def __sub__(self, other: ValueOrInt) -> gdb.Value:
        ...

    def __mul__(self, other: ValueOrInt) -> gdb.Value:
        ...

    def __truediv__(self, other: ValueOrInt) -> gdb.Value:
        ...

    def __mod__(self, other: ValueOrInt) -> gdb.Value:
        ...

    def __and__(self, other: ValueOrInt) -> gdb.Value:
        ...

    def __or__(self, other: ValueOrInt) -> gdb.Value:
        ...

    def __xor__(self, other: ValueOrInt) -> gdb.Value:
        ...

    def __lshift__(self, other: ValueOrInt) -> gdb.Value:
        ...

    def __rshift__(self, other: ValueOrInt) -> gdb.Value:
        ...

    def __eq__(self, other: ValueOrInt) -> bool:
        ...  # type: ignore[override]

    def __ne__(self, other: ValueOrInt) -> bool:
        ...  # type: ignore[override]

    def __lt__(self, other: ValueOrInt) -> bool:
        ...

    def __le__(self, other: ValueOrInt) -> bool:
        ...

    def __gt__(self, other: ValueOrInt) -> bool:
        ...

    def __ge__(self, other: ValueOrInt) -> bool:
        ...

    def __getitem__(self, key: Union[int, str, gdb.Field]) -> gdb.Value:
        ...

    def __call__(self, *args: ValueOrNative) -> gdb.Value:
        ...

    def __init__(self, val: ValueOrNative) -> None:
        ...

    def cast(self, type: gdb.Type) -> gdb.Value:
        ...

    def dereference(self) -> gdb.Value:
        ...

    def referenced_value(self) -> gdb.Value:
        ...

    def reference_value(self) -> gdb.Value:
        ...

    def const_value(self) -> gdb.Value:
        ...

    def dynamic_cast(self, type: gdb.Type) -> gdb.Value:
        ...

    def reinterpret_cast(self, type: gdb.Type) -> gdb.Value:
        ...

    def format_string(
        self,
        raw: bool = ...,
        pretty_arrays: bool = ...,
        pretty_structs: bool = ...,
        array_indexes: bool = ...,
        symbols: bool = ...,
        unions: bool = ...,
        address: bool = ...,
        deref_refs: bool = ...,
        actual_objects: bool = ...,
        static_members: bool = ...,
        max_elements: int = ...,
        max_depth: int = ...,
        repeat_threshold: int = ...,
        format: str = ...,
    ) -> str:
        ...

    def string(self, encoding: str = ..., errors: str = ..., length: int = ...) -> str:
        ...

    def lazy_string(self, encoding: str = ..., length: int = ...) -> LazyString:
        ...

    def fetch_lazy(self) -> None:
        ...
