#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sponsor tracker GUI entry (PySide6). Legacy CustomTkinter UI removed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    from src.qt_app import application

    application.main()


if __name__ == "__main__":
    try:
        import multiprocessing

        multiprocessing.freeze_support()
        main()
    except Exception:
        import traceback

        print("Startup failed:")
        traceback.print_exc()
        raise SystemExit(1)
