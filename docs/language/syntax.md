# Dictum Language Syntax

Dictum is a natural-language programming language that transpiles to C or C++. Its syntax reads like structured English.

## Programs and Modules

A **program** has a `main` entry point:

```dictum
program MyApp:
    print the text "Hello, World!" and newline
end program
```

A **module** declares reusable actions without a main:

```dictum
module MathUtils:
    action clamp takes V as whole number, Lo as whole number, Hi as whole number produces whole number:
        if V is less than Lo then:
            produce success with Lo
        end if
        if V is greater than Hi then:
            produce success with Hi
        end if
        produce success with V
    end action
end module
```

## Variables

```dictum
keep Name as text with value "Alice"
keep Count as whole number with value 0
keep Pi as decimal number with value 3.14159
keep Active as truth value with value true
```

Re-assign with `set`:

```dictum
set Count to 42
set Name to "Bob"
```

## Types

| Dictum type        | C type        |
|--------------------|---------------|
| `whole number`     | `int32_t`     |
| `decimal number`   | `double`      |
| `text`             | `const char*` |
| `truth value`      | `bool`        |
| `count`            | `size_t`      |
| `byte`             | `uint8_t`     |
| `nothing`          | `void`        |

## Arithmetic

```dictum
put the sum of A and B into C
put the product of X and 2 into Y
put A minus B into Diff
put A divided by B into Quot
```

## Conditionals

```dictum
if X is greater than 10 then:
    print the text "big" and newline
otherwise:
    print the text "small" and newline
end if
```

Comparison operators: `is equal to`, `is not equal to`, `is less than`, `is greater than`, `is less than or equal to`, `is greater than or equal to`.

## Loops

```dictum
while I is less than 10:
    put the sum of I and 1 into I
end while
```

```dictum
for each Item in Collection:
    print the text Item and newline
end for
```

## Actions (Functions)

```dictum
action greet takes Name as text produces nothing:
    print the text "Hello, " and newline
    print the text Name and newline
end action
```

Call with:
```dictum
call greet with "World"
```

Or store the result:
```dictum
keep R as whole number
put factorial with 5 into R
```

## Error Handling

```dictum
attempt
    call Http.get with "https://example.com" giving Response
on failure with Err
    print the text Err and newline
end attempt
```

## Shapes (Structs)

```dictum
shape Point holds:
    X as whole number
    Y as whole number
end shape

keep P as Point
set P.X to 10
set P.Y to 20
```

## Using Standard Library Modules

```dictum
use Http
use Json
use Console
use File
use Net
```
