# Dataset preparation

The original recording remains unchanged at the absolute path in
[`configs/nyc_traffic.json`](../configs/nyc_traffic.json). It is a 5,649,293,214-byte
MOV, 2436×1568 pixels, 20,432.595 seconds long, with 28,835 stored frames. Average
stored FPS is about 1.4112; the nominal 60 FPS metadata must not be treated as a
camera update rate. MP4 and MOV inputs are both supported.

The existing camera rectangles are approved and reused unchanged. Their exact
coordinates, per-camera diagnostic ROIs and source metadata are in the configuration.
The old preparation report, sample links and detailed initial coordinate-selection
explanation are preserved in [DATA_PREPARATION_LEGACY.md](DATA_PREPARATION_LEGACY.md).

## Files and source protection

- `data/originals/recordings.json` references the external original. It does not copy,
  alter or replace the MOV.
- `data/clips/smoke/nyc_traffic_30_60/` links to all seven preserved short samples.
- `data/clips/dev/nyc_traffic_000500_001500/` contains the three development MP4s,
  per-frame timestamp CSVs, export manifest, crop snapshot and verification evidence.
- `data/metadata/nyc_traffic/availability_scan_v1/` contains full-source metric CSVs,
  black/maintenance review images and explicit review decisions.
- `data/metadata/nyc_traffic/availability_v2/` contains the current availability
  protocol, interval CSV, per-camera JSON reports and update-rate summaries.
- `data/processed/` is reserved for future full-length camera exports; none were made.

Every output directory must be new. Completed outputs and earlier report versions
are preserved, including a superseded availability v1 and earlier baseline runs.
Old `output/` paths resolve through a compatibility link to `archive/legacy_output/`.
The source's size, mtime and sampled first/last-MiB fingerprint are checked; no full
original-file checksum was computed. This is explicitly a sampled identity check,
not a cryptographic integrity claim about every original byte.

## Requirements and recording setup

The existing Python requirements suffice; no new Python dependencies were added.
FFmpeg/ffprobe 9.0.2 with libx264 is installed locally.

```bash
brew install ffmpeg                          # macOS
# Ubuntu/Debian alternative: sudo apt install ffmpeg
.venv/bin/python -m pip install -r requirements.lock.txt

# For another source; choose a new config and review its rectangles:
.venv/bin/python prepare_data.py init --source '/absolute/path/recording.mov' \
  --feeds 7 --config configs/new_recording.json
.venv/bin/python prepare_data.py preview --config configs/new_recording.json \
  --at 30 --output data/metadata/new_recording/preview
```

Coordinates are `[x,y,width,height]` in coded pixels, top-left origin, half-open
rectangles; use even values. `null` crops are excluded. Existing NYC crops must not
be recalculated merely because camera imagery or PTZ orientation changes.

## Executed development export and validation

The first three prioritized cameras share requested source interval `[300,900)` s.
This exact export command was executed:

```bash
.venv/bin/python prepare_data.py export --config configs/nyc_traffic.json \
  --camera broadway_46st_quad_south --camera broadway_43st \
  --camera central_park_west_72st --start 00:05:00 --duration 600 \
  --output data/clips/dev/nyc_traffic_000500_001500

.venv/bin/python scripts/verify_preprocessing_samples.py --config configs/nyc_traffic.json \
  --samples data/clips/dev/nyc_traffic_000500_001500 --review-dir review_v2
```

Each export has 843 frames and playable duration **598.760 s**, despite a requested
600-second source window. The first retained source frame is at **301.738333333 s**;
the last is at **898.531666667 s**. No boundary frames were synthesized. The MP4
encoder's last-frame hold duration is not guaranteed to stop exactly at the requested
source end. Always use the timestamp CSV to map observations, not playable file length.

| Camera | Resolution | Frames | Playable duration | Average stored FPS |
| --- | --- | ---: | ---: | ---: |
| Broadway @ 46 St Quad South | 592×356 | 843 | 598.760 s | 1.407910 |
| Broadway @ 43 St | 592×376 | 843 | 598.760 s | 1.407910 |
| Central Park West @ 72 St | 592×372 | 843 | 598.760 s | 1.407910 |

The ffprobe average is `21075/14969`. The first-to-last-frame pair rate uses a
slightly different denominator. Beginning, middle and end frames from each camera
were compared with independently decoded original crops; all passed the lossy
H.264 pixel tolerance. All encoded frame times passed the CSV comparison within
0.333334 microseconds. The [review sheet](../data/clips/dev/nyc_traffic_000500_001500/review_v2/contact_sheet.jpg)
and [verification JSON](../data/clips/dev/nyc_traffic_000500_001500/review_v2/verification.json)
are saved. The reviewed clips contain only the intended camera imagery.

## Timeline and resource contract

FFmpeg seeks near the requested start with input `-ss`, then accurately decodes
from a preceding keyframe. Crops retain source PTS in `[start,end)` and rebase the
first retained frame to zero with `setpts=PTS-STARTPTS`. `-fps_mode passthrough`,
filter time base and a microsecond MP4 track time base preserve irregular spacing;
there is no FPS resampling or frame interpolation. Audio is omitted.

Each `CAMERA.timeline.csv` records `frame`, `source_seconds`, and `cropped_seconds`.
For these single-interval exports:

```text
source_seconds ≈ 301.738333333 + cropped_seconds
```

The CSV is authoritative for joining individual frames. The NPZ index also stores
selected original-recording timestamps explicitly, rather than assuming constant
FPS. Original container PTS is `source_seconds + format_start_time` (zero here).
Screen-recording time is not calibrated sensor capture time; feeds may have different
latencies and burned-in clock offsets.

Exports are sequential FFmpeg passes with bounded decoding buffers. Analysis uses
small grayscale mosaics and streaming CSVs. No workflow loads the five-hour recording
into RAM. Full-source availability analysis decodes every stored frame once but
**does not export full-length cropped videos**. Input keyframe/GOP layout determines
seek overhead; whole-source metric CSVs occupy disk, not a collection of RGB frames.

## Executed availability and review workflow

```bash
.venv/bin/python scripts/analyze_availability.py --config configs/nyc_traffic.json \
  --output data/metadata/nyc_traffic/availability_scan_v1

.venv/bin/python scripts/review_availability.py --config configs/nyc_traffic.json \
  --scan data/metadata/nyc_traffic/availability_scan_v1/scan.json \
  --output data/metadata/nyc_traffic/availability_scan_v1/review

# Original uncertain candidates were rendered with the earlier availability v1:
.venv/bin/python scripts/extract_uncertain_reviews.py --config configs/nyc_traffic.json \
  --scan data/metadata/nyc_traffic/availability_scan_v1/scan.json \
  --availability data/metadata/nyc_traffic/availability_v1/availability.json \
  --output data/metadata/nyc_traffic/availability_v1/manual_review

# Refine the explicitly observed service-card interval from metrics + source images:
.venv/bin/python scripts/refine_service_review.py

# Apply the saved explicit visual review decisions, including cursor and service card:
.venv/bin/python scripts/finalize_dataset.py --config configs/nyc_traffic.json \
  --scan data/metadata/nyc_traffic/availability_scan_v1/scan.json \
  --decisions data/metadata/nyc_traffic/availability_scan_v1/review/review_decisions_v2.json \
  --clips data/clips/dev/nyc_traffic_000500_001500 \
  --output data/metadata/nyc_traffic/availability_v2 --manifest-suffix .dataset.v2.json

.venv/bin/python scripts/summarize_update_rates.py \
  --scan data/metadata/nyc_traffic/availability_scan_v1/scan.json \
  --availability data/metadata/nyc_traffic/availability_v2/availability.json \
  --output data/metadata/nyc_traffic/availability_v2/update_rates.json
```

The first report version and both review-decision versions remain preserved.
For a new dataset/version, use new output names and matching `--manifest-suffix`.
`refine_service_review.py` is a dataset-specific refinement of the card visually
observed near source 9317 s, not a general service-card classifier. Explicit review
is required before confirming new unavailable intervals. Do not reuse these review
decisions on a different source fingerprint or different crop geometry.

The latest findings and thresholds are in [CAMERA_AVAILABILITY.md](CAMERA_AVAILABILITY.md).
Default eligibility excludes **confirmed unavailable** intervals. Suspected freezes,
static scenes and ambiguous dark/blank content stay in the dataset with review flags.
A more conservative comparison may also exclude uncertain intervals, but all methods
must share and record the same explicit policy/version.

## Small diagnostics and future exports

The original short diagnostic still works:

```bash
.venv/bin/python prepare_data.py diagnose --config configs/nyc_traffic.json \
  --camera broadway_43st --start 00:05:00 --duration 30 \
  --output experiments/new_update_window
```

This diagnostic uses 160×90 grayscale, while the full-source audit uses 80×48.
Do not directly compare threshold-derived rates across different analysis scales
without a sensitivity study. Use the current full-source summaries consistently.

`--profile smoke` requests 30 source seconds; `--profile dev` requests 300 source
seconds; explicit `--duration 600` requests ten minutes. `--end` supports an exclusive
end time and is mutually exclusive with duration. `--dry-run` prints commands.
Full export support remains available after crop approval but **was not invoked**.
No full-length export command is needed for the current experiment.

## Index/retrieval reproduction

See [DEVELOPMENT_VERIFICATION.md](DEVELOPMENT_VERIFICATION.md) for the guarded
fresh-process experiment commands and [the root README](../README.md) for ordinary
index/search commands. Always pass the prepared camera's `.dataset.v2.json` manifest
for research indexing. It pins the clip checksum, crop/configuration, original source
identity, source-time mapping and availability report/policy. All future representations
can reuse this same dataset context and mask without changing the footage.
