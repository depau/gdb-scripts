from _commons_lib import deref
from _commons_lib.comparisons import equals
from _commons_lib.xmethods import cpp_class, CppClass, member_function


@cpp_class("std::unique_ptr", ["T"])
class StdUniquePtr(CppClass):
    @member_function("T&", "operator*")
    def operator_deref(obj):
        return deref(obj)

    @member_function("T*", "operator->")
    def operator_arrow(obj):
        return deref(obj).pointer()


@cpp_class("std::shared_ptr", ["T"])
class StdSharedPtr(CppClass):
    @member_function("T&", "operator*")
    def operator_deref(obj):
        return deref(obj)

    @member_function("T*", "operator->")
    def operator_arrow(obj):
        return deref(obj).pointer()


@cpp_class("std::optional", ["T"])
class StdOptional(CppClass):
    @member_function("T&", "operator*")
    def operator_deref(obj):
        return deref(obj)

    @member_function("T*", "operator->")
    def operator_arrow(obj):
        return deref(obj).pointer()

    @member_function("bool", "has_value")
    def has_value(obj):
        return obj["_M_engaged"]


@cpp_class("std::basic_string", ["CharT"])
class StdBasicString(CppClass):
    @member_function("CharT*", "data")
    def data(obj):
        return obj["_M_dataplus"]["_M_p"]

    @member_function("size_t", "size")
    def size(obj):
        return obj["_M_string_length"]

    @member_function("CharT*", "c_str")
    def c_str(obj):
        return obj["_M_dataplus"]["_M_p"]

    @member_function("bool", "operator==", ["std::string"])
    def operator_eq(obj, other):
        return equals(obj, other, from_tty=True)

    @member_function("bool", "operator==", ["CharT*"])
    def operator_eq1(obj, other):
        return equals(obj, other, from_tty=True)

    @member_function("bool", "operator==", ["llvm::StringRef"])
    def operator_eq2(obj, other):
        return equals(obj, other, from_tty=True)


@cpp_class("llvm::StringRef")
class LLVMStringRef(CppClass):
    @member_function("const char*", "data")
    def data(obj):
        return obj["Data"]

    @member_function("size_t", "size")
    def size(obj):
        return obj["Length"]

    @member_function("bool", "operator==", ["llvm::StringRef"])
    def operator_eq(obj, other):
        return equals(obj, other, from_tty=True)

    @member_function("bool", "operator==", ["CharT*"])
    def operator_eq1(obj, other):
        return equals(obj, other, from_tty=True)

    @member_function("bool", "operator==", ["std::string"])
    def operator_eq2(obj, other):
        return equals(obj, other, from_tty=True)


@cpp_class("llvm::Optional", ["T"])
class LLVMOptional(CppClass):
    @member_function("T&", "operator*")
    def operator_deref(obj):
        return deref(obj)

    @member_function("T*", "operator->")
    def operator_arrow(obj):
        return deref(obj).pointer()

    @member_function("bool", "has_value")
    def has_value(obj):
        return obj["hasVal"]

    @member_function("bool", "hasValue")
    def has_value1(obj):
        return obj["hasVal"]


@cpp_class("std::string")
@cpp_class("std::vector", ["T"])
class StdVector(CppClass):
    @member_function("T&", "operator[]", ["int"])
    def operator_subscript(obj, index):
        return obj["M_impl"]["_M_start"][index]

    @member_function("T&", "at", ["int"])
    def at(obj, index):
        return obj["M_impl"]["_M_start"][index]

    @member_function("size_t", "size")
    def size(obj):
        return obj["M_impl"]["_M_finish"] - obj["M_impl"]["_M_start"]


@cpp_class("llvm::SmallVector", ["T", "N"])
class LLVMSmallVector(CppClass):
    @member_function("T&", "operator[]", ["int"])
    def operator_subscript(obj, index):
        return obj["BeginX"][index]

    @member_function("T&", "at", ["int"])
    def at(obj, index):
        return obj["BeginX"][index]

    @member_function("size_t", "size")
    def size(obj):
        return obj.type.template_argument(1)
