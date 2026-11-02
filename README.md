# mathbook .ipynb $\leftrightarrow$ .md

Two commands. Bash and linux only

1. `jupyter mathbook` to create or run a static version of a jupyter notebook
2. `jupyter kernel` to inspect or stop hanking kernels


## 1. `jupyter mathbook <filename>.<md/ipynb>`

Static jupyter notebooks. Prevent hanging kernels. Avoids git .ipynb mess.
- Converts `.md` to `.ipynb` and `.ipynb` to `.md`.
- writes .ipynb images and outpts to fenced blocks.

`pip install .` adds `jupyter mathbook` and `jupyter kernel` bash commands.


Write markdown file with ```python```  code fences, or start with ipynb, and run
```bash
jupyter mathbook <filename>.md # creates <filename>.ipynb, runs, and copies outputs to .md
# or
jupyter mathbook <filename>.ipynb # copies .ipynb outputs without running to <filename>.md

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
cd examples && jupyter mathbook TheoremaEgregium.md
```

## 2. `jupyter kernels`
Utility to inspect and/or shutdown jupyter kerne;s
```bash
jupyter kernels                           # list jupyter kernels
jupyter kernels --stop                    # stop inactive kernels
jupyter kernels --stop -all               # stop all kernels
jupyter kernels --stop --older-than <int> # stop older than <int> minutes
jupyter kernels --stop --pid <int>        # stop by <int> pid
jupyter kernels --stop --parent <name>    # started by <name> parent process
```
