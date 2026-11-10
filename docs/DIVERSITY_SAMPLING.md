# Method 2: diversity-based frame selection

Uniform sampling keeps frames at regular times. Diversity sampling keeps frames
whose OpenCLIP appearances cover different parts of the same clip. Both use the
same OpenCLIP checkpoint, normalized float32 embeddings, NPZ storage, source-time
mapping, eligibility policy, cosine retrieval and top-five preview exporter.
Change-aware selection is not implemented.

## Exact rule

1. Decode the cropped video's timeline and apply the existing availability mask.
2. Encode **every eligible stored frame** with the same OpenCLIP model, in batches.
3. Start with the earliest eligible frame. For each remaining candidate, track
   its smallest cosine distance (`1 - cosine similarity`) to any selected frame.
4. Select the candidate with the largest such distance. Exact ties choose the
   earliest remaining frame. Repeat until the retained-frame budget is reached.
5. Put the retained frames and their existing embeddings in chronological order
   and save the normal index. Discard other candidate embeddings after the build.

This is a farthest-first selection heuristic inspired by
[Gonzalez's clustering algorithm](https://www.cs.columbia.edu/~verma/classes/uml/ref/clustering_minimize_intercluster_distance_gonzalez.pdf).
We do not claim a metric approximation guarantee for cosine distance or a
retrieval-quality guarantee. OpenCLIP appearance diversity can reflect billboard,
lighting or compression differences rather than events useful to a query.

The selection is deterministic for identical candidate embeddings and numerical
settings. It uses float64 selection arithmetic; stored representations remain
float32. If fewer eligible candidates exist than the budget, all are retained.
No query or event labels influence selection. All candidates are chronological
stored frames, with no extra candidate interval or temporal thinning.

## Run and inspect

The named experiment is `diversity_120_broadway46_dev_r01` in
[the catalog](../configs/experiments.json). It uses the same approximately ten-minute
Broadway 46 St clip and three-query workload as `nyc_dev_uniform_5s_v3`.

```bash
.venv/bin/python scripts/run_experiment.py list
.venv/bin/python scripts/run_experiment.py show --id diversity_120_broadway46_dev_r01
# Executes only when output folders and registration do not already exist:
.venv/bin/python scripts/run_experiment.py run --id diversity_120_broadway46_dev_r01
```

For another repetition, copy the catalog entry with a new experiment ID. For a
standalone index using a new output path:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python main.py index \
  --method diversity --max-frames 120 --batch-size 16 --threads 4 \
  --video data/clips/dev/nyc_traffic_000500_001500/broadway_46st_quad_south.mp4 \
  --dataset-manifest data/clips/dev/nyc_traffic_000500_001500/broadway_46st_quad_south.dataset.v2.json \
  --index indexes/my_diversity_run/index.npz
```

Search uses the same `main.py search` command for either method. There are no
candidate embeddings or selection structures needed at query time.

## Display stats and results in the terminal

```bash
# Print the comparison table and refresh the saved CSV/Markdown views:
.venv/bin/python scripts/summarize_experiments.py

# Print this experiment's saved stats and all three top-five query result sets:
.venv/bin/python scripts/run_experiment.py results --id diversity_120_broadway46_dev_r01
```

Both commands read saved measurements without running OpenCLIP or decoding video.
The result display includes model/dimensions, footage path, frames, index bytes,
median construction/query times and sample counts, peak indexing process RAM,
query texts, ranked timestamps, cosine scores and preview filenames. The separate
truck demonstration is outside the experiment's three-query workload.

Executing a fresh named experiment now prints this summary automatically at the
end and still saves its JSON/CSV metrics, ranked results and preview images.
A direct `main.py search` also prints the five timestamps and cosine scores while
saving the corresponding results and images. Terminal commands print text;
open the saved JPEGs to inspect the images.

## Costs and comparison limits

The first comparison matches **120 retained frames**, not exact NPZ bytes.
Embeddings have the same dimension and precision, so their numeric payloads match;
metadata length can change total file size. Use the actual byte counts in
[Results overview](RESULTS_OVERVIEW.md), not frame counts as a substitute for bytes.
Strict matched-byte budget sweeps remain future work.

All candidate decoding, inference and feature selection occur inside measured
index construction. The metadata reports `candidate_frames_encoded`; the
`diversity_selection` stage measures the greedy selection separately from image
encoding. The runner's independent correctness checks happen after construction
and are not included in the indexing measurement. They re-encode candidates to
check the selection and saved features, then verify source timestamps, ranking,
preview images, repeated fresh-process results and resident-model latency.

Image memory is bounded by the batch size. Candidate feature storage is O(ND),
and selection costs O(NKD) with O(N) distance bookkeeping, without an N×N matrix.
This is appropriate for the current development clip; full-recording performance
has not been evaluated. No full-length crop or index is produced by this demo.

Qualitative retrieval results demonstrate functionality. Event annotations,
held-out queries and repeated builds are still needed to compare retrieval
quality and estimate performance variability. A single run per method does not
establish a winner.

## Executed development test

The ten-minute Broadway 46 St experiment completed successfully. All nine
runner verification checks passed; the full unit/regression suite passed 44 tests.
No full recording was processed.

[Raw checks and all three query result sets](../experiments/diversity_120_broadway46_dev_r01/experiment.json) · [Normalized metrics](../experiments/diversity_120_broadway46_dev_r01/benchmark_record.json) · [The 120 retained frames and both timestamps](../experiments/diversity_120_broadway46_dev_r01/retained_frames.csv)

| Measurement | Observed value |
| --- | ---: |
| Video duration (s) | 598.76 |
| Eligible candidates encoded | 843 |
| Retained frames | 120 |
| Embedding dimensions | 512 |
| Numeric payload (bytes) | 248640 |
| Index file (bytes) | 286178 |
| Fresh-process indexing (s) | 41.741 |
| Greedy selection stage (s) | 0.012238 |
| Median fresh query including previews (s; 6 observations) | 8.658 |
| Median resident query without previews (ms; 9 observations) | 34.048 |

The existing uniform index is 285,146 bytes; the diversity index is 286,178 bytes.
Both retain 120 frames and have a 248,640-byte numeric payload. This demonstrates
why retained-frame matching must not be described as exact storage-budget matching.
The uniform build was measured previously; controlled repeated build measurements
under current conditions remain necessary for a reliable cost comparison.

Additional qualitative query (outside the fixed three-query latency workload):

```bash
HF_HUB_OFFLINE=1 .venv/bin/python main.py search \
  --index indexes/diversity_120_broadway46_dev_r01/index.npz \
  --query "A large white box truck in the crosswalk." \
  --output results/retrieval/diversity_white_box_truck
```

This command was executed once; choose a fresh output path to repeat it.

| Rank | Clip timestamp | Cosine similarity | Saved image |
| --- | --- | ---: | --- |
| 1 | 00:04:52.372 | 0.278442651 | [Frame](../results/retrieval/diversity_white_box_truck/rank_01_frame_00000423.jpg) |
| 2 | 00:04:56.355 | 0.269711494 | [Frame](../results/retrieval/diversity_white_box_truck/rank_02_frame_00000429.jpg) |
| 3 | 00:05:26.405 | 0.266559958 | [Frame](../results/retrieval/diversity_white_box_truck/rank_03_frame_00000468.jpg) |
| 4 | 00:05:18.438 | 0.254632741 | [Frame](../results/retrieval/diversity_white_box_truck/rank_04_frame_00000458.jpg) |
| 5 | 00:05:54.422 | 0.254482895 | [Frame](../results/retrieval/diversity_white_box_truck/rank_05_frame_00000510.jpg) |

Visual inspection: rank 1 has a prominent white van and a more distant truck;
rank 2 contains the familiar box truck occupying the striped roadway. Scores are
not probabilities, and the larger rank-1 score is not evidence of better semantic
correctness. Neither this demonstration nor any of the three workload queries
has annotated accuracy yet.
