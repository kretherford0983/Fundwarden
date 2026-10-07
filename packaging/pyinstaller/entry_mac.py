"""PyInstaller entry point for PennyWarden.app (macOS, 1.6.7): local mode behind a small status window."""
import multiprocessing
import sys

from fmpoc.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    args = [a for a in sys.argv[1:] if not a.startswith("-psn_")]  # Finder's process serial number on old macOS
    sys.exit(main(args, window=True))
