"""The frozen second opinion is ../region.py (same sha256, 286305bd...); region_slim*.py import it under this name."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from region import *  # noqa: E402,F401,F403
