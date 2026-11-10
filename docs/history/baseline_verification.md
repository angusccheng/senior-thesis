# Uniform OpenCLIP baseline verification

Result: **PASS**. 64/64 audit checks passed; 0 failed. The separate offline unittest suite ran 7 tests successfully.

This is an executed backend verification using the existing real `data/sample.mp4`. No synthetic fallback was needed. No new selection method or frontend was added. The backend is ready for an adviser demonstration and development of a controlled evaluation; retrieval accuracy on annotated videos has not been established.

Machine-readable evidence, all child-process commands, stdout/stderr, and individual assertions: [output/verification_2026-10-27/verification.json](../../archive/legacy_output/verification_2026-10-27/verification.json).

## Video, configuration and performance

| Measurement | Observed value |
| --- | --- |
| Video stream duration | 5.700000 s |
| Container/movie duration | 5.759000 s |
| Last decoded frame timestamp | 5.666666667 s |
| Frame rate / source frame count | 30 FPS, 171 frames; CFR |
| Resolution | 1920 × 1080 |
| Uniform interval / retained frames | 1 s / 6 |
| Model / pretrained tag | `ViT-B-32` / `laion2b_s34b_b79k` |
| Embeddings | 6 × 512, normalized float32 |
| Index archive size | 19,632 bytes |
| Numeric index payload | 12,384 bytes |
| Embeddings / timestamps / frame numbers | 12,288 / 48 / 48 bytes |
| Indexing runtime, fresh process | 5.982927 s |
| Average query runtime, fresh process | 5.541595 s (3 queries) |
| Average query runtime, resident model | 0.024664 s (9 queries) |

CPU, 4 Torch threads, fp32, seed 0, batch size 4, 1 s interval, cached weights; no downloads. Fresh process times include interpreter/import/model load and preview/results I/O. Resident timings exclude model load, initial fingerprint and previews, but reload NPZ per query. Single indexing measurement; three fresh-process queries; nine resident queries.

Fresh-process timings are measured by the parent with `time.perf_counter()` around `subprocess.run()`, including interpreter exit. They use fresh interpreters with already cached model files and potentially warm OS file caches; they are not cold-download measurements. Fresh-query averages use the first execution of each of the three distinct queries, excluding repeat/guard/error tests. Resident timing uses three rounds of those queries after one untimed warm-up. The resident model fingerprint is computed before timing. These small-sample measurements are descriptive, not a throughput or scaling benchmark.

Environment: Python 3.11.7; `macOS-26.5.2-arm64-arm-64bit`. CPU inference, 4 Torch threads, fp32, seed 0, image batch size 4; network disabled with `HF_HUB_OFFLINE=1`. Exact installed dependencies are in `requirements.lock.txt`.

Core packages: `Pillow==13.0.0`, `numpy==2.4.6`, `open_clip_torch==3.3.0`, `opencv-python==5.0.0.93`, `timm==1.0.30`, `torch==2.14.1`, `torchvision==0.29.1`.

Source SHA-256: `05bd857af7f70bf51b6aac1144046973bf3325c9101a554bc27dc9607dbbd8f5`. Source: [Samplelib MP4](https://download.samplelib.com/mp4/sample-5s.mp4); local provenance is `data/sample.source.json`.

Index SHA-256: `735bef4b4ed1fd2f18ccf710f2f11be03f851270ba36d1cc85a783fb33b942f9`. Loaded-model tensor fingerprint: `e3267697543bbe2b3a7bd68f10d1b683ad822a7ad6088f45c32ea33b3c18cc58`.

## Executed correctness checks

| Check | Status and evidence |
| --- | --- |
| Load MP4 and read duration/FPS | PASS. OpenCV metadata agrees with independent MP4 `mdhd` and `stts` timing tables. |
| Uniform frame count | PASS. Targets 0–5 s select frames 0, 30, 60, 90, 120, 150, exactly six frames. |
| Accurate timestamps | PASS. All 171 decoded times equal frame number / 30, tolerance 1e-9 s; stored times are 0, 1, 2, 3, 4, 5 s. |
| Embedding dimensions/values | PASS. Every stored vector is 512-dimensional, float32, finite and unit normalized. |
| Embedding-to-frame mapping | PASS. Independently decoded source frames were re-embedded in batches of four; stored vectors match within atol=1e-6, rtol=1e-5. |
| Index save/load | PASS. Repeated NPZ loads preserve every array; query commands run after the indexing process has exited. |
| No recomputation on retrieval | PASS. Fresh guarded process forbids image encoding, source decoding and index rebuilding; index-only search still succeeds. |
| Natural-language queries/top five | PASS. Three distinct queries each return exactly five frames. |
| CSV/JSON export consistency | PASS. Report renderer independently checks all numeric and string fields for all 15 original query results. |
| Independent cosine scores | PASS. Explicit float64 dot/(norm×norm) calculation matches stored result scores; maximum absolute discrepancy 8.65e-08. |
| Score ordering | PASS. Descending scores; independently calculated top-five frame ordering matches. |
| Repeated-query consistency | PASS. Each query repeated in another fresh process has identical ranks, timestamps, frame numbers, scores and image filenames. |
| Source locations and saved JPEGs | PASS. All 30 JPEGs (15 original + 15 repeat) are byte-identical to JPEG quality-95 exports of independently decoded source frames. |
| Invalid video path | PASS. CLI exits 2 with a concise Error message and no traceback. |
| Empty/whitespace query | PASS. CLI exits 2 with a concise Error message and no traceback. |
| Index immutability | PASS. Index SHA-256 unchanged after searches. |
| Offline regression suite | PASS. Seven tests, including fractional/subframe sampling, frame caps, stable score ties, invalid input, index/encoder/source mismatch handling. |
| Dependency consistency | PASS. `pip check` reports no broken requirements. |

The independent MP4 parser is intentionally limited to the ordinary nonfragmented sample; it confirms 171 samples of 512 ticks at timescale 15,360, giving 30 FPS and 5.7 s. The container duration is 5.759 s; it is distinct from the video stream duration and the last frame time (5.666667 s).

## Actual retrieval results

Scores below are rounded to nine decimal places for reading; JSON/CSV retain full precision. Image links point to the saved files. Each query also has a separate `_repeat` directory.

### Query 1: cars driving on a road beside trees

Fresh-process wall time: 5.177937 s. [CSV](../../archive/legacy_output/verification_2026-10-27/query_01/results.csv), [JSON](../../archive/legacy_output/verification_2026-10-27/query_01/results.json).

| Rank | Timestamp | Frame | Cosine similarity | Saved image |
| --- | --- | --- | --- | --- |
| 1 | 00:00:05.000 | 150 | 0.259984106 | [output/verification_2026-10-27/query_01/rank_01_frame_00000150.jpg](../../archive/legacy_output/verification_2026-10-27/query_01/rank_01_frame_00000150.jpg) |
| 2 | 00:00:03.000 | 90 | 0.233552396 | [output/verification_2026-10-27/query_01/rank_02_frame_00000090.jpg](../../archive/legacy_output/verification_2026-10-27/query_01/rank_02_frame_00000090.jpg) |
| 3 | 00:00:04.000 | 120 | 0.233262464 | [output/verification_2026-10-27/query_01/rank_03_frame_00000120.jpg](../../archive/legacy_output/verification_2026-10-27/query_01/rank_03_frame_00000120.jpg) |
| 4 | 00:00:02.000 | 60 | 0.232159317 | [output/verification_2026-10-27/query_01/rank_04_frame_00000060.jpg](../../archive/legacy_output/verification_2026-10-27/query_01/rank_04_frame_00000060.jpg) |
| 5 | 00:00:00.000 | 0 | 0.214712381 | [output/verification_2026-10-27/query_01/rank_05_frame_00000000.jpg](../../archive/legacy_output/verification_2026-10-27/query_01/rank_05_frame_00000000.jpg) |

### Query 2: a park with green trees and a walking path

Fresh-process wall time: 5.548220 s. [CSV](../../archive/legacy_output/verification_2026-10-27/query_02/results.csv), [JSON](../../archive/legacy_output/verification_2026-10-27/query_02/results.json).

| Rank | Timestamp | Frame | Cosine similarity | Saved image |
| --- | --- | --- | --- | --- |
| 1 | 00:00:02.000 | 60 | 0.306828260 | [output/verification_2026-10-27/query_02/rank_01_frame_00000060.jpg](../../archive/legacy_output/verification_2026-10-27/query_02/rank_01_frame_00000060.jpg) |
| 2 | 00:00:00.000 | 0 | 0.305544078 | [output/verification_2026-10-27/query_02/rank_02_frame_00000000.jpg](../../archive/legacy_output/verification_2026-10-27/query_02/rank_02_frame_00000000.jpg) |
| 3 | 00:00:01.000 | 30 | 0.304860353 | [output/verification_2026-10-27/query_02/rank_03_frame_00000030.jpg](../../archive/legacy_output/verification_2026-10-27/query_02/rank_03_frame_00000030.jpg) |
| 4 | 00:00:04.000 | 120 | 0.304277837 | [output/verification_2026-10-27/query_02/rank_04_frame_00000120.jpg](../../archive/legacy_output/verification_2026-10-27/query_02/rank_04_frame_00000120.jpg) |
| 5 | 00:00:05.000 | 150 | 0.300197899 | [output/verification_2026-10-27/query_02/rank_05_frame_00000150.jpg](../../archive/legacy_output/verification_2026-10-27/query_02/rank_05_frame_00000150.jpg) |

### Query 3: a person cooking food in a kitchen

Fresh-process wall time: 5.898627 s. [CSV](../../archive/legacy_output/verification_2026-10-27/query_03/results.csv), [JSON](../../archive/legacy_output/verification_2026-10-27/query_03/results.json).

| Rank | Timestamp | Frame | Cosine similarity | Saved image |
| --- | --- | --- | --- | --- |
| 1 | 00:00:03.000 | 90 | 0.083129257 | [output/verification_2026-10-27/query_03/rank_01_frame_00000090.jpg](../../archive/legacy_output/verification_2026-10-27/query_03/rank_01_frame_00000090.jpg) |
| 2 | 00:00:01.000 | 30 | 0.072480023 | [output/verification_2026-10-27/query_03/rank_02_frame_00000030.jpg](../../archive/legacy_output/verification_2026-10-27/query_03/rank_02_frame_00000030.jpg) |
| 3 | 00:00:05.000 | 150 | 0.070627153 | [output/verification_2026-10-27/query_03/rank_03_frame_00000150.jpg](../../archive/legacy_output/verification_2026-10-27/query_03/rank_03_frame_00000150.jpg) |
| 4 | 00:00:02.000 | 60 | 0.064901829 | [output/verification_2026-10-27/query_03/rank_04_frame_00000060.jpg](../../archive/legacy_output/verification_2026-10-27/query_03/rank_04_frame_00000060.jpg) |
| 5 | 00:00:04.000 | 120 | 0.062979780 | [output/verification_2026-10-27/query_03/rank_05_frame_00000120.jpg](../../archive/legacy_output/verification_2026-10-27/query_03/rank_05_frame_00000120.jpg) |

Query 3 is an intentionally unrelated distractor. A kitchen query still returns five park/street frames because this baseline always ranks available candidates and has no abstention threshold. Its lower scores are not calibrated probabilities, and this example does not establish a general threshold for irrelevant queries.

## Changes made during verification

- Fixed incomplete video provenance: `video.py` now exposes FPS, reported frame count, resolution and a duration estimate; `pipeline.py` persists these alongside decoded-frame count and last-frame time. The original last-frame timestamp must not be presented as full video duration. Unit tests now assert 4 s duration and 10 FPS for their generated CFR clip.
- Recorded Torch thread count in encoder metadata so the benchmark configuration is explicit.
- Added `scripts/verify_baseline.py` to reproduce the fresh-process searches, independent timing/cosine/frame checks, error checks and runtime measurements. `scripts/render_verification_report.py` renders the recorded evidence into this report.
- No retrieval or sampling correctness defect was observed in the executed checks. No additional indexing strategies or frontend were implemented.

## Commands and reproduction

Run from the repository root. The weights were already available locally; no dependency installation or model/video download was needed for this verification.

```bash
HF_HUB_OFFLINE=1 .venv/bin/python scripts/verify_baseline.py --output output/verification_2026-10-27
.venv/bin/python scripts/render_verification_report.py --evidence output/verification_2026-10-27/verification.json --report baseline_verification.md
```

The artifact directory must be new. To repeat the experiment, choose another `--output` and pass its `verification.json` to the renderer. Verification is deliberately scoped to the existing CFR sample video and the default model. The test script fails rather than silently substituting a synthetic video if the sample is absent.

The verifier executed these child commands. Full stdout/stderr and individual runtimes are retained in `verification.json`. Exit 2 is expected for the two invalid-input cases.

```bash
# observed exit 0; expected 0; 0.341726 s
HF_HUB_OFFLINE=1 /Users/anguscheng/Downloads/video-search-baseline/.venv/bin/python -m unittest discover -s tests -v
# observed exit 0; expected 0; 0.412158 s
HF_HUB_OFFLINE=1 /Users/anguscheng/Downloads/video-search-baseline/.venv/bin/python -m pip check
# observed exit 0; expected 0; 5.982927 s
HF_HUB_OFFLINE=1 /Users/anguscheng/Downloads/video-search-baseline/.venv/bin/python main.py index --video data/sample.mp4 --interval 1 --batch-size 4 --threads 4 --index output/verification_2026-10-27/index.npz
# observed exit 0; expected 0; 5.177937 s
HF_HUB_OFFLINE=1 /Users/anguscheng/Downloads/video-search-baseline/.venv/bin/python main.py search --index output/verification_2026-10-27/index.npz --query 'cars driving on a road beside trees' --top-k 5 --output output/verification_2026-10-27/query_01
# observed exit 0; expected 0; 5.480970 s
HF_HUB_OFFLINE=1 /Users/anguscheng/Downloads/video-search-baseline/.venv/bin/python main.py search --index output/verification_2026-10-27/index.npz --query 'cars driving on a road beside trees' --top-k 5 --output output/verification_2026-10-27/query_01_repeat
# observed exit 0; expected 0; 5.548220 s
HF_HUB_OFFLINE=1 /Users/anguscheng/Downloads/video-search-baseline/.venv/bin/python main.py search --index output/verification_2026-10-27/index.npz --query 'a park with green trees and a walking path' --top-k 5 --output output/verification_2026-10-27/query_02
# observed exit 0; expected 0; 5.311399 s
HF_HUB_OFFLINE=1 /Users/anguscheng/Downloads/video-search-baseline/.venv/bin/python main.py search --index output/verification_2026-10-27/index.npz --query 'a park with green trees and a walking path' --top-k 5 --output output/verification_2026-10-27/query_02_repeat
# observed exit 0; expected 0; 5.898627 s
HF_HUB_OFFLINE=1 /Users/anguscheng/Downloads/video-search-baseline/.venv/bin/python main.py search --index output/verification_2026-10-27/index.npz --query 'a person cooking food in a kitchen' --top-k 5 --output output/verification_2026-10-27/query_03
# observed exit 0; expected 0; 5.155762 s
HF_HUB_OFFLINE=1 /Users/anguscheng/Downloads/video-search-baseline/.venv/bin/python main.py search --index output/verification_2026-10-27/index.npz --query 'a person cooking food in a kitchen' --top-k 5 --output output/verification_2026-10-27/query_03_repeat
# observed exit 0; expected 0; 5.196454 s
HF_HUB_OFFLINE=1 /Users/anguscheng/Downloads/video-search-baseline/.venv/bin/python scripts/verify_baseline.py --guarded-search search --index output/verification_2026-10-27/index.npz --query 'cars driving on a road beside trees' --no-previews --output output/verification_2026-10-27/index_only_guard
# observed exit 2; expected 2; 3.075039 s
HF_HUB_OFFLINE=1 /Users/anguscheng/Downloads/video-search-baseline/.venv/bin/python main.py index --video output/verification_2026-10-27/missing.mp4 --index output/verification_2026-10-27/invalid.npz
# observed exit 2; expected 2; 2.632505 s
HF_HUB_OFFLINE=1 /Users/anguscheng/Downloads/video-search-baseline/.venv/bin/python main.py search --index output/verification_2026-10-27/index.npz --query '   ' --output output/verification_2026-10-27/empty_query
```

## Extensibility review

The architecture supports future selection methods without replacing the encoder, storage format or ranking code. `Sampler.select(timeline)` returns unique chronological `FrameInfo` values; `metadata()` records the strategy configuration. A visual strategy can receive the video path and feature extractor through its constructor, analyze candidates during selection, and return retained frame identities. `build_index()` validates those identities and applies the same encoder; `search_index()` has no strategy-specific branches. Visual candidate computation is therefore additional work inside the future sampler, not functionality already implemented or tested here.

For controlled comparisons, keep source hashes, encoder/checkpoint, preprocessing, dtype, candidate pool, query set, device, thread count and batch size fixed. Record selection compute costs separately. At D=512 each frame costs 2,064 numeric bytes (2,048 embedding + 8 timestamp + 8 frame number); equal retained counts match payload bytes. Archive headers and metadata vary, so a strict total-file budget requires measuring the actual NPZ size. The larger archive in this run versus the earlier smoke test reflects the added metadata, not more embeddings.

## Remaining limitations and tests not performed

- Retrieval quality, recall/mAP/temporal tolerance metrics and event-boundary accuracy: not evaluated; there are no annotated query intervals and this clip is very short and largely one scene.
- Real variable-frame-rate media, fragmented MP4s, other codecs, long videos, many videos, large indexes and memory scaling: not tested. The offline variable-timestamp test uses synthetic timeline records, not an actual VFR file. Production duration uses frame-count/FPS and is explicitly an estimate for VFR; sampling uses decoded timestamps.
- GPU/CUDA/MPS, other operating systems, dependency versions, checkpoints and batch-size comparisons: not tested. Bitwise agreement is established only within this recorded CPU configuration.
- `ffprobe` cross-validation was not performed because it is not installed. Independent ISO BMFF timing-table parsing was successfully executed instead.
- Missing/corrupt-input and compatibility checks were exercised by the offline suite, but exhaustive corruption recovery, concurrent writes and failure recovery during export are not verified. OpenCV is not an exhaustive video-integrity validator.
- Hardware CPU model retrieval via `sysctl` was unavailable under the sandbox; OS/architecture, inference device and Torch thread count are recorded. No hardware-specific performance claim is made.
- Runtime samples are small; machine load and OS cache state are not controlled. No downloads are included. Source video and model weight storage and preview JPEGs are excluded from the reported index size.

Backend mechanics passed the executed checks. The next research stage is an annotated evaluation protocol followed by additional samplers using the shared pipeline.
