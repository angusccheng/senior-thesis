# A distinctive occurrence in one clip

Clip: [Broadway @ 46 St](../data/clips/dev/nyc_traffic_000500_001500/broadway_46st_quad_south.mp4).

The earlier pedestrian/crosswalk query describes the setting throughout the clip. A more useful example is the large white box truck appearing around the five-minute mark. The truck occupies the crosswalk for part of one sequence, then leaves.

The source clip was inspected with a 20-second storyboard, then a five-second storyboard over 4:40–6:00. Truck imagery is visible in the reviewed frames around 4:56–5:56. This is an approximate visual observation, not an exact event-boundary annotation.

[Review the surrounding sequence](../experiments/single_clip_event_review/truck_window.jpg).

Executed query: **A large white box truck in the crosswalk.**

| Rank | Time in cropped clip | Cosine similarity | Actual returned frame |
| --- | --- | ---: | --- |
| 1 | 00:04:56.355 | 0.269711 | [Frame 1](../results/retrieval/meeting_white_box_truck/rank_01_frame_00000429.jpg) |
| 2 | 00:05:26.372 | 0.265903 | [Frame 2](../results/retrieval/meeting_white_box_truck/rank_02_frame_00000467.jpg) |
| 3 | 00:05:50.405 | 0.262470 | [Frame 3](../results/retrieval/meeting_white_box_truck/rank_03_frame_00000505.jpg) |
| 4 | 00:05:30.388 | 0.258195 | [Frame 4](../results/retrieval/meeting_white_box_truck/rank_04_frame_00000474.jpg) |
| 5 | 00:05:20.372 | 0.253842 | [Frame 5](../results/retrieval/meeting_white_box_truck/rank_05_frame_00000459.jpg) |

All five returned timestamps fall in the visually identified truck sequence. The same 120-frame index was used; no re-indexing or new sampling method was needed.

For the meeting: “A generic crosswalk query mainly retrieves scene context. A truck-specific query concentrates results around one distinctive occurrence. This is a useful qualitative sanity check, but event annotations and more queries are still needed to measure accuracy.”

The current model matches individual frames. It does not establish that a truck turned, stopped, or entered before/after another event from temporal reasoning. Avoid presenting those motion/sequence claims as verified model capabilities. This example was chosen from the inspected clip and is not a held-out evaluation.

Executed command (use a different output directory if repeating):

```bash
HF_HUB_OFFLINE=1 .venv/bin/python main.py search \
  --index indexes/nyc_dev_uniform_5s_v3/index.npz \
  --query "A large white box truck in the crosswalk." \
  --output results/retrieval/meeting_white_box_truck
```
