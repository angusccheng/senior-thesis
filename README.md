# Video retrieval thesis baseline

Research backend for natural-language retrieval from continuous video. It prepares
independent camera clips, records source-time and availability metadata, and indexes
frames selected uniformly or for appearance diversity with pretrained OpenCLIP. Retrieval uses exact cosine
similarity. No frontend, captions, hybrid representations or change-aware sampling
are implemented.


**[Run both methods and interpret their results](docs/RUNNING_METHODS.md)** is the command walkthrough.

**Start with [Results overview](docs/RESULTS_OVERVIEW.md)** for the current stats table,
prepared clips and missing measurements. [The truck demo](docs/DISTINCT_EVENT_DEMO.md)
is the meeting walkthrough. Earlier reports live in [docs/history](docs/history/README.md).

The thesis objective, measurement boundaries, baseline instrumentation audit, and
reusable JSON cost schema are documented in [BENCHMARKING.md](docs/BENCHMARKING.md).
Primary comparisons are retrieval accuracy versus persistent index storage; compute
and memory are separately reported tradeoffs.

## Project layout

```text
main.py, prepare_data.py     Existing CLI entry points
video_search/               Encoding, sampling, storage, dataset and video utilities
configs/                    Approved camera crops and recording metadata
data/originals/             Registry of external original recordings
data/processed/             Reserved for future full camera exports (none made)
data/clips/smoke/            Links to preserved short camera samples
data/clips/dev/              Three verified development clips and frame-time CSVs
data/metadata/              Availability reports, review evidence and update rates
indexes/                    Persistent NPZ indexes and index metadata
results/retrieval/           Ranked JSON/CSV results and matching JPEGs
experiments/                Query sets, commands, timing/memory metrics and logs
docs/                       Detailed preparation and verification reports
scripts/, tests/            Reproducible experiment tools and automated tests
archive/                    Preserved historical outputs and pre-cleanup snapshots
output/                     Compatibility link to archive/legacy_output
```

The original MOV remains on the Desktop. Nothing in the workflow modifies it.
All 150 previous output files are preserved. `output/`, archives, environments and
caches are hidden in VS Code's Explorer; they still exist. Older CLI paths continue
to work through the compatibility link. See [cleanup inventory](experiments/cleanup_2026-11-03.json).

## Setup

The existing `.venv` and cached weights are ready locally. For a new environment:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
brew install ffmpeg           # macOS; Ubuntu/Debian: sudo apt install ffmpeg
```

Use a recent FFmpeg with libx264. Python 3.11/macOS arm64 is the tested environment.
First model use downloads weights; `HF_HUB_OFFLINE=1` uses the existing local cache.
See [baseline implementation details](docs/history/BASELINE_USAGE.md).

## Add and prepare recordings

```bash
.venv/bin/python prepare_data.py init --source '/absolute/path/recording.mov' \
  --config configs/new_recording.json --feeds 7
.venv/bin/python prepare_data.py preview --config configs/new_recording.json \
  --at 30 --output data/metadata/new_recording/crop_preview
```

Enter crop rectangles in the configuration. The NYC coordinates in
[configs/nyc_traffic.json](configs/nyc_traffic.json) are already approved and reused
unchanged. Short smoke samples remain available at
`data/clips/smoke/nyc_traffic_30_60/`.

The three prepared development videos are in
`data/clips/dev/nyc_traffic_000500_001500/`: Broadway @ 46 St Quad South, Broadway @
43 St, and Central Park West @ 72 St. They share the requested source interval
00:05:00–00:15:00. Each contains 843 frames and plays for 598.760 s because sparse
VFR boundary frames are not synthesized. Every source-frame mapping is retained.
No full-length camera exports were made.

See [DATA_PREPARATION.md](docs/DATA_PREPARATION.md) for exact export, availability,
review and validation commands. The current quality protocol is
[data/metadata/nyc_traffic/availability_v2/availability.json](data/metadata/nyc_traffic/availability_v2/availability.json).
Confirmed outages are excluded; ambiguous static/dark/frozen footage is flagged,
retained and available for review. All methods must use the same versioned protocol.

## Index and search

Use the dataset manifest for camera footage so camera ID, source timestamps,
availability policy and crop/encoding settings are embedded alongside the index.
Use **new output paths** when repeating these commands; completed runs are preserved.

```bash
HF_HUB_OFFLINE=1 .venv/bin/python main.py index \
  --video data/clips/dev/nyc_traffic_000500_001500/broadway_46st_quad_south.mp4 \
  --dataset-manifest data/clips/dev/nyc_traffic_000500_001500/broadway_46st_quad_south.dataset.v2.json \
  --interval 5 --batch-size 16 --threads 4 --index indexes/my_run/index.npz

HF_HUB_OFFLINE=1 .venv/bin/python main.py search --index indexes/my_run/index.npz \
  --query 'Yellow taxis driving through an intersection.' \
  --output results/retrieval/my_run/taxis
```

Search returns five frames by default and saves JPEGs plus full-precision CSV/JSON
scores and both cropped-video and original-recording times. It reloads the saved
index; it does not re-embed video images. Preview export decodes the cropped MP4,
while the original multi-camera recording is unnecessary. Add `--no-previews` to
retrieve without video access. Query scores are not probabilities. Ground-truth
intervals are not yet annotated, so no retrieval-accuracy claim is made.

`--dataset-manifest` remains optional for the original plain-video smoke baseline;
that mode has no camera-specific availability/source-grid provenance. Research runs
on prepared camera videos should always pass an explicit, shared manifest.

## Define, run and compare experiments

**[configs/experiments.json](configs/experiments.json) is the runnable catalog.**
Each named entry lists `method`, `footage`, `dataset_manifest`, sampling interval,
query file, batch size and threads. The overview shows these settings alongside
current/planned status. Uniform and diversity sampling use the same fixed OpenCLIP encoder. See
[Method 2: diversity sampling](docs/DIVERSITY_SAMPLING.md) for its exact rule and costs.

```bash
# See each method + footage + status together
.venv/bin/python scripts/run_experiment.py list

# Display saved stats and top-five results (no computation)
.venv/bin/python scripts/run_experiment.py results --id diversity_120_broadway46_dev_r01

# Inspect all settings, output paths and the exact command (no computation)
.venv/bin/python scripts/run_experiment.py show --id uniform_5s_broadway43_dev_r01

# Preview a planned run; remove --dry-run to execute it
.venv/bin/python scripts/run_experiment.py run --id uniform_5s_broadway43_dev_r01 --dry-run
```

An executed entry builds the index, runs its queries in fresh processes and with
a resident model, verifies timestamps/rankings/previews, and saves a configuration
snapshot with the evidence. Successful runs register automatically and refresh the
stats tables, and prints a readable stats/result summary in the terminal.
Failed attempts keep their logs and do not become completed rows.
Index, retrieval and evidence folders all use the same experiment ID. Existing
outputs are protected; copy an entry with a **new ID** for another repetition.

The Broadway 46 St uniform entry identifies the original benchmark. The diversity
entry uses that same clip and retains 120 frames. Other-camera uniform entries
remain planned until executed. All three reuse the original three-query file;
these are demonstration queries, with no annotated accuracy yet. For a sampling
comparison, repeat the **same footage and query file** at another interval under a
new ID; compare actual measured bytes. Runs on other clips extend dataset coverage.


[experiments/summary.csv](experiments/summary.csv) stores one row per registered,
completed comparison run, with units, repetition counts and reasons for missing
measurements. [experiments/registry.json](experiments/registry.json) identifies the
current run and preserves superseded/failed attempts separately. An audit is a
view of an existing run and is never counted as another experiment.

Refresh the tables from saved JSON without processing video or loading a model:

```bash
.venv/bin/python scripts/summarize_experiments.py
```

Use the same clip, model, eligibility policy, queries and storage definition for
future controlled comparisons. Accuracy remains pending event annotations.

## Verify and reproduce

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip check
```

The latest experiment is `experiments/nyc_dev_uniform_5s_v3/`; its index is in
`indexes/nyc_dev_uniform_5s_v3/` and retrieval outputs are in
`results/retrieval/nyc_dev_uniform_5s_v3/`. Queries, subprocess commands, independent
cosine/image checks, timing, memory measurements and limitations are documented in
[DEVELOPMENT_VERIFICATION.md](docs/DEVELOPMENT_VERIFICATION.md).

See [CAMERA_AVAILABILITY.md](docs/CAMERA_AVAILABILITY.md) for outages, uncertain
intervals, usable-duration accounting and camera update-rate measurements. The
[earlier sample-video verification](docs/history/baseline_verification.md) remains preserved.

## GitHub checkout and local research artifacts

This repository versions the source code, tests, documentation, approved crop
configuration, timeline/availability metadata, and small experiment reports.
Recordings, cropped MP4s, generated preview images, per-frame diagnostic traces,
model caches, saved NPZ indexes, and local archives are excluded from Git.
They remain on the development machine and are recreated using the documented
preparation/indexing commands. Existing report links to those local artifacts
will become available after regeneration; the repository alone is not the dataset.

Historical JSON manifests contain absolute paths from the original experiment.
On another machine, initialize a configuration for the recording's local path and
regenerate clip/index manifests rather than treating historical paths as portable.
The five-hour source recording is supplied separately and is never modified.

The initial repository uses the local SSH remote
`git@github.com:angusccheng/senior-thesis.git`. Future changes can be published with:

```bash
git status
git add .
git commit -m "Describe the change"
git push
```
