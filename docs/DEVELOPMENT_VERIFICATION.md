# Development OpenCLIP baseline verification

**PASS**: 8/8 development-audit checks. All three queries were repeated in separate fresh processes; rankings, timestamps, scores and image filenames were identical. No retrieval accuracy is claimed without ground-truth event intervals.

[Complete experiment evidence/commands](../experiments/nyc_dev_uniform_5s_v3/experiment.json) · [Saved index](../indexes/nyc_dev_uniform_5s_v3/index.npz) · [Index metadata](../indexes/nyc_dev_uniform_5s_v3/index.metadata.json) · [Final regression/migration validation](../experiments/final_validation_2026-11-03/validation.json)

## Development footage

Requested shared source interval **00:05:00–00:15:00** (600 s). Each sparse-VFR clip starts at original source **301.738333333 s**, has last source-frame PTS **898.531666667 s**, and plays for **598.760 s**. Source PTS spacing is retained; boundary frames were not synthesized and final held-frame playback duration is not a reconstruction of exact source-window coverage.

| Camera/video | Resolution | Frames | Actual duration | ffprobe average FPS |
| --- | --- | ---: | ---: | ---: |
| [broadway_46st_quad_south](../data/clips/dev/nyc_traffic_000500_001500/broadway_46st_quad_south.mp4) | 592×356 | 843 | 598.760000 s | 1.407909680 |
| [broadway_43st](../data/clips/dev/nyc_traffic_000500_001500/broadway_43st.mp4) | 592×376 | 843 | 598.760000 s | 1.407909680 |
| [central_park_west_72st](../data/clips/dev/nyc_traffic_000500_001500/central_park_west_72st.mp4) | 592×372 | 843 | 598.760000 s | 1.407909680 |

[Development review sheet](../data/clips/dev/nyc_traffic_000500_001500/review_v2/contact_sheet.jpg) · [Frame/timestamp validation](../data/clips/dev/nyc_traffic_000500_001500/review_v2/verification.json) · [Exact FFmpeg export commands](../data/clips/dev/nyc_traffic_000500_001500/manifest.json)

The beginning/middle/end frame of each export matches its original camera region within CRF-18 re-encoding tolerance. All 843 encoded frame timestamps per camera agree with the source mapping CSV within 0.333334 μs. All three cameras have no detected quality flags in this window. Only these development and existing smoke clips were exported.

## Model, indexing, storage and performance

| Measurement | Observed value |
| --- | --- |
| Model/checkpoint | `ViT-B-32` / `laion2b_s34b_b79k` |
| Configuration | CPU, 4 Torch threads, fp32, seed 0, batch size 16; cached weights, offline |
| Uniform sampling | 5 s grid, first decoded frame at/after each target, then shared eligibility mask |
| Retained vectors | 120 × 512, float32, unit norm |
| Candidate/masked count | 120 / 0 excluded |
| Persistent archive | 285,146 bytes |
| Numeric payload | 248,640 bytes |
| Indexing, fresh process wall time | 9.306197 s |
| Core build incl. persistence | 3.719867 s, excluding model construction/imports |
| Mean fresh-process query wall time | 7.483912 s (three distinct queries) |
| Mean resident-model query time | 0.040987 s (9 queries, one untimed warm-up) |
| Index worker peak RSS | 1,166,409,728 bytes |
| Max query worker peak RSS | 1,343,242,240 bytes across six queries/repeats |

CPU, 4 Torch threads, fp32, seed0, batch16, 5s uniform, cached weights, offline; fresh-query times include imports/model loading/cropped-preview decoding/JPEG/CSV/JSON writes. Original grid is inaccessible during retrieval. Loaded model, one untimed warm-up, 9 queries; includes NPZ loading and text encoding/ranking, excludes previews/model load/initial fingerprint.

Fresh-process wall time is measured by the parent with `perf_counter()` around the child command, including interpreter import/exit and model construction. Query workers also decode only the cropped MP4 for JPEG previews. Peak RSS uses `resource.getrusage(RUSAGE_SELF).ru_maxrss` (Darwin bytes; Linux KiB converted). It excludes parent/other processes and is not whole-machine memory. OS cache state and background load are uncontrolled, and samples are few.

The numeric payload includes float32 embeddings plus float64 cropped timestamps, int64 frame numbers and float64 source timestamps: **2072 bytes/vector** at D=512. Generic legacy indexes without source-grid provenance use 2064 bytes/vector. Archive JSON/header overhead is additional. Compare methods using the same provenance schema and measured storage accounting.

Software: Python 3.11.7; macOS-26.5.2-arm64-arm-64bit. `numpy==2.4.6`, `opencv-python==5.0.0.93`, `Pillow==13.0.0`, `torch==2.14.1`, `torchvision==0.29.1`, `open_clip_torch==3.3.0`, `timm==1.0.30`.

Loaded model-tensor SHA-256: `e3267697543bbe2b3a7bd68f10d1b683ad822a7ad6088f45c32ea33b3c18cc58`. Index SHA-256: `f4629c31e5e6bc18d5f1903f60edbb02fd63795819912f1330d273c9c38f0fe1`.

## Actual ranked results

Both cropped and original source timestamps below refer to selected frames, not estimated event start/end times. Scores are cosine ranking values, not probabilities.

### Q1: Pedestrians crossing a wide crosswalk at a busy city intersection.

Fresh-process latency: 7.232022 s. [JSON](../results/retrieval/nyc_dev_uniform_5s_v3/query_01/results.json) · [CSV](../results/retrieval/nyc_dev_uniform_5s_v3/query_01/results.csv)

| Rank | Cropped time | Source time | Source seconds | Cosine | Preview |
| --- | --- | --- | ---: | ---: | --- |
| 1 | 00:07:46.558 | 00:12:48.297 | 768.296666667 | 0.341718644 | [rank_01_frame_00000658.jpg](../results/retrieval/nyc_dev_uniform_5s_v3/query_01/rank_01_frame_00000658.jpg) |
| 2 | 00:04:30.320 | 00:09:32.058 | 572.058333333 | 0.339663684 | [rank_02_frame_00000390.jpg](../results/retrieval/nyc_dev_uniform_5s_v3/query_01/rank_02_frame_00000390.jpg) |
| 3 | 00:01:06.067 | 00:06:07.805 | 367.805000000 | 0.338752508 | [rank_03_frame_00000103.jpg](../results/retrieval/nyc_dev_uniform_5s_v3/query_01/rank_03_frame_00000103.jpg) |
| 4 | 00:07:56.508 | 00:12:58.247 | 778.246666667 | 0.336079836 | [rank_04_frame_00000674.jpg](../results/retrieval/nyc_dev_uniform_5s_v3/query_01/rank_04_frame_00000674.jpg) |
| 5 | 00:03:20.237 | 00:08:21.975 | 501.975000000 | 0.333254069 | [rank_05_frame_00000296.jpg](../results/retrieval/nyc_dev_uniform_5s_v3/query_01/rank_05_frame_00000296.jpg) |

### Q2: Yellow taxis driving through an intersection.

Fresh-process latency: 6.781680 s. [JSON](../results/retrieval/nyc_dev_uniform_5s_v3/query_02/results.json) · [CSV](../results/retrieval/nyc_dev_uniform_5s_v3/query_02/results.csv)

| Rank | Cropped time | Source time | Source seconds | Cosine | Preview |
| --- | --- | --- | ---: | ---: | --- |
| 1 | 00:01:26.102 | 00:06:27.840 | 387.840000000 | 0.309757769 | [rank_01_frame_00000131.jpg](../results/retrieval/nyc_dev_uniform_5s_v3/query_02/rank_01_frame_00000131.jpg) |
| 2 | 00:04:46.338 | 00:09:48.077 | 588.076666667 | 0.295387238 | [rank_02_frame_00000414.jpg](../results/retrieval/nyc_dev_uniform_5s_v3/query_02/rank_02_frame_00000414.jpg) |
| 3 | 00:04:50.372 | 00:09:52.110 | 592.110000000 | 0.268874735 | [rank_03_frame_00000419.jpg](../results/retrieval/nyc_dev_uniform_5s_v3/query_02/rank_03_frame_00000419.jpg) |
| 4 | 00:07:50.558 | 00:12:52.297 | 772.296666667 | 0.266761988 | [rank_04_frame_00000665.jpg](../results/retrieval/nyc_dev_uniform_5s_v3/query_02/rank_04_frame_00000665.jpg) |
| 5 | 00:01:20.102 | 00:06:21.840 | 381.840000000 | 0.259376705 | [rank_05_frame_00000122.jpg](../results/retrieval/nyc_dev_uniform_5s_v3/query_02/rank_05_frame_00000122.jpg) |

### Q3: A bus passing through a crowded intersection.

Fresh-process latency: 8.438034 s. [JSON](../results/retrieval/nyc_dev_uniform_5s_v3/query_03/results.json) · [CSV](../results/retrieval/nyc_dev_uniform_5s_v3/query_03/results.csv)

| Rank | Cropped time | Source time | Source seconds | Cosine | Preview |
| --- | --- | --- | ---: | ---: | --- |
| 1 | 00:05:26.372 | 00:10:28.110 | 628.110000000 | 0.326139897 | [rank_01_frame_00000467.jpg](../results/retrieval/nyc_dev_uniform_5s_v3/query_03/rank_01_frame_00000467.jpg) |
| 2 | 00:04:56.355 | 00:09:58.093 | 598.093333333 | 0.320534587 | [rank_02_frame_00000429.jpg](../results/retrieval/nyc_dev_uniform_5s_v3/query_03/rank_02_frame_00000429.jpg) |
| 3 | 00:03:10.253 | 00:08:11.992 | 491.991666667 | 0.320177615 | [rank_03_frame_00000278.jpg](../results/retrieval/nyc_dev_uniform_5s_v3/query_03/rank_03_frame_00000278.jpg) |
| 4 | 00:05:20.372 | 00:10:22.110 | 622.110000000 | 0.318524361 | [rank_04_frame_00000459.jpg](../results/retrieval/nyc_dev_uniform_5s_v3/query_03/rank_04_frame_00000459.jpg) |
| 5 | 00:07:46.558 | 00:12:48.297 | 768.296666667 | 0.315167040 | [rank_05_frame_00000658.jpg](../results/retrieval/nyc_dev_uniform_5s_v3/query_03/rank_05_frame_00000658.jpg) |

## Executed correctness checks

- PASS: `uniform_selection_matches_independent_grid`.
- PASS: `finite_unit_embeddings`.
- PASS: `fresh_process_queries_repeat_identically`.
- PASS: `original_not_accessed_no_reencoding_no_image_embedding_recompute`.
- PASS: `independent_cosine_and_rankings`.
- PASS: `all_preview_jpegs_match_cropped_frame`.
- PASS: `retrieval_source_times_match_export_csv`.
- PASS: `index_unchanged`.

Independent float64 cosine-formula maximum discrepancy: 6.11e-08. Every original source time joins to the export CSV. All 30 preview JPEGs (15 originals +15 repeats) match independently decoded cropped frames exactly at Pillow quality 95. The 120-frame selection matches an independent five-second grid/searchsorted calculation.

Every retrieval worker blocks original-recording file access, original-recording VideoCapture, image embedding, index rebuilding and FFmpeg re-encoding. All searches passed these guards. Cropped-preview decoding and JPEG writing are intentionally allowed. All eight checks passed; no source-grid reprocessing or embedding recomputation occurred.

All three index builds (v1/v2/v3) have identical embedding, cropped-time, frame-number and source-time arrays. Archive hashes differ because runtime/provenance metadata differs. The sampler and encoder/ranking algorithms were not replaced.

## Preserved earlier runs, errors and timing variability

- v1 built a valid index, then the audit guard incorrectly blocked Python `platform` from invoking its harmless OS-information subprocess. The guard was corrected to block video re-encoding/original access, rather than all subprocesses. Its logs and index remain preserved.
- v2 completed all development checks under availability_v1. It is superseded by v3 only to pin the reviewed maintenance-card availability_v2 protocol. The Broadway eligibility and numeric index payload are identical in all versions.
- v3 is the current complete run under availability_v2, not a selection of the fastest run. Earlier measured indexing latencies were approximately 49.885 s (v1) and 35.930 s (v2); v2 fresh queries were 8.307, 10.746 and 31.847 s (mean 16.967 s). These preserved observations show substantial run-to-run/cache/resource variability; the current timings are not stable cross-method benchmark estimates. Repeated controlled runs are needed.

## Exact reproduction commands

Use new output names when repeating; no completed result is overwritten. The executed orchestrator command was:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python scripts/run_development_experiment.py \
  --dataset-manifest data/clips/dev/nyc_traffic_000500_001500/broadway_46st_quad_south.dataset.v2.json \
  --index indexes/nyc_dev_uniform_5s_v3/index.npz \
  --results results/retrieval/nyc_dev_uniform_5s_v3 \
  --output experiments/nyc_dev_uniform_5s_v3
```

It runs the standard `main.py index` / `main.py search` entry points in guarded workers. Every exact child command, stdout/stderr and timing is in the linked experiment JSON; the root README gives equivalent ordinary CLI commands. Dataset preparation and availability commands are in [DATA_PREPARATION.md](DATA_PREPARATION.md).

Additional regression commands executed:

```bash
.venv/bin/python scripts/validate_project.py --output experiments/final_validation_2026-11-03
HF_HUB_OFFLINE=1 .venv/bin/python scripts/verify_baseline.py --output experiments/legacy_regression_2026-11-03
```

Regression: **18 tests passed**; pip dependencies consistent; both CLI help commands pass. The original sample-video end-to-end audit also passes **64/64 checks** in fresh processes. Migration validation verifies all 150 historical output files by SHA-256, unchanged crop coordinates, unchanged source size/mtime/sampled fingerprint, working legacy link and identical numeric payloads across the three development index builds.

## Remaining limitations and next steps

- No ground-truth retrieval intervals exist; no accuracy, recall, mAP or event-boundary claim is made. Annotate a fixed query set and held-out intervals before comparing methods.
- Frozen intervals remain uncertain and require human/clock review. Heuristic availability is not exhaustive; strict dark-flat checks cannot recognize all unfamiliar outage screens.
- Camera clocks/latencies and exact VFR boundary coverage are not calibrated. Use frame-level source mappings and avoid silently time-compressing excluded intervals.
- Runtime/memory observations are small-sample CPU measurements, with uncontrolled OS caches/load. GPU behavior, full-length camera indexing and large-corpus scaling remain untested.
- The original recording fingerprint samples the first/last MiB plus size; a full-file checksum was not computed. Cropped video/index/mapping/availability files have full hashes.
- No full-length camera exports, new indexing methods or frontend were implemented. Fix dataset version, eligibility policy, queries, annotations, encoding, hardware, model settings and storage-budget convention before the comparative evaluation.
