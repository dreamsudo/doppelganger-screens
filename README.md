# Doppelganger Screens

The laboratory behind the paper **Doppelganger Screens: Indistinguishable Authority Spoofing Against Computer Use Agents** (Christian David Varela, Psypher Labs, 2026): the harness, the experiments, every recorded episode the paper reads, and the scripts that rebuild the paper from those records.

## The experiment

A computer-use agent sees a screen and acts on it. An authority prompt on that screen — a sign-in form, a permission dialog, a confirmation, an update notice — can be drawn by the application that owns the screen or by content inside it: a web page, a chat message, an email. When the two renderings are pixel-identical nothing in a screenshot tells them apart. The paper measures what three agents do with such a copy: two open-weight models run locally (Qwen3-VL 8B, UI-TARS 1.5 7B) and one frontier model over its API (Claude Opus 5.5), on paired episodes that differ only in who drew the prompt. Under screenshot-only observation on the browser surfaces the agents act on the copy 71%, 74% and 96% of the time. The record then follows the copy under richer observations (the accessibility tree, principal labels), through the published pixel-side defences run on the same screens, and across a text-injection comparison. [RESULTS.md](RESULTS.md) lists every number; the paper reports and interprets them.

## What is here

| path | contents |
|---|---|
| [paper/doppelganger-screens.pdf](paper/doppelganger-screens.pdf) | the paper, 14 pages, rebuilt from this tree |
| [METHOD.md](METHOD.md) | the preregistered method: threat model, definitions, result and corollaries, hypotheses and refuters, design, experiments, analysis, limits, ethics, and the 22 preregistered claims |
| [RESULTS.md](RESULTS.md) | the numbers, computed from `results/` by `paper/facts.py` |
| `paper/` | the generator: `facts.py` (record → `facts.json`), `figures.py` and `figures8.py` (record → `figures/`), `paper.py` (HTML), `print.py` (print layout), `stamp.py` (page numbers), plus caption and diagram modules |
| `src/awp/` | the harness: the lab web application, the mail and chat cells, the browser and desktop drivers, the agent adapters (local `llama-server` and the Anthropic SDK), metrics and analysis, the network allow-list |
| `experiments/E0` … `E4` | the runners: E0 instrument checks, scripted controls, utility floors and probes; E1 the paired runs; E2 the defences on the recorded pairs; E3 the frontier runs under provenance observation (their episodes are in `results/E1/paired/`); E4 the text-injection comparison |
| `results/` | the record: per run `episodes.jsonl`, `summary.json` where the runner writes one, the screenshots under `shots/`, and beside every run `<name>.provenance.json` (and `<name>.usage.json` for paid runs) |
| `configs/` | the cells, the frozen contexts, the preregistered fixed values, the schemas, and `pins.yaml`: the hash of every third-party source, dataset, model, weight and instrument used |
| `data/raw/wainjectbench/MANIFEST.sha256` | the manifest of the pinned WAInjectBench image set (the images themselves are not distributed; see below) |
| `lab` | run a command under a provenance record; analyse a run |
| `requirements*.txt` | the Python environments, pinned as they ran |

## Rebuilding the paper

```bash
python3 paper/facts.py && python3 paper/figures.py && python3 paper/figures8.py && python3 paper/paper.py && python3 paper/print.py && (cd paper && chromium --headless --no-sandbox --disable-gpu --disable-dev-shm-usage --virtual-time-budget=30000 --no-pdf-header-footer --print-to-pdf=doppelganger-screens.pdf print.html && python3 stamp.py)
```

`facts.py` applies the registered utility floor (the `results/E0/utility-floor-*` runs, genuine prompt only, threshold 0.70 per agent, cell and act); every number in the paper and in RESULTS.md is computed under it. Of the paper's fifteen figures, ten are drawn from the record by `figures.py` and `figures8.py`, three are diagrams drawn by the generator itself, and two (`paper/figures/first-clicks.png`, `first-action.png`) are committed as images.

## Reproducing the measurements

**Environments.** The harness, the experiments and the paper build run on the system Python 3.14 with [requirements.txt](requirements.txt). Three tasks run in their own virtual environments: the Anthropic SDK ([requirements-anthropic.txt](requirements-anthropic.txt), `.venv-anthropic`), the SnapGuard reproduction ([requirements-snapguard.txt](requirements-snapguard.txt), `.venv-snapguard`) and the UI-TARS weight conversion ([requirements-gguf.txt](requirements-gguf.txt), `.venv-gguf`). The system packages (Roundcube, Dovecot, Thunderbird, PostgreSQL, AT-SPI, Docker, the Kali `llama.cpp` source) are listed with versions under `installed` in [configs/pins.yaml](configs/pins.yaml).

**Third-party material** lives in a sibling directory, `../alpha-vendor/`, and is not part of this repository: the native `llama.cpp` build, the model weights, the Mattermost server and desktop client, the two published defences (UCM, SnapGuard) and the WAInjectBench clone. `configs/pins.yaml` records the source, the revision and the sha256 of each, so every piece can be fetched and checked. For the image set:

```bash
git clone https://github.com/Norrrrrrr-lyn/WAInjectBench ../alpha-vendor/WAInjectBench && git -C ../alpha-vendor/WAInjectBench checkout ee55236860820b3639c9039a2aa367b2cb86d114 && (cd ../alpha-vendor/WAInjectBench && sha256sum -c "$OLDPWD/data/raw/wainjectbench/MANIFEST.sha256" | grep -v ': OK$' || echo "all 2970 files verified")
```

**Running.** `./lab run` pins the command to the current commit, hashes `configs/` and the pinned raw data, runs it under a timeout and writes `results/<exp>/<name>.provenance.json` beside whatever the command produced. `./lab analyse` summarises a run's episode records: rates per group with their intervals, the equivalence verdict, the no-data count and the utility-floor verdict for that run.

```bash
./lab run --exp E1 --name paired --class local --timeout 21600 --depends experiments/E1/paired_runs.py src/awp/harness.py configs/prereg.yaml -- python3 experiments/E1/paired_runs.py
```

```bash
./lab analyse results/E1/paired/episodes.jsonl --by cell,act,agent,observation
```

A model-class run (`--class model`) takes `ANTHROPIC_API_KEY` from `~/.config/awp/anthropic.env` into the child's environment only; the key is never printed or stored, and `--max-usd` is the run's spend cap. `lab analyse` judges the utility floor from the run it is given; `paper/facts.py` applies the registered floor from the E0 utility-floor runs, which is why a cell can be reported differently by the two.

**The network.** Every target application runs on the loopback interface of the lab machine. The only outbound destination allowed during the runs was the Anthropic API host; the rule set is [src/awp/allowlist.nft](src/awp/allowlist.nft) and [src/awp/netprobe.py](src/awp/netprobe.py) verifies it from inside without privileges.

**The record.** Each provenance record carries the command, the commit, the hash of `configs/` and of the pinned data, the instrument (guest OS, Python, the native `llama.cpp` binaries by hash), the exit status, the wall time and, for paid runs, the token usage and the spend at the pinned prices. `results/E1/paired/episodes.jsonl` was appended to by several invocations — the open-weight batches under `paired`, the frontier batches under `paired-frontier*` in `E1` and `E3` — and the record of each is kept beside it. Commit hashes in the records refer to the development history, which is not published; the tree at those commits produced the files you see. The paper reports 33.72 USD of API spend for the whole project; the runs whose records are in this tree account for 27.36 USD of it, the rest went to earlier versions, re-checks and a superseded judge run that the paper does not read and that are not distributed.

## What is not here

The development history, the project's working notes and decision records, pilot and superseded runs, the stdout and stderr streams of the runs, and the third-party sources, weights and images named above.

## Ethics

Own infrastructure and accounts only; no live third parties; no real credential entered anywhere; no human subjects. The only commercial system exercised was the model vendor's computer-use interface, used as documented and within its terms, and the only outbound destination during the runs was its API host under the allow-list above. The full statement is in METHOD.md §10.

## Licence

Code (`src/`, `experiments/`, `lab`, `paper/*.py`, `configs/`) is released under the [Apache License 2.0](LICENSE). Data and figures (`results/`, `paper/figures/`, the PDF) are released under [CC BY 4.0](LICENSE-DATA).

## Citation

See [CITATION.cff](CITATION.cff).

> Christian David Varela. *Doppelganger Screens: Indistinguishable Authority Spoofing Against Computer Use Agents.* Psypher Labs, 2026.

## Acknowledgement

Analysis, verification and writing assisted by Claude (Mythos 5.1), Anthropic.
