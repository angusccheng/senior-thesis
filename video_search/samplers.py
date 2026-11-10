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
