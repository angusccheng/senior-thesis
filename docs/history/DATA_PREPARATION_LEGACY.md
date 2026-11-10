> Historical preparation report from before crop approval and the full availability scan. Current instructions and findings are in DATA_PREPARATION.md and CAMERA_AVAILABILITY.md. All referenced legacy artifacts remain available through output/.

# Reproducible camera-video preparation

This workflow is separate from OpenCLIP. `encoder.py`, `samplers.py`, `pipeline.py`,
`main.py`, and the retrieval logic were not changed. It accepts MP4 or MOV sources,
creates independent video-only H.264 MP4s, and records each output frame's source
presentation timestamp. There is no frontend or new indexing strategy.

## Current recording and review status

The supplied file is accessible:

```text
/Users/anguscheng/Desktop/Screen Recording 2026-10-30 at 4.46.46 PM.mov
```

The space before `PM` is U+202F (narrow no-break space). The exact path is already
stored in [configs/nyc_traffic.json](../../configs/nyc_traffic.json), so downstream commands
do not need to type it again. The source is read-only throughout this workflow.

| Source property | Observed value |
| --- | --- |
| File size | 5,649,293,214 bytes |
| Coded image size | 2436 × 1568 pixels |
| Video duration | 20,432.595 s = 05:40:32.595 |
| Stored video frames (metadata) | 28,835 |
| Average stored-frame rate | 5767000/4086519, approximately 1.4112 FPS |
| Nominal `r_frame_rate` | 60/1; **not** the observed camera update rate |
| Video time base | 1/600 s |
| Codec / pixels | H.264 / yuv420p |
| Source format / video start | 0 / 0 s |

This recording is variable-frame-rate. Do not assume it is 30 or 60 stored frames
per second. Source stream/container metadata is embedded in the configuration.
The default source identity check hashes only file size plus the first/last MiB;
this is a bounded-I/O fingerprint, **not a full-file integrity checksum**. Size,
mtime and that fingerprint were unchanged after sample exports and verification.

**Only short samples were exported. Crop approval is pending.** The configuration
has `"crops_verified": false`; commands requesting more than 600 seconds are blocked.
No full-length or 5–10-minute real-recording exports have been run. The development
and full commands below are for use after reviewing the short samples. Do not mark
the crops verified until you have checked them.

## Review the proposed crops

The seven cameras occupy three columns, with one camera in the bottom row. These
rectangles were selected from the representative source frame at 30 seconds and
visually checked against another source frame at four hours. They exclude browser
headings, feed clock bands and black side padding, while retaining burned-in DOT
marks. They do not recover image areas already absent from the screen recording.

Coordinates are `[x, y, width, height]`, in unscaled coded pixels, measured from the
top-left corner. Rectangles are half-open: `[x, x+width) × [y, y+height)`. No automatic
rotation or resizing is applied. All four values must be even for yuv420p encoding;
invalid/out-of-bounds crops fail rather than silently rounding.

| Camera ID | Feed label | Proposed rectangle |
| --- | --- | --- |
| `5ave_57st` | 5 Ave @ 57 St | `[116, 198, 592, 370]` |
| `central_park_west_72st` | Central Park West @ 72 St | `[924, 196, 592, 372]` |
| `broadway_43st` | Broadway @ 43 St | `[1732, 192, 592, 376]` |
| `broadway_46st_quad_south` | Broadway @ 46 St - Quad South | `[116, 696, 592, 356]` |
| `5ave_34st` | 5 Ave @ 34 St | `[924, 676, 592, 376]` |
| `7ave_43st_ptz` | 7 Ave @ 43 St - 64.186 - PTZ | `[1732, 676, 592, 376]` |
| `central_park_72nd_post37` | Central Park @ 72nd St Post 37 | `[116, 1132, 592, 406]` |

Start with the [sample review sheet](../../archive/legacy_output/nyc_traffic/smoke_30_60/review/contact_sheet.jpg).
Then open the independent MP4s:

- [5 Ave @ 57 St](../../archive/legacy_output/nyc_traffic/smoke_30_60/5ave_57st.mp4)
- [Central Park West @ 72 St](../../archive/legacy_output/nyc_traffic/smoke_30_60/central_park_west_72st.mp4)
- [Broadway @ 43 St](../../archive/legacy_output/nyc_traffic/smoke_30_60/broadway_43st.mp4)
- [Broadway @ 46 St](../../archive/legacy_output/nyc_traffic/smoke_30_60/broadway_46st_quad_south.mp4)
- [5 Ave @ 34 St](../../archive/legacy_output/nyc_traffic/smoke_30_60/5ave_34st.mp4)
- [7 Ave @ 43 St](../../archive/legacy_output/nyc_traffic/smoke_30_60/7ave_43st_ptz.mp4)
- [Central Park @ 72nd St Post 37](../../archive/legacy_output/nyc_traffic/smoke_30_60/central_park_72nd_post37.mp4)

Additional inspection artifacts:

- [Full source frame at approximately 30 s](../../archive/legacy_output/nyc_traffic/crop_review_30s/source.png)
- [Coordinates/crop outlines at approximately 30 s](../../archive/legacy_output/nyc_traffic/crop_review_30s/coordinates.png)
- [Full source frame at approximately four hours](../../archive/legacy_output/nyc_traffic/crop_review_4h/source.png)
- [Export manifest, exact FFmpeg commands and output hashes](../../archive/legacy_output/nyc_traffic/smoke_30_60/manifest.json)
- [Pixel/timestamp verification evidence](../../archive/legacy_output/nyc_traffic/smoke_30_60/review/verification.json)

The preview command records the requested time; its PNG is the first decodable
frame at/after that time. Use the export mapping CSV for precise timestamps.

## Installation

FFmpeg and ffprobe were initially missing. `brew install ffmpeg` was executed
successfully; the tested installation is FFmpeg 9.0.2. Both executables must be on
PATH, and the build must include the `libx264` encoder. Existing Python dependencies
(NumPy, Pillow and OpenCV) suffice; no new Python packages were installed.

```bash
# macOS, with Homebrew already installed:
brew install ffmpeg

# Ubuntu/Debian alternative (not executed here):
sudo apt update
sudo apt install ffmpeg

ffmpeg -version
ffprobe -version
ffmpeg -encoders
```

For other systems, use the packages linked from the
[official FFmpeg download page](https://ffmpeg.org/download.html). This workflow
uses `-enc_time_base:v filter` and `-fps_mode passthrough`; use a recent FFmpeg build
if an older distribution version does not recognize these options.

## Exact workflow commands

Run commands from the project root with `.venv/bin/python`. Every output directory
must be new. Reruns refuse to overwrite an experiment. Source files are never
replaced or modified. Paths with spaces are passed as subprocess arguments, not
constructed as executable shell strings.

### Initialize a new configuration

This command was executed for the supplied recording (the existing config now
also contains the proposed rectangles above):

```bash
.venv/bin/python prepare_data.py init \
  --source '/Users/anguscheng/Desktop/Screen Recording 2026-10-30 at 4.46.46 PM.mov' \
  --feeds 7 --config configs/nyc_traffic.json
```

For a different recording, choose a new configuration path:

```bash
.venv/bin/python prepare_data.py init \
  --source '/absolute/path/to/recording.mp4' \
  --feeds 7 --config configs/new_recording.json
```

New cameras have `"crop": null`. Generate a coordinate preview, open the original
PNG at native scale in an image editor, read the upper-left `(x,y)` and lower-right
`(right,bottom)` corners, then enter `[x,y,right-x,bottom-y]` in JSON. Null crops are
excluded. Use separate stable camera IDs and descriptive labels. Never infer a
uniform grid from video dimensions alone; browser borders, headings and letterbox
padding change the actual feed rectangles.

`init --hash-source` optionally computes a full SHA-256, reading the entire file
once without decoding it. `--verify-full-hash` on subsequent commands verifies that
optional checksum and also reads the entire file. Neither flag was used for the
5.6 GB recording, keeping ordinary short-clip preparation bounded in I/O. The default
checks only the sampled fingerprint, size, and key stream metadata. To relocate a
source, update `source.path` to the new file; it must match those identity checks.
Relative source paths resolve against the configuration directory.

### Inspect and adjust regions

These commands were executed:

```bash
.venv/bin/python prepare_data.py preview --config configs/nyc_traffic.json \
  --at 30 --output output/nyc_traffic/crop_review_30s
.venv/bin/python prepare_data.py preview --config configs/nyc_traffic.json \
  --at 04:00:00 --output output/nyc_traffic/crop_review_4h
```

Each directory contains the unscaled `source.png`, `coordinates.png`, individual
camera crop PNGs, and a configuration/command snapshot. Check multiple time points
for scrolling, resizing, moved windows, or PTZ changes. PTZ scene changes inside a
stationary player are not changes to the screen crop geometry.

### Export short smoke-test samples

This exact command was executed for all seven cameras:

```bash
.venv/bin/python prepare_data.py export --config configs/nyc_traffic.json \
  --start 30 --profile smoke --output output/nyc_traffic/smoke_30_60
```

`smoke` requests a 30-second source interval. To select only certain cameras or an
arbitrary interval, use, for example (not executed):

```bash
.venv/bin/python prepare_data.py export --config configs/nyc_traffic.json \
  --camera 5ave_57st --camera broadway_43st \
  --start 00:12:10 --end 00:12:40 --output output/nyc_traffic/smoke_12m10
```

`--start`, `--end` and `--duration` accept seconds, `MM:SS`, or `HH:MM:SS` with
fractional seconds. End is exclusive. `--end` and `--duration` are mutually exclusive;
explicit duration/end overrides the profile default. Out-of-range requests fail;
there is no silent truncation. A window containing no decoded frames fails clearly.

Use `--dry-run` to print exact FFmpeg commands without creating exports. Input-side
`-ss` seeks to a nearby keyframe and decodes only the requested neighborhood; it
avoids decoding the preceding hours. FFmpeg must still decode from a preceding
keyframe for accurate seeking. Extremely long GOPs or poorly indexed media can
make that neighborhood larger. Each selected camera is processed sequentially in
its own FFmpeg pass, trading additional decoding for bounded memory and simplicity.

### Prepare development clips after crop review

These commands are implemented but **have not been run on the real recording**:

```bash
# Five-minute source interval starting at five minutes:
.venv/bin/python prepare_data.py export --config configs/nyc_traffic.json \
  --start 00:05:00 --profile dev --output output/nyc_traffic/dev_5m_10m

# Ten-minute source interval, with the same crop coordinates:
.venv/bin/python prepare_data.py export --config configs/nyc_traffic.json \
  --start 00:05:00 --duration 600 --output output/nyc_traffic/dev_5m_15m
```

Select development intervals containing live feeds; black segments should be
explicit quality annotations, not unrecorded removals that alter the timeline.
Keep a configuration snapshot per dataset version if adjusting crops.

### Full-length exports only after verification

Do not run this yet. After reviewing the short samples and accepting the coordinates,
set `"crops_verified": true` in the configuration. This boolean controls the explicit
block on requests longer than ten minutes. A dry run can then show the future job:

```bash
.venv/bin/python prepare_data.py export --config configs/nyc_traffic.json \
  --profile full --output output/nyc_traffic/full_verified --dry-run

# Future actual export, once crops are verified and disk space is available:
.venv/bin/python prepare_data.py export --config configs/nyc_traffic.json \
  --profile full --output output/nyc_traffic/full_verified
```

Omitting `--start` starts at zero. Full exports from later start times run to video
end. Encoding, timestamp validation, output hashing and MP4 faststart relocation
are sequential disk operations; full exports require runtime and storage that have
not been measured here. CRF 18/preset medium/4 encoder threads are configurable in
JSON. Use identical encoding settings for strategy comparisons. Audio is omitted
because this is a screen recording of independent visual feeds.

## Timeline contract and variable-frame-rate boundaries

No forced output FPS, temporal subsampling, frame interpolation, duplicate removal
or blackout deletion is applied. `-copyts -start_at_zero` expresses source PTS relative
to source `format.start_time`; `trim` retains decoded frame timestamps in `[start,end)`.
Cropping preserves their time differences. `setpts=PTS-STARTPTS` rebases the first
retained frame to zero for compatibility with existing indexing. `-fps_mode passthrough`
and the filter time base preserve irregular spacing; MP4 timestamps use microseconds.
B-frames are disabled in the cropped output, making packet/frame mapping unambiguous.

Each camera has a `CAMERA.timeline.csv` with `frame`, `source_seconds` and
`cropped_seconds`. The manifest stores the first retained source timestamp, source
metadata/identity, requested range, actual output metadata, crop, command, checksum,
frame count and timestamp validation error. The relationship is:

```text
source_seconds = first_retained_source_seconds + cropped_seconds
original_container_pts_seconds = source_seconds + source.format_start_time
```

The CSV source times come from integer FFmpeg `showinfo` PTS and a rational time
base, not its rounded `pts_time` display. Every encoded packet timestamp is checked
with ffprobe against the corresponding CSV value (tolerance 2 microseconds).

**Requested interval duration is distinct from playable file duration for sparse
VFR sources.** The smoke request is `[30,60)` seconds. It contains 44 frames with
source times 30.783333333 through 59.566666667. Each cropped file starts at zero
and is approximately **28.816666 seconds** long. No earlier held frame is invented
at the requested boundary, and the encoder's final frame duration is not an exact
copy of the source's held-frame duration. Thus source frame timestamps and their
spacing are preserved; the exact displayed coverage of the two clip boundaries
is not guaranteed. This policy is intentional and recorded rather than disguising
sparse source timing as a 30 FPS, exactly 30-second movie. If exact wall-clock
playback windows become a requirement, implement an explicit boundary-hold policy
and mark any synthesized boundary frames separately before evaluation.

For example, a retrieval time of 10 s in these samples maps to source time
40.783333333 s, not 40 s. For an indexed frame, join by its cropped timestamp to the
CSV; do not infer source positions from nominal FPS. Do not treat the screen
recording's creation timestamp as ground-truth camera capture time. Different camera
feeds can have distinct latency, clock offsets and stale content even when recorded
simultaneously. Removing the burned-in clocks from visual inputs does not resolve
that synchronization uncertainty; original snapshots retain them for inspection.

The FFmpeg option behavior is described in the official
[seeking/timestamp documentation](https://ffmpeg.org/ffmpeg.html) and
[crop/showinfo filter documentation](https://ffmpeg.org/ffmpeg-filters.html).

## Effective camera-update and blackout diagnostic

The diagnostic examines **every stored frame**, within each crop's optional
`diagnostic_roi`, at 160×90 grayscale using area downsampling. The ROI is relative
to the crop. The supplied configuration excludes a 16-pixel inner border and the
lower region containing the DOT mark so logos do not masquerade as updates. It
computes consecutive-frame mean absolute difference (MAD) and the fraction of
pixels whose intensity changed by at least 8/255. An observable update requires
both MAD ≥2/255 and changed fraction ≥0.01 by default. Thresholds are configurable.

These commands were executed:

```bash
.venv/bin/python prepare_data.py diagnose --config configs/nyc_traffic.json \
  --start 30 --duration 30 --output output/nyc_traffic/updates_30_60_quality

.venv/bin/python prepare_data.py diagnose --config configs/nyc_traffic.json \
  --camera 5ave_57st --camera 7ave_43st_ptz \
  --start 04:00:00 --duration 30 --output output/nyc_traffic/updates_4h_quality
```

For a sensitivity check (not executed), use a new output directory and vary thresholds:

```bash
.venv/bin/python prepare_data.py diagnose --config configs/nyc_traffic.json \
  --camera 5ave_57st --start 30 --duration 30 \
  --mad-threshold 3 --pixel-delta 12 --min-fraction 0.02 \
  --output output/nyc_traffic/update_sensitivity
```

Each camera gets `diagnostic.json` and a streaming `differences.csv` containing
source timestamps, MAD, changed fraction, update flags, mean luma, dark-pixel fraction
and near-black flags. Reported change Hz is counted updates divided by elapsed time
between the first and last decoded frame. `inter_update_hz`, when defined, uses the
span from first to last detected change and reduces short-window boundary effects.
Exact repeated-pair fraction is also reported. Near-black means at least 99% of ROI
gray pixels are ≤16; this is an image-content signal, not proof of hardware failure.

Executed early-window observations (44 frames; effective stored-frame rate 1.494 FPS):

| Camera | Detected updates | Observable change Hz | Near-black analyzed frames |
| --- | --- | --- | --- |
| 5 Ave @ 57 St | 15 | 0.521135 | 0% |
| Central Park West @ 72 St | 15 | 0.521135 | 0% |
| Broadway @ 43 St | 15 | 0.521135 | 0% |
| Broadway @ 46 St | 15 | 0.521135 | 0% |
| 5 Ave @ 34 St | 4 | 0.138969 | 0% |
| 7 Ave @ 43 St | 0 | 0 | 100% |
| Central Park @ 72nd St Post 37 | 15 | 0.521135 | 0% |

At the four-hour window, both selected problem feeds were near-black in all 48
analyzed frames, with zero detected updates. The retained times were approximately
14,401.356667–14,429.473333 s. The 30 s snapshot already shows 7 Ave black; the 4 h
snapshot also shows 5 Ave black. The exact onset, duration, recurrence and recovery
of either outage **have not been established**. These observations do not prove that
an entire intervening interval is black. Keep black intervals in the source timeline;
use the diagnostic's timestamped flags to build quality annotations after review.

**Observable change rate is not true camera sensor/network refresh frequency.** A
static scene may refresh without visible changes. Compression noise, motion, loading
screens, clocks, cursor movement and overlays may trigger or hide changes. A recording
can miss updates between its stored frames. Rates are therefore a content-based
proxy, which can undercount or overcount, not a recovered network protocol measurement.
Inspect several windows and threshold choices before using a rate in the thesis.
Do not extrapolate the 30 s estimates to the entire recording.

The diagnostic stores two grayscale frames, bounded timestamp queues, counters and
streamed CSV rows. FFmpeg handles decoding; neither this diagnostic nor exporting
loads the five-hour recording into RAM.

## Executed tests and unexecuted work

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/verify_preprocessing_samples.py \
  --config configs/nyc_traffic.json --samples output/nyc_traffic/smoke_30_60
```

Both commands were executed successfully. The sample verifier creates `review/`
and should be run on a new export directory rather than overwriting previous evidence.

- **13 automated tests passed:** the 7 existing baseline tests plus 6 preprocessing
  tests. New tests use a generated four-second lossless two-panel fixture with a
  known 1 Hz-changing view and a static black view. They verify coordinate/input
  validation, fractional start times, crop isolation, exact source mappings, encoded
  timestamp preservation, full-mode behavior on the tiny fixture, dry-run behavior,
  the long-export gate, integer-PTS parsing, known update frequency and black flags.
  Synthetic tests verify mechanics, not traffic retrieval quality.
- **Real exports passed:** seven camera MP4s, 44 frames each; dimensions match each
  crop; encoded timestamp errors are at most 0.333334 microseconds against source
  differences. No frame-rate conversion was applied.
- **Real spatial checks passed:** the first, middle and last output frames from every
  camera were compared with independently decoded source crops (21 comparisons),
  within a mean absolute pixel-error tolerance of 6/255 for CRF-18 re-encoding.
  Every decoded cropped-frame timestamp was checked against its CSV. The contact
  sheet was also visually inspected; samples show only their intended camera views.
- **Original preserved:** file size, modification time and sampled fingerprint match
  initialization. The original was never opened for writing. A full-source hash was
  not computed, and no stronger whole-file checksum claim is made.
- **Full-length real exports, development exports and exhaustive blackout detection
  were not executed.** Crop review remains pending, as requested. No OpenCLIP model
  changes or new retrieval-quality experiments were performed.

## Reusing the existing research baseline

After crops are accepted, index a development export with the existing commands,
using a new output path (example not executed here):

```bash
HF_HUB_OFFLINE=1 .venv/bin/python main.py index \
  --video output/nyc_traffic/dev_5m_10m/5ave_57st.mp4 --interval 2 \
  --index output/indexes/5ave_57st_uniform_2s.npz
```

The existing backend reads actual decoded timestamps and can accept these VFR MP4s.
Keep the preparation configuration, export manifest, source/output hashes and timeline
CSV alongside every future index. Fix crops, source intervals, encoding settings,
video versions and query annotations before comparing selection methods. Burned-in
logos, camera resolution differences, blackouts and camera time offsets remain
potential dataset confounds to annotate and discuss.
