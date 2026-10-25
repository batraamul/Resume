#!/usr/bin/env python3
"""Launch Resume Intelligence Studio.

    python run_application.py              # open the desktop application
    python run_application.py --sample     # open the fictional sample workspace
    python run_application.py --selftest   # check the installation
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if sys.version_info < (3, 11):
    sys.stderr.write("Resume Intelligence Studio needs Python 3.11 or newer.\n")
    sys.exit(1)

from ris.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
