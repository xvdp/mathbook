# mathbook .ipynb $\leftrightarrow$ .md

Linux bash jupyter notebook management.

1. `jupyter mathbook <file.{md, ipynb}>`: bidirectional conversion of .ipynb to static mirror .md
2. `jupyter kernels [args]`: list or stop hanging kernels (not to be confused with `jupyter kernel` which starts a new kernel).


### 1. `jupyter mathbook <file>.<md|ipynb>`

Static jupyter notebooks. Built to prevent hanging kernels and avoid .ipynb execution state mess in git.

`pip install .` adds `jupyter mathbook` and `jupyter kernels` bash commands.

Write markdown .md file with ```python```  code fences, or start with .ipynb, and run
```bash
jupyter mathbook <file>.ipynb   # copies outputs to: <file>.md
# or
jupyter mathbook <file>.md      # creates and runs <file>.ipynb, and copies outputs to <file>.md
```
* On failure, `<file>_partial.ipynb` and `.md` up to failed cell are written.
* Subsequent successful rerun overwites `<file>.ipynb` and `<file>.md`, and removes partials

If opposite md<->ipynb exists nothing is run unless:
```bash
jupyter mathbook <file>.{ipynb|md} --force  # Overwrites old
jupyter mathbook <file>.ipynb --force  --no-mirror # restores unrun state on .md
```
### Other optional args
```bash
--out <path>         # .ipynb dir, ["."] # `Path(<file>.md).parent/out` unless `out` is absolute
--images <path>      # images dir, ["."] # `<out>/images/<name>/` unless `images` is absolute
--compress-fmt <fmt> # compression format for high bpp (>.45) images  ["webp"] | "jpeg"
--quality <90>       # compression quality for webp and jpeg
--validate           # writes <file>.validate.ipynb & .validate.md # does not touch existing .md and .ipynb
                     # successful rerun w/o --validate to overwrite
# Only ,.md -> .ipynb
--no-run             # output .ipynb without running.
--reuse              # only runs changed code
```


### Ctrl-C
1. first Ctrl-C interrupts  kernel like jupyter's stop button. Cell keeps output + KeyboardInterrupt traceback.
2. second Ctrl-C, kills the kernel. The cell gets the error KeyboardInterrupt.
3. Ctrl-C during kernel startup	Kills the kernel straight away.

After any of these:
* `<file>_partial.` files are written and the failure banner prints.
* `<file>.ipynb`, `<file>.md` and the images stay unchanged.


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
