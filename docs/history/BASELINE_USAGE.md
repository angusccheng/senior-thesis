> Historical baseline implementation/usage notes, preserved during cleanup. Source modules now live in `video_search/`; existing CLI commands and legacy `output/` paths remain compatible. See the root README for current dataset workflows.

# Natural-language temporal video retrieval baseline

A research baseline for comparing frame selection under fixed storage budgets.
It loads an MP4, selects frames, embeds them with OpenCLIP, and ranks the retained
frames against a natural-language query. There is no training or approximate search.

For the seven-camera NYC screen recording, see [DATA_PREPARATION.md](../DATA_PREPARATION.md)
and [configs/nyc_traffic.json](../../configs/nyc_traffic.json). The separate `prepare_data.py`
workflow exports camera crops, preserves timestamp mappings and diagnoses visible
update rates. Short samples are ready for crop review; full-length exports remain blocked.

The executed three-query backend audit, exact retrieval tables and measured
runtimes are in [baseline_verification.md](baseline_verification.md). To repeat
that audit with cached weights, use a new artifact directory:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python scripts/verify_baseline.py --output output/new_verification
.venv/bin/python scripts/render_verification_report.py \
  --evidence output/new_verification/verification.json --report baseline_verification.md
```

## Setup and first experiment

Tested with Python 3.11.7 on macOS arm64. Dependencies are installed in `.venv/`.
Direct dependencies are pinned in `requirements.txt`; `requirements.lock.txt`
records the full installed dependency set for repeating this environment. Wheel
availability on other Python versions/platforms can differ.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt

# Optional: download the small real MP4 used for the smoke test.
# Skip this if data/sample.mp4 already exists.
python scripts/download_sample.py

python main.py index --video data/sample.mp4 --interval 1 \
  --batch-size 4 --index output/my_run/index.npz

# After the first model download, prevent Hub network checks with this variable.
HF_HUB_OFFLINE=1 python main.py search --index output/my_run/index.npz \
  --query "cars driving on a road beside trees" --output output/my_run/matches
```

The first indexing run downloads approximately 600 MB of pretrained weights into
`.cache/open_clip/`. Subsequent indexing commands can also use `HF_HUB_OFFLINE=1`.
CPU is the default. `--device cuda` or `--device mps` opts into acceleration;
repeat experiments on the same device and dependency versions. `--threads` defaults
to 4. Existing index files and results directories are refused to avoid overwriting
an experiment; supply a new path for each run.

The sample download records its source URL and SHA-256 in `data/sample.source.json`.
This short, mostly single-scene clip is a pipeline smoke test, not evidence of
retrieval quality. Use an annotated, diverse video collection for the thesis.

## Modules and extension point

| File | Responsibility |
| --- | --- |
| `video.py` | Sequential FFmpeg decoding, RGB conversion, decoded timestamps and exact frame extraction |
| `samplers.py` | `Sampler` protocol and `UniformSampler` selection policy |
| `encoder.py` | Shared OpenCLIP image/text preprocessing, inference and normalization |
| `pipeline.py` | Index persistence, validation, cosine ranking and preview export |
| `main.py` | CLI configuration and CSV/JSON result writing |
| `tests/test_baseline.py` | Offline regression tests with a generated MP4 |

`build_index(video, sampler, encoder, output, batch_size=16)` accepts any sampler
implementing `select(timeline) -> list[FrameInfo]` and `metadata() -> dict`.
Selections must be unique frames from that timeline in chronological order.
A diversity/change sampler can receive the video path and any feature extractor
through its constructor, decode candidate frames as needed, then return selected
`FrameInfo` entries. Record its settings in `metadata()`. Only the sampler changes;
index construction and `search_index` remain shared. Candidate feature computation
and selection costs should be measured separately from retained-index storage.

## Implementation decisions

**Timestamp correctness.** The decoder records frame numbers and presentation
times reported by OpenCV's FFmpeg backend. Uniform targets are `0, interval,
2 * interval, ...`; select the first decoded frame at or after each target, with
a 1 ns comparison tolerance. Repeated selections are skipped when the interval is
shorter than frame spacing. Store actual decoded times, rather than requested seek
times. Fractional seconds are preserved in NPZ, CSV and JSON; console times show
milliseconds. No frame at the end-of-file boundary is invented.

Indexing first scans the timeline, then decodes the selected frames in a second
pass. Preview export uses the stored frame numbers and verifies their timestamps.
This avoids approximate seeks and uses memory proportional to timeline metadata,
retained embeddings and one image batch, rather than holding all decoded RGB frames.
It trades extra decoding time for clear frame identity. Missing/non-increasing
presentation times and detected early decoder termination are rejected. OpenCV
provides no exhaustive corruption check, and some unusual MP4s may need remuxing
or a different decoder backend.

**Shared representation and exact ranking.** Defaults are `ViT-B-32` with
`laion2b_s34b_b79k` weights. Images use the checkpoint's evaluation transform;
queries use its tokenizer. The model runs in evaluation mode with inference mode,
float32 precision, seed 0 and deterministic PyTorch algorithms. Both modalities
are normalized to unit length, so their dot product is cosine similarity. This
follows the [official OpenCLIP inference recipe](https://github.com/mlfoundations/open_clip#usage).
Scores are ranking values, not probabilities. Exact search avoids ANN parameters
as a confound. Ties use chronological index order. Default top-k is 5; fewer than
five retained frames returns all frames. Invalid top-k or blank queries are errors.

**Persistence and provenance.** Each uncompressed NPZ contains float32 embeddings,
float64 timestamps, int64 frame numbers and JSON metadata; loading disallows pickle.
One archive is written through a temporary file, so metadata and arrays stay together.
Its `.metadata.json` sidecar is a readable report, not the source used by search.
It records the source SHA-256, sampler settings, model identity, a hash of the actual
loaded model tensors, preprocessing, core library versions, batch size and storage
counts. Search reconstructs the recorded encoder and rejects mismatched weights,
precision, preprocessing or core dependency versions. Save the dependency lock
and source code with thesis experiments. Deterministic settings do not promise
identical floating-point results across devices, batch sizes or software versions.

**Inspection and source access.** Search saves five ranked JPGs and
`results.csv` / `results.json`, including the query, index hash, seconds, frame
numbers, cosine scores and image filenames. Each query should use a separate
`--output`. Previews require the original video; its SHA-256 is verified before
extraction. `--video /new/location.mp4` supports a relocated source. Add
`--no-previews` to retrieve and save rankings without accessing source footage.
Preview JPEGs, source footage and model weights are excluded from index payload
counts and should be accounted for separately if your experimental setting retains
them. Frame retrieval supplies candidate times, not inferred event start/end spans.

## Budget comparisons

```bash
HF_HUB_OFFLINE=1 python main.py index --video data/sample.mp4 --interval 0.5 \
  --max-frames 5 --index output/uniform_5/index.npz
```

The cap evenly subsamples the interval-selected candidates across the whole video
(including first/last candidates when the cap is at least 2). It does not retain
only an initial prefix. A cap of 1 keeps the first candidate. If fewer candidates
exist than the cap, all are retained, and the recorded count exposes the shortfall.
The capped variant is documented separately from pure interval sampling; choose a
dense enough candidate grid when matching retained counts across strategies.

For embedding dimension D, each retained frame costs `4*D + 8 + 8` numeric bytes.
With the default D=512, this is **2,064 bytes/frame**. A payload budget B therefore
permits `floor(B/2064)` frames; budgets below 2,064 cannot retain a frame. Use that
count as `--max-frames` and verify the recorded count. Storage reporting separates:

- `embedding_bytes`, `timestamp_bytes`, `frame_number_bytes` and `payload_bytes`.
- `index_file_bytes`: the archive's actual size, including JSON and NPZ overhead.

The archive is uncompressed so embedding content cannot affect compression ratios.
Metadata/header overhead still varies between experiments; equal frame counts
match numeric payloads, not necessarily total archive bytes. For a strict physical
file-size budget, use the measured archive size and adjust the cap. A fixed model
and dtype, common candidate pool, identical source hashes, and equal retained counts
are a clear first comparison. Candidate decoding/feature costs are not equalized
by storage caps. Later evaluation needs query ground-truth intervals, predefined
metrics (such as recall within a temporal tolerance), and validation/test splits.
Do not tune the sampling strategy to test queries.

## Validation

```bash
python -m unittest discover -s tests -v
python -m pip check
```

The offline tests cover fractional timestamps, exact RGB frame extraction, variable
timestamp grids, sub-frame intervals, capped timeline coverage, invalid inputs,
cosine ordering/ties, NPZ round trips, encoder mismatch and source hash checks.
The test encoder is a deterministic color-based double; it does not test OpenCLIP
semantics. The separate real-model smoke test indexed the downloaded MP4 at 1 s:
171 decoded frames, 6 retained 512-dimensional vectors, 12,384 payload bytes and
18,884 archive bytes. Its existing artifacts are in `output/sample/`, including
five JPEGs and result tables in `output/sample/matches/`. `output/sample/verification.json`
records a repeat-run equality check. These measurements validate execution and
persistence, not accuracy on a benchmark.
