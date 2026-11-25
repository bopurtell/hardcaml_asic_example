"""Explicit imports for checkout and independently captured Workbench helpers."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for directory in ('scripts', 'tooling_acceptance/workloads/support'):
    sys.path.insert(0, str(ROOT / directory))
