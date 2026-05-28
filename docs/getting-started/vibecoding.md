# Vibecoding with Dictum

Dictum is designed for **vibecoding** — using LLMs to generate code through natural language prompts.

## Why Dictum Wins for AI-Assisted Coding

### 1. Grammar Constraints Prevent Hallucinations

Dictum's grammar-constrained generation ensures the LLM can only produce syntactically valid code:

```python
from dictumc_production_testing import DictumGrammar, GrammarConstrainedGenerator

grammar = DictumGrammar(cpp_mode=True, strict=True)
generator = GrammarConstrainedGenerator(grammar, vocab)

# LLM can only generate valid Dictum tokens at each step
next_token_mask = generator.get_next_token_mask()
```

### 2. Natural Language Syntax Maps Directly to Prompts

| Prompt | Dictum Output |
|--------|---------------|
| "Create a variable X with value 42" | `keep X as whole number with value 42` |
| "If X is greater than 10, print hello" | `if X is greater than 10 then: print the text "hello" and newline end if` |
| "Repeat 5 times" | `repeat 5 times using I: ... end repeat` |

### 3. Type Safety Without Ceremony

The validator catches errors at transpile time:

```
[Line 3] Type mismatch: cannot initialize 'Count' (whole number) with text
[Line 5] Ownership violation: handle 'Buffer' not released at program exit
[Line 7] Use-after-free: handle 'Buffer' used after release
```

### 4. Prompt Template

```
Write a Dictum program that:
1. Initializes a servo on pin 9
2. Sets angle to 90 degrees
3. Waits 1 second
4. Detaches the servo

Use the robotics stdlib. Target: ESP32-S3.
```

Output:
```dictum
program ServoDemo:
    keep Arm as servo handle
    call dictum_servo_init with 9 and 50 and Arm
    call dictum_servo_set_angle with Arm and 90
    call dictum_task_sleep with 1000
    call dictum_servo_detach with Arm
end program
```

## Best Practices

1. **Start with stdlib snippets**: `dictumc --snippet robot` gives you a scaffold
2. **Use `--grammar-guided`**: Forces LLM output through the grammar validator
3. **Iterate in REPL**: Test small snippets before building full programs
4. **Check warnings**: The transpiler warns about potential issues
