# GDB common utilities library

This is a collection of common utilities for GDB.

## Installation

In your `~/.gdbinit` file, add the following line:

```
source /path/to/gdb-scripts/commons_lib.py
```

## Utilities

### Commands

You can invoke commands from your regular GDB shell by typing the command name.

#### `deref`

Dereference an expression containing a pointer or a C++ pointer-like object and
store the result in a convenience variable.

```
Usage: deref [-r] <expression> [<convenience_variable>]

Options:
    -r --recursive  Dereference recursively until a non-pointer type is reached
```

#### `getitem`

Get a value from a container, optionally storing it to a convenience variable.
Most STL and LLVM sequential and map containers are supported, as long as the
keys are integers, strings or pointers.

```
Usage: getitem <container> <key> [<convenience_variable>]
```

#### `ptpython`

Start a [ptpython](https://github.com/prompt-toolkit/ptpython) interactive
shell. This is a Python REPL with syntax highlighting, autocompletion and
history navigation.

This command is only available if the dependencies (`requirements.txt`) are
installed.

Within the Python REPL you can use a number of helpers that are exclusive to
Python. These are documented below.

### Convenience functions

Use convenience functions as you would use a C function within the `print` GDB
command.

For instance, to check for string equality in a breakpoint condition:

```
break foo.c:42 if $equals(some_symbol, "some string")
```

All convenience functions are also available as Python functions.

#### `$deref`

Same as the `deref` command, but it returns the dereferenced value directly.

```
$deref(symbol)
```

#### `$getitem`

Same as the `getitem` command, but it returns the value directly.

```
$getitem(container, key)
```

#### `$equals`, `$eq` - `$not_equals`, `$ne`

Check for equality between two values. Values are first dereferenced and an
attempt to convert them to a native Python type is made.

The comparison is then performed using Python's `==` operator.

If the values can't be converted to a native Python type, the comparison is
performed by checking identity in the inferior process.

```
$equals(value1, value2)
$eq(value1, value2)
$not_equals(value1, value2)
$ne(value1, value2)
```

#### `$less_than`, `$lt` - `$less_than_or_equal`, `$le`, `$greater_than`, `$gt` - `$greater_than_or_equal`, `$ge`

Compare two values. Values are first dereferenced and an attempt to convert them
to a native Python type is made.

The comparison is then performed using only Python's `<`, `<=` operators and
their negations.

```
$less_than(value1, value2)
$lt(value1, value2)
$less_than_or_equal(value1, value2)
$le(value1, value2)
$greater_than(value1, value2)
$gt(value1, value2)
$greater_than_or_equal(value1, value2)
$ge(value1, value2)
```

#### `$contains`, `$in`

Check if a value is contained in a container.

The following containers are supported:

- Strings
    - `char *`
    - `char []`
    - `std::string`
    - `std::string_view`
    - `llvm::StringRef`
- C fixed-size arrays
- C++ sequential containers
    - `std::vector`
    - `std::array`
    - `llvm::SmallVector`
    - `llvm::ArrayRef`
- C++ maps (it checks whether the value is contained in the map keys)
    - `std::map`
    - `llvm::StringMap`

```
$contains(container, value)
$in(value, container)
```

#### `$values_contain`, `$in_values`

Check if a value is contained in a map container values.

The following containers are supported:

- C++ maps
    - `std::map`
    - `llvm::StringMap`

```
$values_contain(container, value)
$in_values(value, container)
```

### Python-only helpers

These helpers are only available within Python.

Convenience functions are also available as Python functions, without the
leading `$`.

#### `gdb(string)`

Shortcut for `gdb.parse_and_eval(string)`. Use it to obtain a value from GDB
into Python.

#### `p(value)`

Output a `gdb.Value` object to the GDB console and store it into the GDB
history, similar to the GDB `print` command.

#### `is_seq(value)`

Check if a value is a supported sequential container.

#### `seq_iterate(value)`

Iterate over a supported sequential container's items.

#### `is_map(value)`

Check if a value is a supported map container.

#### `map_iterate(value)`

Iterate over a supported map container's key-value pairs.

#### `add_to_history(value)`

Add a value to the GDB history.

