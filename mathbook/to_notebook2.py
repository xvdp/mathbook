"""xvdp

Static .md mirror to .ipynb notebook. Runs .ipynb and mirrors cell outputs into .md.
Executes markdwown ```python ``` code blocks in juptyer notebook cells.

Images are written with name: f"{Path(file).stem}/{i:003d}{name}", where name defaults to:
1.`# figure: <name>` comment in first code line 2. .suptitle() 3. .set_title(), 4. 'figure'.
Stale images are removed.

Python code blocks with first line tag `# figure:` or `# fold` are folded with html <details>

Cell outputs: (images, tables, print() __repr__) are mirrored into .md and fenced

<!-- outputs {i:003d{} -->
    <samp>short&nbsp;stdout&nbsp;or&nbsp;text/plain<br>
    second&nbsp;line</samp>

    <details class="mathbook-output">
    <summary>{class.__repr__()}</summary>

    ```text
    long text, stderr, tracebacks
    ```
    </details>

    ![{i:003d}{img_name}](../images/{file_name}.stem/{i:003d}_{img_name}.png)

    <table> text/html </table>
 <!-- /outputs -->
 
    Short text outputs render as `<samp>` lines.
    Text outputs longer than `clip_long` lines keep head and tail.
    Text oututs longer than `fold_long` lines fold in `<details>`
    stderr and tracebacks always fold, summarized in one line. Folded text is fenced.

    strip_outputs() drops these  and `<!-- figures N -->` blocks, on read.

Failed notebook run keeps <stem>.ipynb, <stem>.md, images from last good run, and writes
<stem>_partial.ipynb with outputs up to and including the failing cell.
    The next successful run deletes <stem>_partial.ipynb.

`run=False` writes <stem>.ipynb only when none exists.

`validate=True`, writes parallel <stem>.validate. set {.md, .ipynb, image dir}.
Originals stay untouched, and the parallel set holds outputs up to and including a failing
    The next successful run deletes <stem>.validate.{} set.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import sys
from pathlib import Path

FENCE = re.compile(r"^```[ \t]*(\w*)[ \t]*$")
FOLD_OPEN = re.compile(r"^<details class=\"mathbook-drawing\">[ \t]*$")
FOLD_SUMMARY = re.compile(r"^<summary>.*</summary>[ \t]*$")
FOLD_CLOSE = re.compile(r"^</details>[ \t]*$")
OUTPUTS_OPEN = re.compile(r"^<!--[ \t]*(?:outputs|figures)\b[^>]*-->[ \t]*$")
OUTPUTS_CLOSE = re.compile(r"^<!--[ \t]*/(?:outputs|figures)[ \t]*-->[ \t]*$")
NAME_COMMENT = re.compile(r"^[ \t]*#[ \t]*figure:[ \t]*(.+?)[ \t]*$", re.M)
TITLE_CALL = re.compile(r"(?:suptitle|set_title)\(\s*[fr]?[\"']([^\"'\n]{3,80})")
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
STYLE = re.compile(r"<style\b[^>]*>.*?</style>[ \t]*\n?", re.S | re.I)
SCRIPT = re.compile(r"<script\b", re.I)
ALERT = re.compile(r"\b\w*(?:Error|Warning|Exception):.*")
SAMP_INLINE = re.compile(r"[\\`*_\[\]~|]")
SAMP_SPACES = re.compile(r"^ +| {2,}")
SAMP_BLOCK = re.compile(r"(?:[#>+=-]|\d+[.)])")
KERNEL_FILE = re.compile(r"(?:[A-Za-z]:)?[^\s\"'():]*ipykernel_\d+[/\\]\d+\.py")
"""Temporary file ipykernel compiles each cell to: `<tmp>/ipykernel_<pid>/<hash>.py`."""
VALIDATE = ".validate"
"""Stem suffix of the parallel set a validation run writes."""
PARTIAL = "_partial"
"""Stem suffix of the notebook a failed run writes beside the last good one."""

IMAGE_MIMES = ("image/svg+xml", "image/png", "image/jpeg")
MIME_PRIORITY = (*IMAGE_MIMES, "text/markdown", "text/latex", "text/html", "text/plain")
"""Display outputs render their first carried MIME type. text/html holding <script> is skipped:
markdown hosts run no javascript."""
TRACEBACK_TAIL = 20
"""Traceback lines kept, counted from the end."""
SUMMARY_CHARS = 120
"""Fold summary length limit."""


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
           reuse: bool = False,
           clip_long: int = 100,
           fold_long: int = 20,
           validate: bool = False):
    """Run .ipynb, then mirror cell outputs into source .md.

    <stem>.md  is rewritten only when the run completed without errors.
    Failed completions write `<stem>_partial.ipynb` w/o touching `<stem>.ipynb` and `<stem>.md`
    Successful completion deletes previous failure and validate runs.

    Args:
        reuse:     only run changed code cells.
        clip_long: text outputs above this many lines keep head and tail. 0 keeps all.
        fold_long: text outputs above this many lines fold. 0 folds none.
        validate: create parallel `<stem>.validate` .md, .ipynb and image di.

    Returns:
        (notebook path, code cell count, figure count, failure message or None).
    """
    src = Path(src_path)
    text = strip_folds(strip_outputs(src.read_text()))
    cells = split_cells(text)
    n_code = sum(1 for kind, _ in cells if kind == "code")
    nb = build_notebook(cells)
    out_dir = Path(out_dir)
    if not out_dir.is_absolute():
        out_dir = src.parent.joinpath(out_dir).absolute()

    stem = src.stem + VALIDATE if validate else src.stem
    out = out_dir / f"{stem}.ipynb"
    if validate:
        run, reuse = True, False
    executed = run and not reuse and n_code
    if reuse:
        err = reuse_outputs(nb, out) if n_code else None
    else:
        err = execute(nb, src.parent, keep_partial=True) if executed else None

    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out_dir / f"{src.stem}{PARTIAL}.ipynb"
    if err is not None and executed and not validate:
        partial.write_text(json.dumps(nb, indent=1))
        err = f"{err}\n{failure_note(nb, err, partial, out)}"
        return partial, n_code, 0, err
    if err is None or validate:
        if run or reuse or not out.exists():
            out.write_text(json.dumps(nb, indent=1))
        else:
            print(f"kept existing {out}: --no-run writes a notebook only when none exists")

    # overwrite .md only on sucessful run; a validation set records failures too.
    n_fig = 0
    if mirror and (err is None or validate) and n_code and (run or reuse):
        image_path = image_dir(images, out_dir, stem)
        relative = os.path.relpath(image_path, src.parent).replace(os.sep, "/")
        blocks, n_fig = write_outputs(nb, image_path, relative, compress_fmt, quality,
                                      clip_long, fold_long)
        src.with_name(f"{stem}.md").write_text(add_folds(insert_outputs(text, blocks)))
        if not validate:
            remove_validation(src.stem, src.parent, out_dir, images)
            partial.unlink(missing_ok=True)
    return out, n_code, n_fig, err


def failure_note(nb, err, partial, previous):
    """Banner closing a failed-run message: failing code cell, reason, both notebook paths.

    The failing cell is the first code cell with an error output, else the first unexecuted one
    (a timeout or a dead kernel leaves no error output).
    """
    code = [cell for cell in nb["cells"] if cell.get("cell_type") == "code"]
    failing = next((i for i, cell in enumerate(code)
                    if any(o.get("output_type") == "error" for o in cell.get("outputs", []))), None)
    if failing is None:
        failing = next((i for i, cell in enumerate(code) if not cell.get("execution_count")),
                       len(code) - 1)
    errors = [o for o in code[failing].get("outputs", []) if o.get("output_type") == "error"]
    reason = (f"{errors[0].get('ename')}: {errors[0].get('evalue')}" if errors
              else err.strip().split("\n", 1)[0])
    first = next((line.strip() for line in cell_source(code[failing]).split("\n") if line.strip()), "")
    rule = "!" * 72
    lines = [rule,
             f"!!! NOTEBOOK FAILED at code cell {failing + 1} of {len(code)}: {reason}"[:200],
             f"!!!   cell starts:  {first}"[:200],
             f"!!!   failed run:   {partial}"]
    if previous.exists():
        lines += [f"!!!   last good run: {previous}  (unchanged)",
                  f"!!!   compare {partial.name} with {previous.name}"]
    else:
        lines.append("!!!   last good run: none")
    return "\n".join([*lines, rule])


def remove_validation(stem, md_dir, notebook_dir, images):
    """Delete the parallel `<stem>.validate` .md, .ipynb and image dir. Returns removed paths."""
    stem = stem + VALIDATE
    removed = []
    for path in (Path(md_dir) / f"{stem}.md", Path(notebook_dir) / f"{stem}.ipynb"):
        if path.is_file():
            path.unlink()
            removed.append(path)
    folder = image_dir(images, Path(notebook_dir), stem)
    if folder.is_dir() and folder.name == stem:
        shutil.rmtree(folder)
        removed.append(folder)
    return removed


def strip_outputs(text):
    """The document with every mirrored output block removed.

    Blocks run from `<!-- outputs ... -->` to `<!-- /outputs -->`, or the legacy `figures` pair.
    Unmatched openers raise.
    """
    out, skipping = [], False
    for line in text.splitlines():
        if OUTPUTS_OPEN.match(line):
            # The blank line separating a block from the fence above belongs to the block.
            if out and not out[-1].strip():
                out.pop()
            skipping = True
            continue
        if skipping:
            if OUTPUTS_CLOSE.match(line):
                skipping = False
            continue
        out.append(line)
    if skipping:
        raise ValueError("unclosed output block")
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

    Output blocks pass verbatim: a ```python line inside an output is not a cell.
    """
    lines, out, inside, buffer, block = text.splitlines(), [], False, [], False
    for line in lines:
        if not inside and (block or OUTPUTS_OPEN.match(line)):
            block = not OUTPUTS_CLOSE.match(line)
            out.append(line)
            continue
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

    if "image/png" not in data:  # jpeg: already lossy, stored as is
        return base64.b64decode(joined(data["image/jpeg"])), "jpg"

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


def joined(raw):
    """nbformat multiline string, list or str, as str."""
    return "".join(raw) if isinstance(raw, list) else raw


def display_text(raw):
    """Text as a Jupyter frontend displays it.

    ANSI escapes removed. A carriage return overwrites its line: each line keeps the segment after
    its last nonempty `\\r` split, which leaves a progress bar at its final state. The per-run
    temporary path of a cell, `<tmp>/ipykernel_<pid>/<hash>.py`, reads `<cell>`.
    """
    text = KERNEL_FILE.sub("<cell>", ANSI.sub("", joined(raw))).replace("\r\n", "\n")
    lines = []
    for line in text.split("\n"):
        segments = [s for s in line.split("\r") if s]
        lines.append(segments[-1] if segments else "")
    return "\n".join(lines).strip("\n")


def merged_streams(outputs):
    """Outputs with consecutive stream outputs of one name joined, as Jupyter displays them."""
    merged = []
    for output in outputs:
        last = merged[-1] if merged else {}
        if (output.get("output_type") == "stream" and last.get("output_type") == "stream"
                and last.get("name") == output.get("name")):
            merged[-1] = {**last, "text": joined(last["text"]) + joined(output["text"])}
        else:
            merged.append(output)
    return merged


def pick_mime(data):
    """First MIME_PRIORITY type in `data`; text/html holding <script> is skipped. None if none."""
    for mime in MIME_PRIORITY:
        if mime in data and not (mime == "text/html" and SCRIPT.search(joined(data[mime]))):
            return mime
    return None


def stderr_summary(text):
    """One line naming stderr: its first `<Name>Error|Warning|Exception: ...` line, else its last
    nonblank line, with `(+k)` counting further alerts."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    alerts = [hit.group(0) for line in lines if (hit := ALERT.search(line))]
    head = alerts[0] if alerts else (lines[-1] if lines else "")
    more = f" (+{len(alerts) - 1})" if len(alerts) > 1 else ""
    return f"stderr: {head}"[:SUMMARY_CHARS] + more


def last_code_line(source):
    """Last line of a cell that is neither blank nor a comment, stripped; '' if none."""
    for line in reversed(source.split("\n")):
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return ""


def text_block(text, clip_long=100, fold_long=20, summary=None, cause=""):
    """Markdown lines of one text output.

    Fenced ```text, the fence one backtick longer than the longest backtick run in `text`
    (CommonMark: a closing fence needs at least the opener's length). Above `clip_long` lines the
    middle is replaced by a count. Given a `summary` it folds under it; above `fold_long` lines it
    folds under `cause`, the cell line that produced it.
    """
    lines = text.split("\n")
    n = len(lines)
    if clip_long and n > clip_long:
        head = clip_long // 2
        lines = [*lines[:head], f"... {n - clip_long} lines clipped ...",
                 *lines[n - (clip_long - head):]]
    if summary is None and not (fold_long and n > fold_long):
        return samp_block(lines)
    ticks = "`" * max(3, 1 + max(map(len, re.findall(r"`+", text)), default=0))
    fenced = [f"{ticks}text", *lines, ticks]
    summary = (summary or cause or f"output, {n} lines")[:SUMMARY_CHARS]
    # A markdown host renders a fence inside `details` only when blank lines separate it.
    return ['<details class="mathbook-output">', f"<summary>{html.escape(summary)}</summary>",
            "", *fenced, "", "</details>"]


def samp_block(lines):
    """Markdown lines of one unfolded text output: `<samp>` lines joined by `<br>`.

    The lines form one markdown paragraph, so they render on the page background in monospace.
    Characters markdown would format become HTML entities: `& < >`, inline markup
    ``\\ ` * _ [ ] ~ |``, a line-leading block marker (`# > + = -`, `1.`), and every leading
    space or space run, kept as `&nbsp;` so columns stay aligned. An empty line is a bare `<br>`,
    which keeps the paragraph whole.
    """
    out = []
    for line in lines:
        line = html.escape(line, quote=False)
        line = SAMP_INLINE.sub(lambda hit: f"&#{ord(hit.group())};", line)
        line = SAMP_SPACES.sub(lambda hit: "&nbsp;" * len(hit.group()), line)
        if SAMP_BLOCK.match(line):
            line = f"&#{ord(line[0])};{line[1:]}"
        out.append(line)
    return [f"<samp>{line}" if not i else line for i, line in enumerate(
        [line + "<br>" for line in out[:-1]] + [out[-1] + "</samp>"])]


def html_block(raw):
    """Markdown lines of one text/html output: <style> elements and blank lines removed.

    A blank line ends a markdown HTML block, and the indented lines after it would render as code.
    """
    return [line for line in STYLE.sub("", joined(raw)).split("\n") if line.strip()]


def write_outputs(nb, image_dir, relative, compress_fmt="webp", quality=90,
                  clip_long=100, fold_long=20):
    """Render every code cell output to markdown lines; write every figure to `image_dir`.

    Every file the run did not produce leaves the directory, so a renamed or deleted figure
    carries nothing stale forward. The directory is created on the first figure.

    Args:
        relative: the path from the document to `image_dir`.

    Returns:
        ([(code cell ordinal, [markdown lines per output])] in document order, figure count).
    """
    written, blocks, index, ordinal = set(), [], 0, -1
    for cell in nb["cells"]:
        if cell.get("cell_type") != "code":
            continue
        ordinal += 1
        name = figure_name(cell_source(cell))
        cause = last_code_line(cell_source(cell))
        parts = []
        for output in merged_streams(cell.get("outputs", [])):
            kind = output.get("output_type")
            if kind == "stream":
                text = display_text(output.get("text", ""))
                if text.strip():
                    summary = stderr_summary(text) if output.get("name") == "stderr" else None
                    parts.append(text_block(text, clip_long, fold_long, summary, cause))
                continue
            if kind == "error":
                trace = display_text("\n".join(output.get("traceback", [])))
                trace = "\n".join(trace.split("\n")[-TRACEBACK_TAIL:])
                summary = f"{output.get('ename', 'Error')}: {output.get('evalue', '')}"
                parts.append(text_block(trace, 0, fold_long, summary[:SUMMARY_CHARS]))
                continue
            data = output.get("data") or {}
            mime = pick_mime(data)
            if mime in IMAGE_MIMES:
                index += 1
                body, extension = encode_figure(data, compress_fmt, quality)
                filename = f"{index:03d}_{name}.{extension}"
                image_dir.mkdir(parents=True, exist_ok=True)
                (image_dir / filename).write_bytes(body)
                written.add(filename)
                parts.append([f"![{index:03d} {name.replace('_', ' ')}]({relative}/{filename})"])
            elif mime == "text/plain":
                text = display_text(data[mime])
                if text.strip():
                    parts.append(text_block(text, clip_long, fold_long, cause=cause))
            elif mime == "text/html":
                parts.append(html_block(data[mime]))
            elif mime:  # text/markdown, text/latex: the host renders them
                parts.append(joined(data[mime]).strip("\n").split("\n"))
        if parts:
            blocks.append((ordinal, parts))
    if image_dir.is_dir():
        for stale in image_dir.iterdir():
            if stale.is_file() and stale.name not in written:
                stale.unlink()
    return blocks, index


def insert_outputs(text, blocks):
    """The document with an output block after the closing fence of each cell with outputs.

    Args:
        text: the document with output blocks already stripped.
        blocks: (code cell ordinal, [markdown lines per output]) pairs from `write_outputs`.
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
                out.append(f"<!-- outputs {ordinal} -->")
                for part in by_ordinal[ordinal]:
                    out.extend(part)
                    out.append("")
                out.append("<!-- /outputs -->")
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


def execute(nb, cwd, keep_partial=False):
    """Run every code cell in place. Returns None on success, else failure message str.

    On failure `nb` stays as given, unless `keep_partial`: then it holds the outputs up to and
    including the failing cell.

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
        err = None
    except Exception as exc:  # nbclient raises CellExecutionError and kernel errors alike
        err = ANSI.sub("", f"{type(exc).__name__}: {exc}")
    finally:
        # Interrupts that bypass nbclient cleanup.
        if manager.has_kernel:
            manager.shutdown_kernel(now=True)
    if err is None or keep_partial:
        nb.clear()
        nb.update(json.loads(nbformat.writes(node)))
    return err


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
