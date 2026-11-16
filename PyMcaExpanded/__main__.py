import sys

if __name__ == "__main__" and len(sys.argv) == 1:
    from PyMcaExpanded.launch import detach_from_controlling_terminal

    detach_from_controlling_terminal()

from PyMcaExpanded.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
