import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
WAFLIB_SRC = ROOT / 'waflib' / 'waf'

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if str(WAFLIB_SRC) not in sys.path:
    sys.path.insert(0, str(WAFLIB_SRC))