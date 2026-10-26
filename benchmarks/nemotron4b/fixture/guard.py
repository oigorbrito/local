"""Deliberately vulnerable fixture."""
from pathlib import Path

def read_text_under_root(root, relative_path):
    return (Path(root) / relative_path).read_text(encoding="utf-8")
