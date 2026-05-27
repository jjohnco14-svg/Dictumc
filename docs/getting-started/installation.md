# Installation

Dictum v5 requires Python 3.11+ and GCC (or Clang) for compiling emitted C.

## Prerequisites

### Linux (Ubuntu/Debian)
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip gcc make \
    libcurl4-openssl-dev libssl-dev
```

### macOS
```bash
brew install gcc curl openssl
```

### Windows
Dictum requires WSL 2 on Windows. Install Ubuntu from the Microsoft Store, then follow the Linux steps above.

## Install the Dictum Python package

```bash
pip install dictum
```

Or from source:
```bash
git clone https://github.com/your-org/dictum
cd dictum
pip install -e .
```

## Build the standard library

The stdlib must be compiled once before any Dictum program that uses `use Http`, `use Net`, etc. can link:

```bash
cd stdlib
make lib
```

This produces `stdlib/libdictum_stdlib.a`.

## Verify your installation

```bash
dictumc --version
```

Then transpile and run the hello-world example:

```bash
dictumc examples/level1.dict -o hello.c
gcc -std=c11 hello.c stdlib/libdictum_stdlib.a -Istdlib -lm -o hello
./hello
```

Expected output: `Hello, World!`

## VibeCoder UI (optional)

```bash
pip install "dictum[server]"
python ui/backend_server.py
# Open http://localhost:8765 in your browser
```

Or with Docker:
```bash
docker build -t dictum-vibecoder .
docker run -p 8765:8765 dictum-vibecoder
```
