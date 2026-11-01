"""xvdp

.ipynb notebook to .md with fenced python code. Inverse of `to_notebook`.

Code cells become ```python fences. Markdown and raw cells pass verbatim. Image outputs land in
``<images>/<stem>/NNN_<name>.<ext>`` and enter the document as the figure blocks `to_notebook`
writes, so ``.md -> .ipynb`` strips them on read. Text outputs stay in the notebook.

A ```python fence inside a markdown cell is retagged ```py: `split_cells` would read it as a code
cell, and figure blocks would land after the wrong fence.

    mathbook mathbooks/nyquist_check.ipynb --out ..
    mathbook nb/*.ipynb --no-mirror
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .to_notebook import FENCE, add_folds, cell_source, image_dir, insert_figures, write_images


def render_markdown(src_path,
                    out_dir: str = ".",
                    images: str = ".",
                    mirror: bool = True,
                    compress_fmt: str = "webp",
                    quality: int = 90,
                    force: bool = False):
    """Write .md from .ipynb, mirroring figures from code cell outputs.

    A notebook without figure outputs leaves the image directory untouched, so an unexecuted
    notebook does not wipe the figures of a previous run.

    Args:
        src_path: .ipynb path.
        out_dir: .md dir, relative to the notebook dir unless absolute.
        images: image dir, relative to the notebook dir unless absolute; `/<stem>` appended.
        force: overwrite an existing .md.

    Returns:
        (markdown path, code cell count, figure count).
    """
    src = Path(src_path)
    nb = json.loads(src.read_text())
    out_dir = Path(out_dir)
    if not out_dir.is_absolute():
        out_dir = src.parent.joinpath(out_dir).absolute()
    out = out_dir / f"{src.stem}.md"
    if out.exists() and not force:
        raise FileExistsError(f"{out} exists, pass force to overwrite")

    text = join_cells(nb)
    n_code = sum(1 for cell in nb.get("cells", []) if cell.get("cell_type") == "code")
    n_fig = 0
    if mirror and has_figures(nb):
        images = image_dir(images, src.parent.absolute(), src.stem)
        blocks = write_images(nb, images, compress_fmt, quality)
        n_fig = sum(len(links) for _, links in blocks)
        relative = os.path.relpath(images, out_dir).replace(os.sep, "/")
        text = insert_figures(text, blocks, relative)

    out_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(add_folds(text))
    return out, n_code, n_fig


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
    n-th code cell: the ordinal `write_images` and `insert_figures` share.
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


def has_figures(nb):
    """True when any code cell output carries a png or svg figure."""
    return any({"image/png", "image/svg+xml"} & set(output.get("data") or {})
               for cell in nb.get("cells", []) if cell.get("cell_type") == "code"
               for output in cell.get("outputs", []))
