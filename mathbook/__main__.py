"""Mirror .md <-> .ipynb. Direction follows each file's suffix.

    <file>.md     -> <out>/<file>.ipynb, run, figures mirrored into <file>.md
    <file>.ipynb  -> <out>/<file>.md, figures from stored outputs

    mathbook docs/math/nyquist_check.md
    mathbook docs/math/*.md --out mathbooks
    mathbook docs/math/nyquist_check.md --no-run
    mathbook docs/math/nyquist_check.md --no-mirror
    mathbook mathbooks/nyquist_check.ipynb --out ..
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path

from .to_markdown import render_markdown
from .to_notebook import render


def make_mathbook(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docs", nargs="+", help=".md math documents or .ipynb notebooks")
    ap.add_argument("--out", default=".", help="output dir, relative path -> [source dir/<>]")
    ap.add_argument("--no-run", action="store_true", help=".md: write ipynb without executing")
    ap.add_argument("--no-mirror", action="store_true", help="do not mirror imgs into .md")
    ap.add_argument("--reuse", action="store_true", help=".md: do not run if .md cells match")
    ap.add_argument("--force", action="store_true", help=".ipynb: overwrite existing .md")
    ap.add_argument("--images", default="images", help="image dir, relative path -> ipynb dir/<>")
    ap.add_argument("--compress-fmt", default="webp", choices=("webp", "jpeg"), help="compressed format")
    ap.add_argument("--quality", type=int, default=90, help="compress-fmt qualtiy")
    args = ap.parse_args(argv)

    failed = 0
    for doc in args.docs:
        suffix = Path(doc).suffix.lower()
        if suffix == ".md":
            failed += _to_notebook(doc, args)
        elif suffix == ".ipynb":
            failed += _to_markdown(doc, args)
        else:
            print(f"{doc}: expected .md or .ipynb", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


def _to_notebook(doc, args):
    """.md -> .ipynb. Returns 1 on failure, else 0."""
    out, n_code, n_fig, err = render(doc, args.out, run=not args.no_run, mirror=not args.no_mirror,
                                     images=args.images, compress_fmt=args.compress_fmt,
                                     quality=args.quality, reuse=args.reuse)
    if args.reuse:
        state = "mirrored" if err is None else f"needs a run: {err}"
    else:
        state = "not run" if args.no_run else ("ok" if err is None else "FAILED")
    print(f"{doc} -> {out}  ({n_code} code cells, {n_fig} figures, {state})")
    if err and not args.reuse:
        print(f"  {err}", file=sys.stderr)
        return 1
    return 0


def _to_markdown(doc, args):
    """.ipynb -> .md. Returns 1 on failure, else 0."""
    try:
        out, n_code, n_fig = render_markdown(doc, args.out, mirror=not args.no_mirror,
                                             images=args.images, compress_fmt=args.compress_fmt,
                                             quality=args.quality, force=args.force)
    except (FileExistsError, ValueError) as exc:  # ValueError: malformed json
        print(f"{doc}: {exc}", file=sys.stderr)
        return 1
    print(f"{doc} -> {out}  ({n_code} code cells, {n_fig} figures)")
    return 0
