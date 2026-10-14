"""PyInstaller entry point for the bundled core sidecar."""

import sys

from huntly.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
