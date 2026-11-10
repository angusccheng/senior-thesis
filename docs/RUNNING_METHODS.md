# Run the two indexing methods

Run commands from the project folder. The video, model cache and two saved indexes
already exist on the development machine. GitHub contains code and small research
records; videos, NPZ indexes, weights and preview images remain local.

## What each method does

| Method | Frame selection | OpenCLIP work for the existing clip |
| --- | --- | --- |
| Uniform | First stored frame at/after each 5-second target | Encode the 120 selected eligible frames |
| Diversity | Start with the earliest eligible frame, then repeatedly select the candidate farthest from its closest selected frame in embedding space | Encode all 843 eligible frames; retain 120 |

Both use OpenCLIP ViT-B-32 / laion2b_s34b_b79k, CPU, float32, the same cropped
Broadway 46 St clip, eligibility policy, source-time mapping, storage format and
cosine retrieval. Diversity adds selection work; it does not change the search
algorithm. No change-aware method is implemented.

An OpenCLIP embedding is a numerical representation of an image or text. Images
and queries occupy a shared embedding space. Search encodes your text, calculates
cosine similarities with saved frame embeddings, and returns the five highest
scores. It does not regenerate the saved image embeddings.

## 1. See existing experiments and their saved stats

```bash
.venv/bin/python scripts/run_experiment.py list
.venv/bin/python scripts/summarize_experiments.py
```

The first command shows method, footage path, settings and status. The second
prints the measured comparison and regenerates `experiments/summary.csv` and
`docs/RESULTS_OVERVIEW.md` from saved records. Neither runs OpenCLIP.

Print each experiment's saved stats and all three configured query result sets:

```bash
.venv/bin/python scripts/run_experiment.py results --id nyc_dev_uniform_5s_v3
.venv/bin/python scripts/run_experiment.py results --id diversity_120_broadway46_dev_r01
```

## 2. Try the same new query on each saved index

Uniform:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python main.py search \
  --index indexes/nyc_dev_uniform_5s_v3/index.npz \
  --query "A large white box truck in the crosswalk." \
  --output results/retrieval/uniform_truck_walkthrough
```

Diversity:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python main.py search \
  --index indexes/diversity_120_broadway46_dev_r01/index.npz \
  --query "A large white box truck in the crosswalk." \
  --output results/retrieval/diversity_truck_walkthrough
```

These commands perform real text-query inference against the existing indexes.
They print ranked timestamps and cosine scores. Each output folder contains
`results.csv`, `results.json` and five ranked JPEGs. Open the JPEGs to inspect
what was retrieved. `HF_HUB_OFFLINE=1` uses cached weights without contacting
Hugging Face; the model must already be cached.

Use a fresh output folder on every execution; existing results are protected.
These individual searches do not add latency observations to the experiment
comparison table. Its numbers belong to its saved, repeated query workload.

## 3. Rebuild either method and record a complete new experiment

In [configs/experiments.json](../configs/experiments.json), copy the corresponding
entry and change only its ID and label for a repetition:

- Copy `nyc_dev_uniform_5s_v3` to a new entry with ID `uniform_5s_broadway46_dev_r02`.
- Copy `diversity_120_broadway46_dev_r01` to a new entry with ID `diversity_120_broadway46_dev_r02`.

Keep the same footage, manifest, queries, batch size and threads. The copied
uniform entry retains `interval_seconds: 5.0`; the diversity entry retains
`max_frames: 120`. The new entries must be inside the catalog's `experiments`
array. Then run either entry:

```bash
.venv/bin/python scripts/run_experiment.py run --id uniform_5s_broadway46_dev_r02 --dry-run
.venv/bin/python scripts/run_experiment.py run --id uniform_5s_broadway46_dev_r02

.venv/bin/python scripts/run_experiment.py run --id diversity_120_broadway46_dev_r02 --dry-run
.venv/bin/python scripts/run_experiment.py run --id diversity_120_broadway46_dev_r02
```

`--dry-run` prints settings and the underlying command without computing anything.
The actual run builds a new index, executes the three queries twice each in fresh
processes, measures three resident-model rounds, verifies selection/timestamps/
rankings/previews, prints the stats and query results, and registers successful
measurements in the comparison table. Each method measures one index build per
run. Repetitions need new IDs.

Artifacts use the experiment ID consistently:

```text
indexes/<experiment_id>/index.npz
results/retrieval/<experiment_id>/query_01/     # also query_02 and query_03
experiments/<experiment_id>/                  # config, metrics, checks and logs
```

The runner refuses to overwrite existing experiments. None of these commands
processes the five-hour recording; they index the existing development crop.

## 4. Interpret the results

- **Clip timestamp:** where to seek in the approximately ten-minute cropped video.
  `source_seconds` maps to the original recording through the saved timeline.
- **Cosine score:** image/text similarity; larger values rank first for that query.
  A score of 0.27 is not 27% accuracy. Check the image and context in the video.
- **Top-five results:** five frames, which may all depict the same event. They do
  not necessarily represent five different event occurrences. The system retrieves
  frames; it does not currently predict event start/end intervals.
- **Index bytes:** actual persistent retrieval index size, including embedded
  metadata. Both methods retain 120 frames, but metadata makes their total byte
  counts slightly different. This is not yet an exact matched-byte comparison.
- **Build seconds:** fresh-process construction including startup and required
  candidate processing. Diversity pays for all candidate embeddings even though
  most are discarded. One build cannot establish timing variability.
- **Fresh query seconds:** startup/model loading, search, previews and result I/O.
  **Warm query milliseconds:** resident model, text encoding/ranking and NPZ load;
  excludes model startup and previews. Compare methods within the same boundary.
- **n:** timing observations. Six fresh timings are two repeats of three queries;
  nine warm timings are three rounds of three queries. They are not six/nine
  independent footage samples. The two historical builds occurred at different
  times, so small latency differences do not establish a method advantage.
- **Verification PASS:** the backend's mathematical/storage/timestamp/image
  checks passed. It does not mean the semantic retrieval is accurate.
- **Hit@5 pending:** manually annotated event intervals are still needed to
  measure whether any of the top five frames falls inside a correct event.

The truck is a qualitative development example, not held-out accuracy evidence.
The next evaluation step is to annotate events and queries on this clip before
claiming that either method has better retrieval quality.

[Current measurements](RESULTS_OVERVIEW.md) · [Diversity details](DIVERSITY_SAMPLING.md)
