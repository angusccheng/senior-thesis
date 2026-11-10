# Thesis objective and measurement protocol

The primary result is **retrieval accuracy versus actual persistent index storage**.
Indexing time, query latency and resource consumption are additional tradeoffs.
The question is which strategies preserve useful information about queried events
under constrained storage budgets, with what computational costs. The objective
is not simply to choose the fastest or most accurate model.

There are two controlled comparisons:

- **Sampling:** hold encoder/checkpoint, representation, retrieval implementation,
  footage, valid intervals, queries and evaluation rules fixed while changing selection.
- **Representation:** hold footage, eligibility policy, queries, evaluation rules and
  storage budgets fixed; document model, hardware and inference differences explicitly.

The truck example is a qualitative demonstration selected after viewing the clip.
It is not held-out accuracy evidence. No retrieval accuracy can be reported until
queries have annotated ground-truth event intervals.

Current tables: [Results overview](RESULTS_OVERVIEW.md) and
[CSV](../experiments/summary.csv). Refresh with
`.venv/bin/python scripts/summarize_experiments.py`; this reads metadata only.
Historical attempts are labeled in the [registry](../experiments/registry.json).

The second implemented selection method is [diversity sampling](DIVERSITY_SAMPLING.md).
Its first comparison matches retained-frame count; actual index bytes are reported
separately. Retrieval accuracy and strict matched-byte comparisons remain pending.

## What the baseline already measured

The saved development experiment is
[`experiments/nyc_dev_uniform_5s_v3/experiment.json`](../experiments/nyc_dev_uniform_5s_v3/experiment.json).
Its measurements are preserved unchanged. A normalized audit is in
[`experiments/benchmarking_audit_v1/benchmark_record.json`](../experiments/benchmarking_audit_v1/benchmark_record.json).
The audit reads saved timings and file metadata; it does not rerun indexing, decode
video, load OpenCLIP, or inspect the entire five-hour recording.

| Metric | Existing evidence | Gap or qualification |
| --- | --- | --- |
| End-to-end indexing | Fresh-process wall time; separate model-load/core-build values | One indexing repetition per experiment; no reliable variability estimate |
| Indexing stages | Previously no decode/selection/inference split | Historical stages cannot be reconstructed; new timers apply only to future builds |
| Fresh-process query latency | Six samples: three queries, two fresh processes each | Includes imports, model load, fingerprint checks, cropped-video previews and result writes; OS caches not cleared |
| Resident-model latency | Nine samples: three queries × three rounds after one untimed warm-up | Reloads NPZ per query; excludes model load, first fingerprint and previews |
| Process peak RAM | Worker `ru_maxrss`, indexing and fresh queries | Process-lifetime high-water mark; excludes system/other processes; not a warm-query-only memory delta |
| Accelerator memory | CPU run | Unavailable; no accelerator peak captured |
| Storage | Actual NPZ bytes and numeric payload bytes | Optional experiment metadata, corpus videos, shared weights and temporary files must be separate roles |
| Software/inference settings | OS/Python/packages, model/checkpoint hash, fp32, seed, batch size, threads, transforms | Historical CPU model and RAM capacity were not captured |
| Accuracy | No annotated event intervals | Unavailable; do not convert qualitative examples into accuracy claims |

The historical NPZ is **285,146 bytes**, including its embedded retrieval metadata;
its numeric payload is **248,640 bytes**. The adjacent 12,319-byte metadata JSON is
a duplicate experiment report, not required by `search_index`, and is reported
separately. The cropped input is 18,497,430 bytes and the original recording is
5,649,293,214 bytes; both are corpus storage, outside the primary index budget.

The audit pools all **six** saved fresh-process query timings: median **7.418 s**,
sample standard deviation **0.660 s**, range **6.664–8.438 s**. Resident queries have
median **36.535 ms**, sample standard deviation **11.780 ms**, range **28.382–59.656 ms**.
These different scopes must not be compared as if only cache residency differed.
The earlier 7.484 s headline used only the first execution of each query; it remains
unchanged. The new summaries explicitly include repeats and provide per-query values.

Historical indexing wall time is 9.306 s for one completed run. Throughput uses the
actual 598.760 s cropped input divided by wall seconds (source-video hours per wall
hour). It does not count the entire 20,432.595 s recording as processed by this
single-camera development index. The original source window is 600 s; VFR boundary
coverage and playable duration are separately documented.

## Lightweight reusable interface

`video_search/benchmarking.py` supplies dependency-free helpers:

- `StageTimings`: exclusive `perf_counter` stages; decoder iteration timing excludes
  downstream consumer inference. Nested stages are rejected to prevent double-counting.
- `latency_summary(samples)`: raw seconds, count, mean, median, minimum, maximum,
  sample standard deviation and a gated nearest-rank p95.
- `peak_process_ram()`: supported Unix process-lifetime RSS, with explicit units/scope.
- `capture_hardware(device)`: OS, architecture, logical CPU count, CPU-model/RAM
  queries where permitted, and explicit unavailable accelerator/system-memory fields.
- `storage_inventory(files)`: explicit file roles and actual byte counts, duplicate-path
  rejection, unknown rather than zero for unlisted roles or missing required files.
- `baseline_record(...)`: adapter from the current completed-run JSON to the common
  schema below. Future representations use the same metric names/definitions, with
  representation-specific artifact lists and stage hooks.

The existing experiment JSON remains backward compatible. Future executions of
`scripts/run_development_experiment.py` additionally write `benchmark_record.json`
using the same adapter as the historical audit, and capture hardware at run start.
No future indexing representation or sampling strategy is implemented here.

The common JSON structure is:

```text
benchmark_schema_version, experiment_id, evidence_path
source: video/fingerprint, original recording, camera, dataset, valid intervals/protocol
method: sampling parameters, representation, model/checkpoint, dtype, item kind/count,
        embedding dimension, batch size and image preprocessing
repetitions: indexing, per-query fresh/warm repetitions, query count, untimed warm-ups
storage: explicit file roles, measured bytes, primary index total, unavailable roles
timing: indexing totals/stages/throughput, fresh queries, warm queries, per-query summaries
memory: process RSS scope, index/query peaks, unavailable system/accelerator measurements
environment: software and hardware recorded at run time
ground_truth_accuracy: unavailable until annotated evaluation exists
measurement_boundaries: explicit definitions for every operation
```

A metric that cannot be measured is represented by `status: unavailable`, a null
value and an explanation. Structural fields outside the scope of a method may be
null with documented meaning. Null must not be replaced with a fabricated zero.
The adapter is scoped to completed CPU baseline runs; GPU/new-method adapters must
record their own actual providers instead of copying a CPU-run assumption.

## Indexing boundaries and new stage timers

**Primary total:** from a fresh worker launch through creation of the searchable
index and its experiment metadata. This includes model loading and all method-required
preprocessing, decoding, selection, inference, validation and persistence. Record
imports/model initialization separately when feasible, without subtracting them
silently from the primary total.

The existing core `build_index` API receives an already loaded encoder. Its total
therefore excludes model construction/imports. Its JSON sidecar now adds:

- Input fingerprint and dataset-validation time.
- Video probing, first-pass timeline decoding and selection/eligibility time.
- Second-pass selected-frame decoding, separately from RGB-to-PIL conversion.
- Image encoding **including transforms, inference, normalization and CPU transfer**.
- Array construction/validation, checkpoint fingerprinting, NPZ persistence and output hashing.
- Explicit unattributed wall time for provenance assembly and remaining bookkeeping.
- Process-lifetime peak RSS and input-duration/core-wall-time throughput.

Stages are exclusive synchronous wall-clock measurements. Image preprocessing and
pure model inference remain a combined stage because splitting OpenCLIP internals
is outside this lightweight change. They must not be presented as separate measured
values. Source decoding stages include the decoder's RGB conversion, not only codec
kernel time. CPU behavior is regression-tested; future asynchronous accelerator
stages must synchronize the relevant device before and after timing.

Stage timings live in the `.metadata.json` sidecar: persistence completes after the
embedded NPZ metadata has been serialized. The sidecar is an experiment artifact;
recording the timers does not make it a retrieval-required file. Model-load and
whole-worker timing remain separate from the core total. Stage sums should be read
alongside unattributed time; worker/import/initialization overhead is not inferred
by inventing stage values for historical runs.

Common camera cropping and availability labeling are dataset preparation costs and
are already recorded in export/scan manifests. Report these shared costs separately
and declare the input boundary. Do not charge the full seven-feed preparation pass
to only one strategy's ten-minute clip, or quietly treat a strategy-specific scan as
free shared preparation. A future change/diversity method's complete scan or feature
precomputation must occur inside that method's measured construction boundary.

## Query protocol

Record two independent scopes:

1. **Fresh-process end-to-end:** process launch, model/index loading, compatibility
   verification, text encoding, ranking and requested response I/O. Current legacy
   measurements include preview extraction. Call these fresh-process/cached-weights
   measurements; they do not establish a cold filesystem or empty OS page cache.
2. **Resident-model retrieval:** fixed untimed warm-up, then text encoding/index read,
   compatibility checks and top-k ranking. No previews. State whether the index itself
   is resident or reloaded; the current implementation reloads it.

For a future matched comparison, record retrieval-only latency and preview/I/O latency
separately. Do not compare one method with previews against another without them.
The historical pure-cold-without-previews value is unavailable, not reconstructed
by subtracting unrelated timings.

Keep raw observations, query IDs/order, warm-up count, repetition count and workload
composition. Report per-query summaries as well as a pooled fixed-workload summary;
pooled variability includes differences between queries as well as timing noise.
Do not pool unrelated development versions into a single controlled run.

Current reporting policy withholds p95 below **100 timed samples** (nearest-rank
`ceil(0.95*n)`). This minimum gives roughly five observations in the nominal upper
tail; it is a policy threshold, not a guarantee of a precise quantile. A per-query
p95 requires enough samples for that query. No 100-query benchmark was run here.
Suggested future protocol: at least three independent indexing runs, several
fresh-process repetitions per query, and at least 100 warm timings per query if
reporting p95. Fix order/randomization, hardware, background-load policy and cache
conditions in advance, then retain failures/outliers and report variability.

## Persistent-storage accounting

The primary budget is the sum of **all per-dataset files required to retrieve answers**:
embeddings, caption text if used, timestamps, retrieval metadata, vector structures,
lookup tables, learned per-dataset codebooks/adapters and other required auxiliaries.
Content already embedded in NPZ counts. Pure payload bytes are only a breakdown,
not a replacement for the actual persistent-file total.

Explicit roles distinguish `retrieval_required`, `original_video`, `processed_video`,
`shared_model`, `experiment_metadata`, `preview` and `temporary`. Count each resolved
file once. Unlisted model/temporary/preview roles are not inventoried, not zero-cost.
A missing declared retrieval file makes the primary total unavailable.

Original and cropped corpus video storage is separate, as requested. Shared model/
tokenizer weights should also be inventoried separately from a per-video index, with
a total deployment-footprint view when relevant. Model-specific learned **per-dataset**
artifacts cannot be hidden in the shared-model category. This distinction is important
for representation comparisons with different model requirements. Cache-directory
size is not automatically equal to required model storage; caches can contain unused
versions, links and temporary downloads. Historical shared-model bytes remain
unavailable in this audit rather than guessing from the entire cache.

At D=512, current camera indexes use 2072 numeric bytes/frame: 2048 embedding bytes
plus 8 cropped-time, 8 frame-number and 8 original-time bytes. NPZ/JSON overhead adds
storage. Legacy plain-video indexes omit original-time arrays and use 2064 numeric
bytes/frame. Future comparisons must use the same provenance/accounting convention.

## Memory, hardware and unavailable metrics

Peak `ru_maxrss` is process-specific lifetime high-water RSS. On Darwin it is bytes;
on Linux KiB is converted to bytes. It includes model initialization/imports and cannot
be reset into a warm-query-only peak. Use isolated workers to attribute operation-level
peaks; do not sum lifetime peaks as total system memory. Framework/model allocator
peaks, system RAM and process RSS are distinct measurements.

No GPU/MPS inference was performed. Accelerator model/peak, system-wide memory peaks,
and pure warm-phase RAM deltas are unavailable. Future CUDA/MPS providers must document
which allocator/API is measured, when peaks are reset and when operations synchronize.
Do not substitute current allocated memory for a peak or zero for an unsupported API.

The current hardware audit found arm64/macOS and 8 logical CPUs. Sandbox `sysctl`
requests for the actual CPU model and physical RAM capacity were denied, so both
remain unavailable with the captured error. If needed, collect them in a normal
local terminal before future runs:

```bash
sysctl -n machdep.cpu.brand_string
sysctl -n hw.memsize
```

Hardware captured now is labeled **current audit only**. It is not retroactively
asserted as hardware captured during the historical v3 experiment. Historical software,
checkpoint hash, device, seed, transforms, batch size and thread count remain available.

## What was executed for this clarification

```bash
# Metadata/file-stat audit only; use a new output directory when repeating:
.venv/bin/python scripts/audit_benchmarking.py --output experiments/benchmarking_audit_v1

.venv/bin/python -m unittest discover -s tests -v
```

The draft audit was normalized to the same adapter now used by future runs. Historical
experiment/index files were not rewritten. **24 regression tests passed**, including
statistics/missing-data handling, duplicate artifact accounting, nested-timing rejection,
decoder timing that excludes consumer work, stage-report integration, and hardware
permission failures. New stage timers were exercised on tiny synthetic videos with a
deterministic test encoder. They have not yet been profiled in a new real-OpenCLIP run.

No full recording was processed, no model inference benchmark was rerun, no new
indexing method/frontend/dependency was added, and no retrieval-accuracy claim was made.
Before the comparative study, annotate event intervals and freeze a versioned dataset,
query set, eligibility policy, budget convention and measurement protocol. Then run
repeated matched experiments rather than drawing compute conclusions from one run.
