# Results overview

**Start here.** These tables read saved measurements; generating them runs no model or video processing.

The thesis compares retrieval quality versus actual persistent index bytes, with construction time, search latency and memory as additional tradeoffs.

[Download/open the complete CSV](../experiments/summary.csv) · [Experiment registry](../experiments/registry.json) · [Measurement definitions](BENCHMARKING.md)


## Experiment setup: what to run

[Edit the experiment catalog](../configs/experiments.json). Each entry specifies a method, footage, manifest, selection budget and query file. Planned rows have no measured results.

| Experiment ID | Method | Footage path | Selection settings | Status |
| --- | --- | --- | ---: | --- |
| `nyc_dev_uniform_5s_v3` | uniform + OpenCLIP | [data/clips/dev/nyc_traffic_000500_001500/broadway_46st_quad_south.mp4](../data/clips/dev/nyc_traffic_000500_001500/broadway_46st_quad_south.mp4) | 5.0 s interval | current |
| `uniform_5s_broadway43_dev_r01` | uniform + OpenCLIP | [data/clips/dev/nyc_traffic_000500_001500/broadway_43st.mp4](../data/clips/dev/nyc_traffic_000500_001500/broadway_43st.mp4) | 5.0 s interval | planned |
| `uniform_5s_cpw72_dev_r01` | uniform + OpenCLIP | [data/clips/dev/nyc_traffic_000500_001500/central_park_west_72st.mp4](../data/clips/dev/nyc_traffic_000500_001500/central_park_west_72st.mp4) | 5.0 s interval | planned |
| `diversity_120_broadway46_dev_r01` | diversity + OpenCLIP | [data/clips/dev/nyc_traffic_000500_001500/broadway_46st_quad_south.mp4](../data/clips/dev/nyc_traffic_000500_001500/broadway_46st_quad_south.mp4) | 120 retained frames | completed |

```bash
.venv/bin/python scripts/run_experiment.py list
.venv/bin/python scripts/run_experiment.py show --id uniform_5s_broadway43_dev_r01
.venv/bin/python scripts/run_experiment.py run --id uniform_5s_broadway43_dev_r01 --dry-run
# Remove --dry-run to execute this entry and add its verified measurements.
```

A run uses new folders named after its experiment ID for the index, retrieval results and evidence. Existing runs cannot be overwritten; give repeats new IDs. Uniform and diversity sampling are supported. Comparing methods later requires the same footage and queries.

## Current experiment comparison

One row per completed experiment. Audit records are views of a run, not new experiments. Superseded and failed runs remain below as history.

| Method | Camera | Index bytes | Index build median (s; n) | Fresh query median (s; n) | Warm query median (ms; n) | Query Hit@5 |
| --- | --- | ---: | --- | --- | --- | --- |
| Uniform 5 s + OpenCLIP | broadway_46st_quad_south | 285,146 | 9.306; n=1 | 7.418; n=6 | 36.535; n=9 | Pending annotations |
| Broadway 46 St / diversity 120 frames | broadway_46st_quad_south | 286,178 | 41.741; n=1 | 8.658; n=6 | 34.048; n=9 | Pending annotations |

**Timing boundaries:** fresh queries include model startup, previews and result writes; warm queries use a resident model and exclude previews. They measure different scopes. One index build cannot establish variability. p95 is withheld below the protocol sample threshold. No retrieval accuracy has been measured.

## Prepared development clips

All three use the same requested original-source window, 00:05:00–00:15:00. Sparse VFR timing yields 598.760 s of playable video. Use the saved timeline CSVs for precise source mapping.

| Camera / video | Duration (s) | Resolution | Stored frames | Stored FPS | Visible-change Hz | Current comparison |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| [Broadway @ 46 St - Quad South](../data/clips/dev/nyc_traffic_000500_001500/broadway_46st_quad_south.mp4) | 598.760 | 592×356 | 843 | 1.407910 | 0.497660 | Indexed and verified |
| [Broadway @ 43 St](../data/clips/dev/nyc_traffic_000500_001500/broadway_43st.mp4) | 598.760 | 592×376 | 843 | 1.407910 | 0.484255 | Prepared; no current index benchmark |
| [Central Park West @ 72 St](../data/clips/dev/nyc_traffic_000500_001500/central_park_west_72st.mp4) | 598.760 | 592×372 | 843 | 1.407910 | 0.497660 | Prepared; no current index benchmark |

Visible-change rates come from the saved 80×48 grayscale analysis for this source window. They are content-change proxies, not network/sensor FPS. Video/index/preview binaries remain local and are excluded from Git.

## Detailed experiment scorecards

### nyc_dev_uniform_5s_v3

[Normalized measurements](../experiments/benchmarking_audit_v1/benchmark_record.json) · [Raw run evidence](../experiments/nyc_dev_uniform_5s_v3/experiment.json)

| Category | Metric | Recorded value | Scope / limitation |
| --- | --- | --- | --- |
| Retrieval quality | Query Hit@5 | Pending annotations | No annotated event intervals; qualitative examples do not establish accuracy |
| Representation | Retained items / embedding dimensions | 120 frame / 512 | {"interval_seconds":5.0,"max_frames":null,"name":"uniform"} |
| Construction | Candidate frames encoded | Not recorded | All candidate inference counts toward indexing, even if only a subset is retained |
| Representation | Model / checkpoint | ViT-B-32 / laion2b_s34b_b79k | OpenCLIP image/text embeddings |
| Representation | Caption lengths | Not applicable | No captions stored by the current baseline |
| Storage | Persistent retrieval index | 285,146 bytes | Actual retrieval-required files, including embedded metadata; excludes corpus and shared model files |
| Storage | experiment metadata | 12,319 bytes | Separate from primary index budget |
| Storage | original video | 5,649,293,214 bytes | Separate from primary index budget |
| Storage | preview | Not inventoried | Separate from primary index budget |
| Storage | processed video | 18,497,430 bytes | Separate from primary index budget |
| Storage | shared model | Not inventoried | Separate from primary index budget |
| Storage | temporary | Not inventoried | Separate from primary index budget |
| Construction | End-to-end build | 9.306 s (n=1) | Fresh process; includes imports/model loading and full core build |
| Construction | Model loading / core build | 2.797 s / 3.720 s | Saved coarse timings; excludes imports from these two components |
| Construction | Throughput | 64.340 input-video hours/wall hour | Uses actual cropped-input duration; one observation, not an extrapolation to five hours |
| Construction | Detailed stages | unavailable | Stage timers were not present; cannot reconstruct stages retrospectively |
| Search | Fresh-process queries | 7.418 s median; n=6 | With previews/startup |
| Search | Fresh-process queries variability | 6.664–8.438 s; sample SD 0.660 s | Saved query workload; per-query details remain in the normalized record |
| Search | Fresh-process queries p95 | Not recorded | Fewer than 100 samples; tail estimate withheld by protocol |
| Search | Resident-model queries | 36.535 ms median; n=9 | No previews or model load; NPZ reloaded per query |
| Search | Resident-model queries variability | 28.382–59.656 ms; sample SD 11.780 ms | Saved query workload; per-query details remain in the normalized record |
| Search | Resident-model queries p95 | Not recorded | Fewer than 100 samples; tail estimate withheld by protocol |
| Resources | Peak indexing process RAM | 1,166,409,728 bytes | Process-specific lifetime high-water RSS; excludes child/system memory. Not a warm-query-only allocation delta. |
| Resources | Maximum query process RAM | 1,343,242,240 bytes | Maximum of recorded fresh-query worker lifetime peaks |
| Resources | Accelerator peak memory | Not recorded | CPU run; no accelerator peak recorded |
| Resources | System-wide peak RAM | Not recorded | Not recorded |
| Environment | CPU model | Not recorded | Not recorded at run time; current hardware audit is not historical evidence |
| Environment | Physical RAM capacity | Not recorded | Not recorded at run time; current hardware audit is not historical evidence |
| Environment | Device / threads / seed | cpu / 4 / 0 | Recorded inference configuration |
| Environment | Software versions | {"packages":{"Pillow":"13.0.0","numpy":"2.4.6","open_clip_torch":"3.3.0","opencv-python":"5.0.0.93","timm":"1.0.30","torch":"2.14.1","torchvision":"0.29.1"},"platform":"macOS-26.5.2-arm64-arm-64bit","python":"3.11.7"} | Recorded at original run time; current hardware is not backfilled |
| Provenance | Video / availability | broadway_46st_quad_south; SHA-256 a4bc3de1c8811d562ae052c15e5a4895afa86403459d6e3713d26cfc2602d4e4 | {"path":"/Users/anguscheng/Downloads/video-search-baseline/data/metadata/nyc_traffic/availability_v2/availability.json","sha256":"84dbc6de742abdfa2aacf1a9904a647e5ea3dc993814e3b6e7ec83e35093f91e"} |
### diversity_120_broadway46_dev_r01

[Normalized measurements](../experiments/diversity_120_broadway46_dev_r01/benchmark_record.json) · [Raw run evidence](../experiments/diversity_120_broadway46_dev_r01/experiment.json)

| Category | Metric | Recorded value | Scope / limitation |
| --- | --- | --- | --- |
| Retrieval quality | Query Hit@5 | Pending annotations | No annotated event intervals; qualitative examples do not establish accuracy |
| Representation | Retained items / embedding dimensions | 120 frame / 512 | {"algorithm":"greedy_farthest_first","candidates":"all_eligible_decoded_frames","distance":"cosine","initialization":"earliest_eligible_frame","max_frames":120,"name":"diversity","selection_dtype":"float64","tie_break":"earliest_remaining_candidate"} |
| Construction | Candidate frames encoded | 843 | All candidate inference counts toward indexing, even if only a subset is retained |
| Representation | Model / checkpoint | ViT-B-32 / laion2b_s34b_b79k | OpenCLIP image/text embeddings |
| Representation | Caption lengths | Not applicable | No captions stored by the current baseline |
| Storage | Persistent retrieval index | 286,178 bytes | Actual retrieval-required files, including embedded metadata; excludes corpus and shared model files |
| Storage | experiment metadata | 14,781 bytes | Separate from primary index budget |
| Storage | original video | 5,649,293,214 bytes | Separate from primary index budget |
| Storage | preview | Not inventoried | Separate from primary index budget |
| Storage | processed video | 18,497,430 bytes | Separate from primary index budget |
| Storage | shared model | Not inventoried | Separate from primary index budget |
| Storage | temporary | Not inventoried | Separate from primary index budget |
| Construction | End-to-end build | 41.741 s (n=1) | Fresh process; includes imports/model loading and full core build |
| Construction | Model loading / core build | 5.335 s / 31.885 s | Saved coarse timings; excludes imports from these two components |
| Construction | Throughput | 14.345 input-video hours/wall hour | Uses actual cropped-input duration; one observation, not an extrapolation to five hours |
| Construction | Detailed stages | measured | {"dataset_validation":{"calls":1,"seconds":0.0246269169729203},"diversity_selection":{"calls":1,"seconds":0.012237875023856759},"eligibility_filter":{"calls":1,"seconds":0.0006614590529352427},"image_encoding_including_preprocess":{"calls":53,"seconds":25.840609665610828},"index_arrays_and_validation":{"calls":1,"seconds":0.0009128329111263156},"index_persistence":{"calls":1,"seconds":0.010283834068104625},"input_fingerprint":{"calls":1,"seconds":0.027761833043769002},"model_fingerprint":{"calls":1,"seconds":3.349630457931198},"output_fingerprint":{"calls":1,"seconds":0.0002527909819036722},"rgb_to_pil":{"calls":843,"seconds":0.2841221857815981},"selected_frame_decoding":{"calls":844,"seconds":0.7323993999743834},"selection":{"calls":1,"seconds":4.425004590302706e-05},"source_integrity_recheck":{"calls":1,"seconds":0.019255041959695518},"timeline_decoding":{"calls":1,"seconds":1.2037448330083862},"video_probe":{"calls":1,"seconds":0.10708720807451755}} |
| Search | Fresh-process queries | 8.658 s median; n=6 | With previews/startup |
| Search | Fresh-process queries variability | 8.001–11.325 s; sample SD 1.503 s | Saved query workload; per-query details remain in the normalized record |
| Search | Fresh-process queries p95 | Not recorded | Fewer than 100 samples; tail estimate withheld by protocol |
| Search | Resident-model queries | 34.048 ms median; n=9 | No previews or model load; NPZ reloaded per query |
| Search | Resident-model queries variability | 28.825–54.631 ms; sample SD 7.988 ms | Saved query workload; per-query details remain in the normalized record |
| Search | Resident-model queries p95 | Not recorded | Fewer than 100 samples; tail estimate withheld by protocol |
| Resources | Peak indexing process RAM | 531,464,192 bytes | Process-specific lifetime high-water RSS; excludes child/system memory. Not a warm-query-only allocation delta. |
| Resources | Maximum query process RAM | 1,165,508,608 bytes | Maximum of recorded fresh-query worker lifetime peaks |
| Resources | Accelerator peak memory | Not recorded | CPU run; no accelerator peak recorded |
| Resources | System-wide peak RAM | Not recorded | Not recorded |
| Environment | CPU model | Not recorded | sysctl: sysctl fmt -1 1024 1: Operation not permitted |
| Environment | Physical RAM capacity | Not recorded | sysctl: sysctl fmt -1 1024 1: Operation not permitted |
| Environment | Device / threads / seed | cpu / 4 / 0 | Recorded inference configuration |
| Environment | Software versions | {"packages":{"Pillow":"13.0.0","numpy":"2.4.6","open_clip_torch":"3.3.0","opencv-python":"5.0.0.93","timm":"1.0.30","torch":"2.14.1","torchvision":"0.29.1"},"platform":"macOS-26.5.2-arm64-arm-64bit","python":"3.11.7"} | Recorded at original run time; current hardware is not backfilled |
| Provenance | Video / availability | broadway_46st_quad_south; SHA-256 a4bc3de1c8811d562ae052c15e5a4895afa86403459d6e3713d26cfc2602d4e4 | {"path":"/Users/anguscheng/Downloads/video-search-baseline/data/metadata/nyc_traffic/availability_v2/availability.json","sha256":"84dbc6de742abdfa2aacf1a9904a647e5ea3dc993814e3b6e7ec83e35093f91e"} |

## Experiment history

| Experiment | Status | Summary row? | Notes / evidence |
| --- | --- | --- | --- |
| nyc_dev_uniform_5s_v3 | current | Yes | Current completed baseline; availability_v2. Benchmark record is an audit of this run, not a new run. [Evidence](../experiments/nyc_dev_uniform_5s_v3/experiment.json) |
| nyc_dev_uniform_5s_v2 | superseded | No | Completed under availability_v1. Preserved for provenance; not pooled into current timing statistics. [Evidence](../experiments/nyc_dev_uniform_5s_v2/experiment.json) |
| nyc_dev_uniform_5s_v1 | failed | No | Index built, but an overly broad test guard blocked an OS-information subprocess during search. Logs retained; not a completed retrieval benchmark. [Evidence](../experiments/nyc_dev_uniform_5s_v1/experiment.json) |
| diversity_120_broadway46_dev_r01 | completed | Yes | Run from configs/experiments.json; configuration snapshot in experiments/diversity_120_broadway46_dev_r01/run_config.json [Evidence](../experiments/diversity_120_broadway46_dev_r01/experiment.json) |

## Refresh or extend this table

```bash
.venv/bin/python scripts/summarize_experiments.py
```

This regenerates only `experiments/summary.csv` and this overview from the registry and saved JSON. It does not rerun experiments or alter raw evidence. CSV empty cells mean unavailable/not applicable; status/reason columns preserve the distinction. Seconds and bytes are explicit in column names.

For a new completed experiment, add its unique ID, status, evidence path and normalized `benchmark_record.json` to `experiments/registry.json`, then refresh. Mark superseded/failed attempts explicitly. Register one experiment once; never add its audit or each query repeat as another experiment. Unknown metrics remain empty with reasons.

Next work: annotate fixed query/event intervals, gather repeated build and query measurements, then compare configurations under shared storage definitions. The current table organizes existing evidence; it does not add accuracy results or claim one method is cheaper.
