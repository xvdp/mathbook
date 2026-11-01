"""xvdp

Static .md mirror to .ipynb notebook. Runs .ipynb and mirrors figures into .md.

Takes markdwown ```python ``` code blocks and converts them to juptyer notebook cells.

Images are named by `# figure: <name>` comment inside drawing block if found. 
Default to first .suptitle() or .set_title(), or 'figure'. All images are prefixed a number.

Python code blocks with first line tag `# figure:` are folded with html <details>

Stale images are removed.

Mirror. Images are saved to   in `docs/math/images/<stem>/NNN_<name>.png` and enter the document
inside an HTML comment pair:

    <!-- figures 3 -->
    ![003 cone geometry](../images/probe_sampling_and_speckle/003_cone_geometry.png)
    <!-- /figures -->

"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

FENCE = re.compile(r"^```[ \t]*(\w*)[ \t]*$")
FOLD_OPEN = re.compile(r"^<details class=\"mathbook-drawing\">[ \t]*$")
FOLD_SUMMARY = re.compile(r"^<summary>.*</summary>[ \t]*$")
FOLD_CLOSE = re.compile(r"^</details>[ \t]*$")
FIGURES_OPEN = re.compile(r"^<!--[ \t]*figures\b[^>]*-->[ \t]*$")
FIGURES_CLOSE = re.compile(r"^<!--[ \t]*/figures[ \t]*-->[ \t]*$")
NAME_COMMENT = re.compile(r"^[ \t]*#[ \t]*figure:[ \t]*(.+?)[ \t]*$", re.M)
TITLE_CALL = re.compile(r"(?:suptitle|set_title)\(\s*[fr]?[\"']([^\"'\n]{3,80})")


COMPRESS_ABOVE_BPP = 0.45
"""Compress images (to WEBP or JPG) abover bytes per pixel threshold.
False saves all images as PNG
True saves all images compressed
"""

def render(src_path,
           out_dir: str = ".",
           images: str = ".",
           run: bool = True,
           mirror: bool = True,
           compress_fmt="webp",
           quality: int = 90,
           reuse: bool = False):
    """Run .ipynb, then mirror figures into source .md.

    The document is rewritten only when the run completed without errors

    Returns:
        (notebook path, code cell count, figure count, failure message or None).
    """
    src = Path(src_path)
    text = strip_folds(strip_figures(src.read_text()))
    cells = split_cells(text)
    n_code = sum(1 for kind, _ in cells if kind == "code")
    nb = build_notebook(cells)
    out_dir = Path(out_dir)
    if not out_dir.is_absolute():
        out_dir = src.parent.joinpath(out_dir).absolute()

    out = out_dir / f"{src.stem}.ipynb"
    if reuse:
        err = reuse_outputs(nb, out) if n_code else None
    else:
        err = execute(nb, src.parent) if (run and n_code) else None

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(nb, indent=1))

    # overwrite .md only on sucessful run.
    n_fig = 0
    if mirror and err is None and n_code and (run or reuse):
        images = image_dir(images, out_dir, src.stem)
        blocks = write_images(nb, images, compress_fmt, quality)
        n_fig = sum(len(links) for _, links in blocks)
        relative = os.path.relpath(images, src.parent).replace(os.sep, "/")
        src.write_text(add_folds(insert_figures(text, blocks, relative)))
    return out, n_code, n_fig, err


def strip_figures(text):
    """The document with every mirrored figure block removed.

    Blocks run from `<!-- figures ... -->` to `<!-- /figures -->`.  Unmatched openers raise.
    """
    out, skipping = [], False
    for line in text.splitlines():
        if FIGURES_OPEN.match(line):
            # The blank line separating a block from the fence above belongs to the block.
            if out and not out[-1].strip():
                out.pop()
            skipping = True
            continue
        if skipping:
            if FIGURES_CLOSE.match(line):
                skipping = False
            continue
        out.append(line)
    if skipping:
        raise ValueError("unclosed figure block")
    return "\n".join(out).rstrip("\n") + "\n"


def cell_source(cell):
    """Cell's source as string. nbformat returns a line list after executing notebook ."""
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else source


def is_drawing(source):
    """Cells with first line tag `# figure:`  or `# fold` are marked for folding."""
    first = source.lstrip().split("\n", 1)[0]
    return bool(NAME_COMMENT.match(first)) or first.strip() == "# fold"


def strip_folds(text):
    """Unfold `details` blocks folded by this script.
    """
    out, depth, skip_blank = [], 0, False
    for line in text.splitlines():
        if FOLD_OPEN.match(line):
            depth += 1
            skip_blank = True
            continue
        if depth and skip_blank and not line.strip():
            skip_blank = False
            continue
        if depth and FOLD_SUMMARY.match(line):
            skip_blank = True
            continue
        if depth and FOLD_CLOSE.match(line):
            depth -= 1
            if out and not out[-1].strip():
                out.pop()
            continue
        out.append(line)
    if depth:
        raise ValueError("unclosed drawing fold")
    return "\n".join(out).rstrip("\n") + "\n"


def add_folds(text):
    """Wrap drawing cells in a collapsed `details` block.
    """
    lines, out, inside, buffer = text.splitlines(), [], False, []
    for line in lines:
        hit = FENCE.match(line)
        if hit and not inside and hit.group(1) == "python":
            inside, buffer = True, [line]
            continue
        if inside:
            buffer.append(line)
            if hit:
                body = "\n".join(buffer[1:-1])
                if is_drawing(body):
                    count = len(buffer) - 2
                    # A markdown host renders a fence inside `details` only when a blank
                    # line separates it from the tags around it.
                    out.append('<details class="mathbook-drawing">')
                    out.append(f"<summary>drawing code, {count} lines</summary>")
                    out.append("")
                    out.extend(buffer)
                    out.append("")
                    out.append("</details>")
                else:
                    out.extend(buffer)
                inside, buffer = False, []
            continue
        out.append(line)
    if inside:
        raise ValueError("unclosed python fence")
    return "\n".join(out).rstrip("\n") + "\n"


def figure_name(source):
    """The name a code cell gives its figures.

    Order: an explicit `# figure: <name>` comment, then the first plotted title, then
    `figure`. The result is a lowercase slug holding word characters and single underscores.
    """
    hit = NAME_COMMENT.search(source) or TITLE_CALL.search(source)
    raw = hit.group(1) if hit else "figure"
    slug = re.sub(r"[^\w]+", "_", raw.strip().lower()).strip("_")
    return slug[:48] or "figure"



def encode_figure(data, compress_fmt="webp", quality=90):
    """The bytes and extension one figure is stored under, chosen from its own content.

    A cell emitting `image/svg+xml` stores vector, which renders sharp at any zoom and inline
    on a markdown host. A document obtains it by setting the inline figure format in its setup
    cell, and a document that does not falls through to the raster branch below.

    A raster figure is classified by the bytes per pixel of the PNG. A rendered
    scene panel carries COMPRESS_ABOVE_BPP content that PNG stores poorly, so it re-encodes. Line art
    and the mixed band stay PNG, where they are already small and lossless.

    Returns:
        (bytes, extension).
    """
    import base64
    import struct

    if "image/svg+xml" in data:
        raw = data["image/svg+xml"]
        return ("".join(raw) if isinstance(raw, list) else raw).encode(), "svg"

    raw = data["image/png"]
    raw = base64.b64decode("".join(raw) if isinstance(raw, list) else raw)
    width, height = struct.unpack(">II", raw[16:24])
    if isinstance(COMPRESS_ABOVE_BPP, bool):
        _png = not COMPRESS_ABOVE_BPP
    else:
        _png = len(raw) / max(width * height, 1) < COMPRESS_ABOVE_BPP
    if _png:
        return raw, "png"

    import io  # noqa: PLC0415

    from PIL import Image  # noqa: PLC0415

    buffer = io.BytesIO()
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    if compress_fmt == "jpeg":
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        return buffer.getvalue(), "jpg"
    image.save(buffer, format="WEBP", quality=quality, method=6)
    return buffer.getvalue(), "webp"


def write_images(nb, image_dir, compress_fmt="webp", quality=90):
    """Write every figure the run produced, and say which cell drew each.

    Every file the run did not produce leaves the directory, so a renamed or deleted figure
    carries nothing stale forward.

    Returns:
        A list of (code cell ordinal, [(filename, alt text)]) in document order.
    """
    image_dir.mkdir(parents=True, exist_ok=True)
    written, blocks, index, ordinal = set(), [], 0, -1
    for cell in nb["cells"]:
        if cell.get("cell_type") != "code":
            continue
        ordinal += 1
        name = figure_name(cell_source(cell))
        links = []
        for output in cell.get("outputs", []):
            data = output.get("data") or {}
            if not ({"image/png", "image/svg+xml"} & set(data)):
                continue
            index += 1
            body, extension = encode_figure(data, compress_fmt, quality)
            filename = f"{index:03d}_{name}.{extension}"
            (image_dir / filename).write_bytes(body)
            written.add(filename)
            links.append((filename, f"{index:03d} {name.replace('_', ' ')}"))
        if links:
            blocks.append((ordinal, links))
    for stale in image_dir.iterdir():
        if stale.is_file() and stale.name not in written:
            stale.unlink()
    return blocks


def insert_figures(text, blocks, relative):
    """The document with a figure block after the closing fence of each cell that drew one.

    Args:
        text: the document with figure blocks already stripped.
        blocks: (code cell ordinal, [(filename, alt)]) pairs from `write_images`.
        relative: the path from the document to its image directory.
    """
    by_ordinal = dict(blocks)
    lines, out, code, ordinal = text.splitlines(), [], False, -1
    for line in lines:
        hit = FENCE.match(line)
        if hit and not code and hit.group(1) == "python":
            code = True
            ordinal += 1
        elif hit and code:
            code = False
            out.append(line)
            if ordinal in by_ordinal:
                out.append("")
                out.append(f"<!-- figures {ordinal} -->")
                for filename, alt in by_ordinal[ordinal]:
                    out.append(f"![{alt}]({relative}/{filename})")
                out.append("<!-- /figures -->")
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def split_cells(text):
    """Split markdown into (kind, source) pairs. kind is 'markdown' or 'code'.

    A fenced block tagged `python` becomes a code cell. Every other fence stays inside the
    surrounding markdown, so a ```json``` or ```bash``` block renders rather than running.
    """
    cells, buf, code, lang = [], [], None, ""
    for line in text.splitlines():
        hit = FENCE.match(line)
        if hit and code is None:
            lang = hit.group(1)
            if lang == "python":
                if any(s.strip() for s in buf):
                    cells.append(("markdown", "\n".join(buf).strip()))
                buf, code = [], []
                continue
        elif hit and code is not None:
            cells.append(("code", "\n".join(code)))
            code = None
            continue
        (code if code is not None else buf).append(line)
    if code is not None:
        raise ValueError("unclosed python fence")
    if any(s.strip() for s in buf):
        cells.append(("markdown", "\n".join(buf).strip()))
    return cells


def cell_ids(cells):
    """Deterministic nbformat 4.5 cell ids, one per (kind, source) pair.

    id = sha1(kind, source)[:8], suffixed ``-k`` on the k-th repeat of identical content. An id
    depends only on its own cell content and repeat rank, so inserting or moving other cells
    leaves it unchanged. Absent ids, nbformat validation inserts random ones on every write.
    """
    seen = {}
    for kind, src in cells:
        key = hashlib.sha1(f"{kind}\n{src}".encode()).hexdigest()[:8]
        rank = seen.get(key, 0)
        seen[key] = rank + 1
        yield key if not rank else f"{key}-{rank}"


def build_notebook(cells):
    """An nbformat v4 notebook dict from (kind, source) pairs."""
    print(f"building notebook with {len(cells)} cells")
    return {
        "cells": [
            {
                "id": cell_id,
                "cell_type": kind,
                "metadata": (
                    {"jupyter": {"source_hidden": True}}
                    if kind == "code" and is_drawing(src)
                    else {}
                ),
                # str not list: while v4 accepts both list and str, nbclient calls `.strip()`.
                "source": src,
                **({"outputs": [], "execution_count": None} if kind == "code" else {}),
            }
            for cell_id, (kind, src) in zip(cell_ids(cells), cells)
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def execute(nb, cwd):
    """Run every code cell in place. Returns None on success, else failure message str.

    Kernel follows interpreter.
    Substitutes `sys.executable`, so a .ipynb executes under invoked environment.
    """
    print("executing notebook")
    try:
        import nbformat
        from jupyter_client.kernelspec import KernelSpecManager
        from jupyter_client.manager import KernelManager
        from nbclient import NotebookClient
    except ImportError:
        return "nbclient and nbformat are absent; the notebook was written unexecuted"

    class _ThisInterpreter(KernelSpecManager):
        """Every spec launched through the interpreter running this script."""

        def get_kernel_spec(self, kernel_name):
            spec = super().get_kernel_spec(kernel_name)
            spec.argv = [sys.executable, *spec.argv[1:]]
            return spec

    node = nbformat.from_dict(nb)
    manager = KernelManager(kernel_name="python3")
    manager.kernel_spec_manager = _ThisInterpreter()
    cell_timeout = int(os.environ.get("MATHBOOK_CELL_TIMEOUT", "600"))
    client = NotebookClient(node, km=manager, timeout=cell_timeout,
                            resources={"metadata":{"path": str(cwd)}})

    # Watchdog culls zombie kernels cells killed by backend abort.
    state = {"cell": "startup"}

    def on_cell_start(cell=None, cell_index=None, **_):
        state["cell"] = cell_index

    client.on_cell_start = on_cell_start
    try:
        from .watchdog import undertaker

        guard = undertaker(manager.is_alive,
                           lambda: f"jupyter kernel cell {state['cell']} of {len(node.cells)}")
    except ImportError:
        import contextlib  # noqa: PLC0415

        guard = contextlib.nullcontext()
    try:
        with guard:
            # nbclient shuts down only kernels it owns; a caller-supplied `km` stays alive
            # unless `cleanup_kc`. Cleanup runs on success and on cell errors alike: kernel
            # shutdown, connection file removal, client zmq channels closed.
            client.execute(cleanup_kc=True)
    except Exception as exc:  # nbclient raises CellExecutionError and kernel errors alike
        return f"{type(exc).__name__}: {exc}"
    finally:
        # Interrupts that bypass nbclient cleanup.
        if manager.has_kernel:
            manager.shutdown_kernel(now=True)
    nb.clear()
    nb.update(json.loads(nbformat.writes(node)))
    return None


def image_dir(images, notebook_dir, notebook_name):
    """Image directory of document `notebook_name`: `images` resolved against `notebook_dir`, then `/<notebook_name>`.

    `images` None resolves to `notebook_dir`. A path already ending in `notebook_name` takes no suffix.
    """
    images = Path(images or ".")
    if not images.is_absolute():
        images = notebook_dir.joinpath(images)
    return images if images.stem == notebook_name else images / notebook_name


def reuse_outputs(nb, path):
    """ Copy outputs of a stored notebook when there are no changes to code.

    Returns:
        None when notebook has been copied, else reason.
    """
    stored_path = Path(path)
    if not stored_path.exists():
        return "no stored notebook"
    stored = json.loads(stored_path.read_text())
    fresh = [c for c in nb["cells"] if c["cell_type"] == "code"]
    held = [c for c in stored.get("cells", []) if c["cell_type"] == "code"]
    if len(fresh) != len(held):
        return f"{len(held)} stored code cells against {len(fresh)} in the document"
    for index, (new_cell, old_cell) in enumerate(zip(fresh, held, strict=True), 1):
        if cell_source(new_cell).strip() != cell_source(old_cell).strip():
            return f"code cell {index} differs from the stored notebook"
    executed = 0
    for new_cell, old_cell in zip(fresh, held, strict=True):
        new_cell["outputs"] = old_cell.get("outputs", [])
        new_cell["execution_count"] = old_cell.get("execution_count")
        executed += bool(old_cell.get("execution_count"))
    if not executed:
        return "the stored notebook has no runnable data"
    return None
