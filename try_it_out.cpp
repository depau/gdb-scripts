#include <iostream>
#include <string>
#include <string_view>
#include <vector>
#include <array>
#include <map>
#include <memory>

#ifdef WITH_LLVM
#include <llvm/ADT/SmallVector.h>
#include <llvm/ADT/ArrayRef.h>
#include <llvm/ADT/StringMap.h>
#include <llvm/ADT/StringRef.h>
#endif

int main() {
    // Basic types and pointers
    int basic_int;
    int* int_ptr = new int(10);
    double* double_ptr = new double(10.5);

    // Pointer-like objects
    std::unique_ptr<std::string> unique_str_ptr = std::make_unique<std::string>("UniqueStr");
    std::shared_ptr<int> shared_int_ptr = std::make_shared<int>(42);

    // Strings and similar
    std::string str = "Hello, GDB!";
    std::string_view str_view = "Hello, StringView!";
#ifdef WITH_LLVM
    llvm::StringRef llvm_str_ref = "Hello, LLVM!";
#endif

    // C fixed-size arrays
    char char_array[6] = "GDB++";
    int int_array[3];

    // C++ sequential containers
    std::vector<std::string> vec = {"A", "B", "C"};
    std::array<int, 3> arr;

#ifdef WITH_LLVM
    llvm::SmallVector<int, 3> llvm_small_vec = {7, 8, 9};
    llvm::ArrayRef<int> llvm_array_ref(int_array, 3);
#endif

    // C++ map containers
    std::map<std::string, int> str_int_map = {
        {"One", 1},
        {"Two", 2},
        {"Three", 3}
    };

#ifdef WITH_LLVM
    llvm::StringMap<int> llvm_str_int_map;
    llvm_str_int_map.insert({"Four", 4});
    llvm_str_int_map.insert({"Five", 5});
#endif

    return 0;
}
