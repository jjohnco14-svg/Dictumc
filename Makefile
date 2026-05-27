# Dictum v5 — Top-level Makefile
# Delegates to stdlib/ and niche/ sub-makes, runs Python tests.

.PHONY: all stdlib niche test test-python test-c install clean

all: stdlib niche

stdlib:
	$(MAKE) -C stdlib lib

niche:
	$(MAKE) -C niche lib

test: test-python test-c

test-python:
	python -m pytest tests/ -v --tb=short

test-c:
	$(MAKE) -C stdlib test

install:
	pip install -e ".[dev,server]"

clean:
	$(MAKE) -C stdlib clean
	$(MAKE) -C niche clean
	find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
