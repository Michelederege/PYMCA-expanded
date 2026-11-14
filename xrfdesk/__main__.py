import sys

if __name__ == "__main__" and len(sys.argv) == 1:
    from xrfdesk.launch import detach_from_controlling_terminal

    detach_from_controlling_terminal()

from xrfdesk.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
