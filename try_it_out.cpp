#include <iostream>
#include <string>
#include <string_view>
#include <vector>
#include <array>
#include <map>
#include <memory>
#include <queue>
#include <deque>
#include <list>
#include <stack>

#ifdef WITH_LLVM
#include <llvm/ADT/SmallVector.h>
#include <llvm/ADT/ArrayRef.h>
#include <llvm/ADT/StringMap.h>
#include <llvm/ADT/StringRef.h>
#endif

int main() {
    // Basic types and pointers
    int basic_int = 42;
    double basic_double = 42.5;
    int* int_ptr = &basic_int;
    double* double_ptr = &basic_double;

    // Pointer-like objects
    auto unique_str_ptr = std::make_unique<std::string>("UniqueStr");
    auto shared_int_ptr = std::make_shared<int>(42);

    // Strings and similar
    std::string str = "Hello, GDB!";
    std::string_view str_view = "Hello, StringView!";
#ifdef WITH_LLVM
    llvm::StringRef llvm_str_ref = "Hello, LLVM!";
#endif

    // C fixed-size arrays
    char char_array[6] = "GDB++";
    int int_array[3] = {1, 2, 3};

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

    // Queues, deques, lists
    std::queue<int> int_queue;
    int_queue.push(1);
    int_queue.push(2);
    int_queue.push(3);

    std::deque<int> int_deque;
    int_deque.push_back(1);
    int_deque.push_back(2);
    int_deque.push_back(3);

    std::list<int> int_list;
    int_list.push_back(1);
    int_list.push_back(2);
    int_list.push_back(3);

    // Stacks
    std::stack<int> int_stack;
    int_stack.push(1);
    int_stack.push(2);
    int_stack.push(3);

    return 0;
}
