"""pytest configuration — ensure dictumc package root is on sys.path (v5)."""
import sys
import os
# Insert project root (parent of tests/) so `import dictumc` works as a package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
