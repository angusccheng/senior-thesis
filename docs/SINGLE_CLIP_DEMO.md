# One-clip meeting walkthrough

Focus only on **Broadway @ 46 St, Quad South**. Ignore the other camera datasets and historical experiment folders for this demonstration.

1. Open [the video](../data/clips/dev/nyc_traffic_000500_001500/broadway_46st_quad_south.mp4). It is about ten minutes long (actual playback 9:58.760), taken from source minutes 5–15.
2. Explain: “I retained one frame approximately every five seconds: 120 frames, each represented by a 512-dimensional OpenCLIP embedding.”
3. Show the text query below and its returned images. The saved index was loaded in a fresh process; there was no need to rebuild it.
4. Seek to 7:46.558 in the cropped video and compare it with the first result. That frame maps to 12:48.297 in the original recording.

Query: **Pedestrians crossing a wide crosswalk at a busy city intersection.**

| Rank | Time in this clip | Cosine score | Saved frame |
| --- | --- | ---: | --- |
| 1 | 00:07:46.558 | 0.341719 | [Frame 1](../results/retrieval/meeting_single_clip/rank_01_frame_00000658.jpg) |
| 2 | 00:04:30.320 | 0.339664 | [Frame 2](../results/retrieval/meeting_single_clip/rank_02_frame_00000390.jpg) |
| 3 | 00:01:06.067 | 0.338753 | [Frame 3](../results/retrieval/meeting_single_clip/rank_03_frame_00000103.jpg) |
| 4 | 00:07:56.508 | 0.336080 | [Frame 4](../results/retrieval/meeting_single_clip/rank_04_frame_00000674.jpg) |
| 5 | 00:03:20.237 | 0.333254 | [Frame 5](../results/retrieval/meeting_single_clip/rank_05_frame_00000296.jpg) |

[Full results JSON](../results/retrieval/meeting_single_clip/results.json) · [CSV](../results/retrieval/meeting_single_clip/results.csv)

## Run another query live

Use the terminal in the project root. Choose a new results directory each time:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python main.py search \
  --index indexes/nyc_dev_uniform_5s_v3/index.npz \
  --query "Yellow taxis driving through an intersection." \
  --output results/retrieval/meeting_taxis
```

## What to say to the adviser

“I have a working uniform-sampling baseline on one continuous traffic clip. It saves visual embeddings, searches them with natural language, and maps returned frames back to the original recording. My next step is to annotate event intervals on this same clip so I can measure retrieval quality, then compare indexing methods under matched budgets.”

What this establishes: an executed, reproducible search pipeline. What it does not establish: retrieval accuracy or precise event boundaries. Cosine scores are rankings, not probabilities.

For now, work only with this MP4, this saved index, and these query results. The next evaluation task is to watch the clip and manually record a few clearly defined event intervals; labels should come from the video, not be inferred from the model scores.
