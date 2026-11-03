# mathbook .ipynb $\leftrightarrow$ .md

Linux bash jupyter notebook management.

1. `jupyter mathbook <file.{md, ipynb}>`: bidirectional conversion of .ipynb to static mirror .md
2. `jupyter kernels [args]`: list or stop hanging kernels (not to be confused with `jupyter kernel` which starts a new kernel).


### 1. `jupyter mathbook <file>.<md|ipynb>`

Static jupyter notebooks. Built to prevent hanging kernels and avoid .ipynb execution state mess in git.

`pip install .` adds `jupyter mathbook` and `jupyter kernel` bash commands.

Write markdown .md file with ```python```  code fences, or start with .ipynb, and run
```bash
jupyter mathbook <filename>.ipynb # copies .ipynb outputs without running to <filename>.md
# or
jupyter mathbook <filename>.md # creates <filename>.ipynb, runs, and copies outputs to .md
# On failure, `<filename>.partial.ipynb` and `.md` up to failed cell are written.
# Successful rerun overwites the .ipynb and .md, and removes partials

# Optional Args
# --out <path>         .ipynb dir, ["."] # `Path(<file>.md).parent/out` unless `out` is absolute
# --images <path>      images dir, ["."] # `<out>/images/<name>/` unless `images` is absolute
# --compress-fmt <fmt> compression format for high bpp (>.45) images  ["webp"] | "jpeg"
# --quality <90>       compression quality for webp and jpeg
# --no-mirror          images not mirrored into .md
# --validate           writes <file>.validate.ipynb & .validate.md # does not touch existing .md and .ipynb
#                      successful rerun w/o --validate to overwrite

# --no-run             (only .md -> .ipynb) output .ipynb without running.
# --reuse              (only .md -> .ipynb) only runs changed code

# --force              (only .ipynb -> .md). if <name>.md exists overwrite.
```


Example
```bash
# TODO add examples
# cd examples && jupyter mathbook TheoremaEgregium.md
```

### 2. `jupyter kernels`
Utility to inspect and/or shutdown jupyter kernels.
```bash
jupyter kernels                           # list jupyter kernels
jupyter kernels --stop                    # stop inactive kernels
jupyter kernels --stop --all               # stop all kernels
jupyter kernels --stop --older-than <int> # stop older than <int> minutes
jupyter kernels --stop --pid <int>        # stop by <int> pid
jupyter kernels --stop --parent <name>    # started by <name> parent process
```
