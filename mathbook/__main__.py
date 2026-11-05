"""Mirror .md <-> .ipynb. Direction follows each file's suffix.

    <file>.md     -> <out>/<file>.ipynb, run, figures mirrored into <file>.md
    <file>.ipynb  -> <out>/<file>.md, figures from stored outputs

"""

from __future__ import annotations

import sys
import os
import argparse
from pathlib import Path

from . import to_markdown2, to_notebook2

def make_mathbook2(argv=None):
    """`make_mathbook` mirroring every cell output: stdout, stderr, display data, tracebacks."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docs", nargs="+", help=".md math documents or .ipynb notebooks")
    ap.add_argument("--out", default=".", help="output dir, relative path -> [source dir/<>]")
    ap.add_argument("--images", default=".", help="image dir, relative path -> ipynb dir/<>")
    ap.add_argument("--no-run", action="store_true", help=".md: write ipynb without executing")
    ap.add_argument("--no-mirror", action="store_true", help="do not mirror outputs into .md")
    ap.add_argument("--reuse", action="store_true", help=".md: do not run if .md cells match")
    ap.add_argument("--force", action="store_true", help="overwrite the existing opposite file: .md -> .ipynb, .ipynb -> .md")
    ap.add_argument("--compress-fmt", default="webp", choices=("webp", "jpeg"), help="compressed format")
    ap.add_argument("--quality", type=int, default=90, help="compress-fmt qualtiy")
    ap.add_argument("--clip-long", "--clip_long", type=int, default=100, help="text outputs above N lines keep head and tail, 0: no clip")
    ap.add_argument("--fold-long", "--fold_long", type=int, default=20, help="text outputs above N lines fold, 0: no fold")
    ap.add_argument("--validate", action="store_true", help="run into a parallel <stem>.validate set, originals untouched; \
                    \na later run without it updates originals and deletes the set")
    args = ap.parse_args(argv)
    if args.validate and (args.reuse or args.no_run):
        ap.error("--validate runs the notebook: drop --reuse and --no-run")

    failed = 0
    for i, doc in enumerate(args.docs):
        suffix = Path(doc).suffix.lower()
        try:
            if Path(doc).stem.endswith(to_notebook2.VALIDATE):
                print(f"{doc}: validation output, skipped")
            elif suffix == ".ipynb" and Path(doc).stem.endswith(to_notebook2.PARTIAL):
                print(f"{doc}: failed-run notebook, skipped")
            elif suffix == ".md":
                failed += _to_notebook2(doc, args)
            elif suffix == ".ipynb":
                failed += _to_markdown2(doc, args)
            else:
                print(f"{doc}: expected .md or .ipynb", file=sys.stderr)
                failed += 1
        except KeyboardInterrupt:
            skipped = len(args.docs) - i - 1
            print(f"interrupted{f', {skipped} remaining skipped' if skipped else ''}",
                  file=sys.stderr)
            return 130  # 128 + SIGINT
    return 1 if failed else 0


def _to_notebook2(doc, args):
    """.md -> .ipynb. Returns 1 on failure, else 0."""
    try:
        out, n_code, n_fig, err = to_notebook2.render(
            doc, args.out, images=args.images, run=not args.no_run, mirror=not args.no_mirror,
            compress_fmt=args.compress_fmt, quality=args.quality, reuse=args.reuse,
            clip_long=args.clip_long, fold_long=args.fold_long, validate=args.validate,
            force=args.force)
    except FileExistsError as exc:
        print(f"{doc}: {exc}", file=sys.stderr)
        return 1
    if args.reuse:
        state = "mirrored" if err is None else f"needs a run: {err}"
    elif args.validate:
        state = "validated" if err is None else "FAILED validation"
    else:
        state = "not run" if args.no_run else ("ok" if err is None else "FAILED")
    # flush: the failure note on stderr closes the report
    print(f"{doc} -> {out}  ({n_code} code cells, {n_fig} figures, {state})", flush=True)
    if err and not args.reuse:
        print(f"  {err}", file=sys.stderr)
        if err.startswith(to_notebook2.INTERRUPTED):
            raise KeyboardInterrupt
        return 1
    return 0


def _to_markdown2(doc, args):
    """.ipynb -> .md. Returns 1 on failure, else 0."""
    try:
        out, n_code, n_fig, err = to_markdown2.render_markdown(
            doc, args.out, images=args.images, mirror=not args.no_mirror,
            compress_fmt=args.compress_fmt, quality=args.quality, force=args.force,
            clip_long=args.clip_long, fold_long=args.fold_long, validate=args.validate)
    except (FileExistsError, ValueError) as exc:  # ValueError: malformed json
        print(f"{doc}: {exc}", file=sys.stderr)
        return 1
    state = ("validated" if err is None else "FAILED validation") if args.validate else "ok"
    print(f"{doc} -> {out}  ({n_code} code cells, {n_fig} figures, {state})", flush=True)
    if err:
        print(f"  {err}", file=sys.stderr)
        if err.startswith(to_notebook2.INTERRUPTED):
            raise KeyboardInterrupt
        return 1
    return 0

def jupyter_kernels(argv=None):
    script = Path(__file__).with_name("jupyter_kernels.sh")
    os.execvp("bash", ["bash", str(script), *(sys.argv[1:] if argv is None else argv)])
