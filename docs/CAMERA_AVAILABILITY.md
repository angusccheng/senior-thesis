# Camera availability and visible-update audit

Protocol: **availability_v2**, source-relative half-open intervals in seconds. All 28,835 stored frames were analyzed once using bounded-memory grayscale mosaics; the pass took 297.707 s. No full-length camera videos were exported.

[Machine-readable availability JSON](../data/metadata/nyc_traffic/availability_v2/availability.json) · [Interval CSV](../data/metadata/nyc_traffic/availability_v2/intervals.csv) · [Update-rate JSON](../data/metadata/nyc_traffic/availability_v2/update_rates.json)

## Confirmed interruptions and recoveries

| Camera | First confirmed unavailable image | End/recovery | Evidence |
| --- | --- | --- | --- |
| 5 Ave @ 57 St | 00:46:40.935 | Black to source end 05:40:32.595; no observed recovery | Flat-black ROI and beginning/middle/end source images |
| 7 Ave @ 43 St | 00:00:17.583 | Black to source end; no observed scene recovery | 50 ms cursor overlay at 04:56:57.333 is not a recovered feed |
| Central Park @ 72nd St Post 37 | 02:34:49.025 | Live imagery returns at 02:37:39.245 | Explicit “This camera is being serviced” card for 170.220 s |

The last preceding nonblack observations for the first two cameras were at 2800.918333333 and 17.533333333 s respectively. Onset is therefore a first-observed presentation timestamp, not an independently measured network failure instant. Both interrupted feeds contain valid initial footage and remain preserved in their entirety in the original recording. No camera was deleted.

[Black-interval review sheet](../data/metadata/nyc_traffic/availability_scan_v1/review/black_candidates.jpg) · [Cursor false-recovery image](../data/metadata/nyc_traffic/availability_scan_v1/review/7ave_transient_nonblack.png) · [Service-card onset/recovery evidence](../data/metadata/nyc_traffic/availability_scan_v1/service_review/service_transition.jpg)

Source-derived 80×48 diagnostic ROI statistics distinguish flat black from naturally dark imagery. The nighttime park scene preceding the service card has mean luma about 25 and standard deviation about 30, so it is retained rather than classed as flat-black failure. Every frame in the service-card run matches the reviewed reference mean/std within 2 gray levels and dark fraction <0.001; source snapshots show the card at the beginning, middle and end, and a real scene after it. This is a reviewed dataset-specific refinement, not a general-purpose service-card detector.

## Valid, invalid and uncertain intervals

“Eligible” excludes confirmed outages only; uncertain frames are preserved and flagged. “Unflagged usable” conservatively excludes both confirmed and uncertain intervals. Neither is human-annotated availability ground truth for every frame. Intervals are source-relative and hold until the next stored presentation timestamp.

| Camera | Eligible source intervals [s] | Confirmed unavailable [s] | Uncertain [s] | Unflagged usable [s] |
| --- | --- | ---: | ---: | ---: |
| 5 Ave @ 57 St | [0.000000, 2800.935000) | 17631.660000 | 0.000000 | 2800.935000 |
| Central Park West @ 72 St | [0.000000, 20432.595000) | 0.000000 | 0.000000 | 20432.595000 |
| Broadway @ 43 St | [0.000000, 20432.595000) | 0.000000 | 0.000000 | 20432.595000 |
| Broadway @ 46 St - Quad South | [0.000000, 20432.595000) | 0.000000 | 0.000000 | 20432.595000 |
| 5 Ave @ 34 St | [0.000000, 20432.595000) | 0.000000 | 106.135000 | 20326.460000 |
| 7 Ave @ 43 St - 64.186 - PTZ | [0.000000, 17.583333) | 20415.011667 | 0.000000 | 17.583333 |
| Central Park @ 72nd St Post 37 | [0.000000, 9289.025000); [9459.245000, 20432.595000) | 170.220000 | 116.153333 | 20146.221667 |

Uncertain intervals requiring manual review:

- 5 Ave @ 34 St: **01:22:03.580–01:23:49.715**, 106.135 s, freeze-like image stability.
- Central Park @ 72nd St Post 37: **02:32:52.872–02:34:49.025**, 116.153333 s, static nighttime imagery preceding the confirmed maintenance card.

The five initially prioritized feeds remain available for development, but the park camera has the additional maintenance outage above. No unresolved interval intersects the chosen 300–900 s window for the three exported cameras.

[Original uncertain-candidate images](../data/metadata/nyc_traffic/availability_v1/manual_review/uncertain_candidates.jpg) (the service-card portion was promoted to confirmed unavailable in v2).

## Stored frame rate versus visible changes

Metadata average rate: 1.411225544 FPS. First-to-last observed pair rate: 1.411178905 FPS. Nominal r_frame_rate is 60/1, but long, irregular presentation gaps exist. The counts differ by the single-frame/end-duration convention; neither is camera sensor FPS.

| Camera | Whole-recording change Hz | Eligible/nonoutage change Hz | Dev-window change Hz | Whole exact-repeat pairs | Whole near-unchanged pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 5 Ave @ 57 St | 0.067833 | 0.494481 | 0.487606 | 86.114% | 95.155% |
| Central Park West @ 72 St | 0.335934 | 0.335934 | 0.497660 | 0.416% | 64.840% |
| Broadway @ 43 St | 0.489268 | 0.489268 | 0.484255 | 0.163% | 65.072% |
| Broadway @ 46 St - Quad South | 0.493281 | 0.493281 | 0.497660 | 0.274% | 64.559% |
| 5 Ave @ 34 St | 0.276911 | 0.276911 | 0.214480 | 0.194% | 80.141% |
| 7 Ave @ 43 St - 64.186 - PTZ | 0.000343 | 0.342205 | 0.000000 | 99.771% | 99.934% |
| Central Park @ 72nd St Post 37 | 0.298837 | 0.301249 | 0.423932 | 0.929% | 65.881% |

All rates use the same 80×48 grayscale diagnostic ROIs and thresholds. Observable updates require mean absolute difference (MAD) ≥2 and at least 1% of pixels changing by ≥8. Near-unchanged pairs have MAD ≤0.15 and ≤0.1% pixels changing by ≥8; exact repeats require identical analysis pixels. Percentages count frame pairs, not elapsed-time fractions. The eligibility-corrected rates remove reviewed black/card intervals and their boundary pairs. The short valid prefix of 7 Ave gives an especially weak refresh estimate.

Compression noise makes many held images numerically nonidentical. Frame bursts, screen capture behavior, slow motion, dark scenes, clocks and cursor overlays affect these measures. A content-change event is **not a measured camera/network refresh**: static scenes can refresh invisibly, changes can happen between recorded frames, and an overlay can mimic an update. The lower nighttime-sensitive rates for park/street feeds do not establish a slower network refresh. Compare multiple windows and threshold/ROI choices before drawing that conclusion.

## Reproduction and protocol policy

See [DATA_PREPARATION.md](DATA_PREPARATION.md) for the exact streaming scan, evidence extraction, review-decision and report-finalization commands. The original scan, v1 labels, all review images and v2 decisions remain versioned. No invalid interval was physically cut from the recording. Future methods can reuse `DatasetContext` and the same manifest; the explicit default policy is `exclude_confirmed_unavailable_only`. A stricter uncertainty exclusion requires a separately versioned shared protocol, not method-specific filtering.

The detector checks all frames for its defined conditions, not every possible outage type. Short freezes (<90 s), unfamiliar error cards and subtle staleness can remain unflagged. There were no uniform blank runs ≥10 s under std≤2 beyond strict-black regions. Human review of additional windows and feed clocks is recommended before treating this metadata as final ground truth.
