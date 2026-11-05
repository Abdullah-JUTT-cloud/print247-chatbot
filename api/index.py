import os
import sys
from pathlib import Path

# Add project root to sys.path so 'app' and all modules can be imported
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Ensure current working directory is root so kb/ and relative file paths work
try:
    os.chdir(str(ROOT_DIR))
except Exception:
    pass

from app.main import app
