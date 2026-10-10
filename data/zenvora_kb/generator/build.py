# -*- coding: utf-8 -*-
"""Rebuild the whole Zenvora dataset: python3 build.py  (needs pandoc-free tools: wkhtmltopdf, python-markdown)."""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_docs
import build_data
from common import OUT


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    build_docs.build_all()
    n = build_data.build_all()
    gen = os.path.join(OUT, "generator")
    os.makedirs(gen, exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    for fn in os.listdir(here):
        if fn.endswith(".py"):
            shutil.copy(os.path.join(here, fn), os.path.join(gen, fn))
    print(f"built; {n} eval questions")


if __name__ == "__main__":
    main()
