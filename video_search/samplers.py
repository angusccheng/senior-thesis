"""Selection policy only; encoding and retrieval do not depend on the policy."""
from dataclasses import asdict, dataclass
from typing import Protocol
import numpy as np
from .video import FrameInfo


class Sampler(Protocol):
    def select(self, frames: list[FrameInfo]) -> list[FrameInfo]: ...
    def metadata(self) -> dict: ...


@dataclass(frozen=True)
class UniformSampler:
    interval_seconds: float = 5.0
    max_frames: int | None = None

    def __post_init__(self):
        if not np.isfinite(self.interval_seconds) or self.interval_seconds <= 0:
            raise ValueError("interval must be finite and positive")
        if self.max_frames is not None and self.max_frames <= 0:
            raise ValueError("max_frames must be positive")

    def select(self, frames: list[FrameInfo]) -> list[FrameInfo]:
        # First frame at/after each grid time; skip repeated targets for the same
        # frame when the interval is shorter than the frame spacing.
        chosen, target = [], 0.0
        for frame in frames:
            if frame.seconds + 1e-9 >= target:
                chosen.append(frame)
                target = (np.floor((frame.seconds + 1e-9) / self.interval_seconds) + 1) * self.interval_seconds
        if self.max_frames is not None and len(chosen) > self.max_frames:
            positions = np.linspace(0, len(chosen) - 1, self.max_frames, dtype=int)
            chosen = [chosen[i] for i in positions]
        return chosen

    def metadata(self) -> dict:
        return {"name": "uniform", **asdict(self)}


@dataclass(frozen=True)
class DiversitySampler:
    """Greedy farthest-first coverage of unit OpenCLIP embeddings.

    All eligible decoded frames are candidates. Start at the earliest frame,
    then maximize distance to the nearest selected frame. Ties choose the
    earliest remaining candidate. Return chronological positions for storage.
    """
    max_frames: int

    def __post_init__(self):
        if type(self.max_frames) is not int or self.max_frames <= 0:
            raise ValueError('Diversity max_frames must be a positive integer')

    def select(self, frames: list[FrameInfo]) -> list[FrameInfo]:
        return list(frames)

    def select_embeddings(self, embeddings):
        vectors = np.asarray(embeddings)
        if (vectors.ndim != 2 or not len(vectors) or not vectors.shape[1]
                or not np.isfinite(vectors).all()
                or not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)):
            raise ValueError('Diversity selection needs finite unit embedding vectors')
        # Float64 arithmetic and chronological argmax make selection reproducible.
        vectors = vectors.astype(np.float64)
        count = min(self.max_frames, len(vectors))
        selected = np.empty(count, dtype=np.int64)
        nearest = np.full(len(vectors), np.inf)
        used = np.zeros(len(vectors), dtype=bool)
        current = 0
        for step in range(count):
            selected[step] = current
            used[current] = True
            distance = np.clip(1 - vectors @ vectors[current], 0, 2)
            nearest = np.minimum(nearest, distance)
            nearest[used] = -np.inf
            if step + 1 < count:
                current = int(np.argmax(nearest))
        return np.sort(selected)

    def metadata(self):
        return {'name': 'diversity', 'max_frames': self.max_frames,
                'algorithm': 'greedy_farthest_first', 'distance': 'cosine',
                'initialization': 'earliest_eligible_frame',
                'tie_break': 'earliest_remaining_candidate',
                'candidates': 'all_eligible_decoded_frames',
                'selection_dtype': 'float64'}
