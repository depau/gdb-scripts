import sys
from pathlib import Path

LIB_DIR = Path(__file__).parent
sys.path.insert(0, str(LIB_DIR))

# noinspection PyUnresolvedReferences
from _commons_lib.all import *
