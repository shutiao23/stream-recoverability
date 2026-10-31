#!/usr/bin/env python3
"""Refresh current research documents and run the scientific checks."""

from __future__ import annotations
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(["make", "review-report"], cwd=root, check=True)
    subprocess.run(["make", "review-test"], cwd=root, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
