"""xvdp

.ipynb notebook to .md with fenced python code. Inverse of `to_notebook2`.

Code cells become ```python fences. Markdown and raw cells pass verbatim. Cell outputs enter
the document as the output blocks `to_notebook2` writes, so ``.md -> .ipynb`` strips them on read.
Image outputs land in ``<images>/<stem>/NNN_<name>.<ext>``.

Validation re-executes the notebook into a parallel `<stem>.validate` .ipynb, .md and image dir,
outputs cleared first so a cell after a failure shows nothing stale. A later conversion without
`validate` deletes the set.

A ```python fence inside a markdown cell is retagged ```py: `split_cells` would read it as a code
cell, and output blocks would land after the wrong fence.

    mathbook mathbooks/nyquist_check.ipynb --out ..
    mathbook nb/*.ipynb --no-mirror
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .to_notebook2 import (FENCE, VALIDATE, add_folds, cell_source, execute, exists_note,
                           image_dir, insert_outputs, remove_validation, write_outputs)


def render_markdown(src_path,
                    out_dir: str = ".",
                    images: str = ".",
                    mirror: bool = True,
                    compress_fmt: str = "webp",
                    quality: int = 90,
                    force: bool = False,
                    clip_long: int = 100,
                    fold_long: int = 20,
                    validate: bool = False):
    """Write .md from .ipynb, mirroring code cell outputs.

    A notebook without outputs leaves the image directory untouched, so an unexecuted
    notebook does not wipe the figures of a previous run.

    Args:
        src_path: .ipynb path.
        out_dir: .md dir, relative to the notebook dir unless absolute.
        images: image dir, relative to the notebook dir unless absolute; `/<stem>` appended.
        force: overwrite an existing .md.
        clip_long: text outputs above this many lines keep head and tail. 0 keeps all.
        fold_long: text outputs above this many lines fold. 0 folds none.
        validate: re-execute into `<stem>.validate` .ipynb, .md and image dir, failing or not.

    Returns:
        (markdown path, code cell count, figure count, failure message or None).
    """
    src = Path(src_path)
    nb = json.loads(src.read_text())
    out_dir = Path(out_dir)
    if not out_dir.is_absolute():
        out_dir = src.parent.joinpath(out_dir).absolute()
    stem = src.stem + VALIDATE if validate else src.stem
    out = out_dir / f"{stem}.md"
    if out.exists() and not (force or validate):
        raise FileExistsError(exists_note(out, src.stem))

    err = None
    if validate:
        for cell in nb.get("cells", []):
            # str not list: nbclient calls `.strip()`; Jupyter stores line lists.
            cell["source"] = cell_source(cell)
            if cell.get("cell_type") == "code":
                cell["outputs"], cell["execution_count"] = [], None
        err = execute(nb, src.parent, keep_partial=True)
        src.with_name(f"{stem}.ipynb").write_text(json.dumps(nb, indent=1))

    text = join_cells(nb)
    n_code = sum(1 for cell in nb.get("cells", []) if cell.get("cell_type") == "code")
    n_fig = 0
    if mirror and has_outputs(nb):
        image_path = image_dir(images, src.parent.absolute(), stem)
        relative = os.path.relpath(image_path, out_dir).replace(os.sep, "/")
        blocks, n_fig = write_outputs(nb, image_path, relative, compress_fmt, quality,
                                      clip_long, fold_long)
        text = insert_outputs(text, blocks)

    out_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(add_folds(text))
    if not validate:
        remove_validation(src.stem, out_dir, src.parent.absolute(), images)
    return out, n_code, n_fig, err


def retag_python_fences(text):
    """`text` with each ```python fence opener retagged ```py."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        hit = FENCE.match(line)
        if hit and hit.group(1) == "python":
            lines[i] = "```py"
    return "\n".join(lines)


def join_cells(nb):
    """Markdown text from notebook cells, one blank line between cells.

    Every code cell, empty ones included, becomes one ```python fence, so the n-th fence is the
    n-th code cell: the ordinal `write_outputs` and `insert_outputs` share.
    """
    parts = []
    for cell in nb.get("cells", []):
        src = cell_source(cell)
        if cell.get("cell_type") == "code":
            # verbatim: `split_cells` keeps blank lines inside a fence
            parts.append(f"```python\n{src}\n```")
            continue
        src = src.strip("\n")
        if src.strip():
            parts.append(retag_python_fences(src) if cell.get("cell_type") == "markdown" else src)
    return "\n\n".join(parts) + "\n"


def has_outputs(nb):
    """True when any code cell holds an output."""
    return any(cell.get("outputs") for cell in nb.get("cells", []) if cell.get("cell_type") == "code")
