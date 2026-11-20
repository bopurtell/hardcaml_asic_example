#!/usr/bin/env python3
"""Launch Silver on this checkout."""
import sys

sys.dont_write_bytecode = True
from workbench_main import cli


if __name__ == '__main__':
    sys.exit(cli('silver'))
