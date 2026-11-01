# mathbook

Static jupyter notebooks. 
- Converts `<file>.md` with fenced python code to `<file>.ipynb` and mirror generated images.
- Converts `<file>.ipynb` to `<file>.md`.

Why:
- Static clean version.
- Prevent hanging juptyer kernels for notebooks run but not actively running. Mathbooks are run and the kernel is shut down. leaving a static .md version that only requires an .md viewer.
- Prevent jupyter notebook internal .json polluting git commits.

`pip install .` adds `mathbook` bash command.


1. Write markdown file with ```python```  code fences. 
```python
# figure: <name> # fences starting with "# figure:"   or "# fold", are folded in .md
def python_code_to_run()
    ...
```

2. bash `mathbook <name>.md` or `mathbook <name>.ipynb`.  Converts `.md` <-> `.ipynb`.

```bash
mathbook <name>.md | <name>.ipynb # with optional args
# --out <path>         .ipynb dir, ["."] # `Path(<file>.md).parent/out` unless `out` is absolute
# --images <path>      images dir, ["."] # `<out>/images/<name>/` unless `images` is absolute
# --compress-fmt <fmt> compression format for high bpp (>.45) images  ["webp"] | "jpeg"
# --quality <90>       compression quality for webp and jpeg
# --no-mirror          images not mirrored into .md
# --no-run             (only .md -> .ipynb) output .ipynb without running.
# --reuse              (only .md -> .ipynb) only runs changed code
# --force              (only .ipynb -> .md). if <name>.md exists overwrite with force.
```

Example
```bash
cd examples && mathbook TheoremaEgregium.md
```

Utility: Inspect and/or shutdown jupyter kerneks
```bash
scripts/jupyter_kernels.sh                          # list jupyter kernels
scripts/jupyter_kernels.sh --stop                   # stop inactive kernels
scripts/jupyter_kernels.sh --stop -all              # stop all kernels
scripts/jupyter_kernels.sh --stop --older-than 60   # stop older than 60 min
scripts/jupyter_kernels.sh --stop --pid 1021232     # stop by pid
scripts/jupyter_kernels.sh --stop --parent code     # started by parent process
```

