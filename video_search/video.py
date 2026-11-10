"""Sequential decoding; frame numbers and decoder timestamps are authoritative."""
from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np


@dataclass(frozen=True)
class FrameInfo:
    number: int
    seconds: float


def video_properties(path) -> dict:
    """Read FPS and duration estimate; last-frame time is not video duration.

    OpenCV exposes average FPS and frame count, not authoritative container
    duration. Their ratio is an estimate for VFR input. Sampling still uses
    decoded timestamps rather than this estimate.
    """
    if not Path(path).is_file():
        raise FileNotFoundError(path)
    cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    try:
        if not cap.isOpened():
            raise ValueError(f"Cannot decode video: {path}")
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        valid_fps = np.isfinite(fps) and fps > 0
        return {
            'fps': fps if valid_fps else None,
            'reported_frame_count': count if count > 0 else None,
            'duration_seconds': count / fps if valid_fps and count > 0 else None,
            'duration_method': 'reported frame count / average FPS; estimate for VFR',
            'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        }
    finally:
        cap.release()


def decode_video(path):
    """Yield RGB frames and presentation times from OpenCV's FFmpeg backend.

    Reject missing/non-increasing timestamps instead of silently assuming a
    variable-frame-rate video has constant frame rate. Times are video-relative.
    """
    if not Path(path).is_file():
        raise FileNotFoundError(path)
    cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    try:
        if not cap.isOpened():
            raise ValueError(f"Cannot decode video: {path}")
        previous, number = -1.0, 0
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            seconds = float(cap.get(cv2.CAP_PROP_POS_MSEC)) / 1000
            if not np.isfinite(seconds) or seconds < 0 or seconds <= previous:
                raise ValueError(f"Missing/non-increasing timestamp at frame {number}")
            yield FrameInfo(number, seconds), cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            previous = seconds
            number += 1
        if number == 0:
            raise ValueError(f"Video contains no decodable frames: {path}")
        expected = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if expected > 0 and number < expected:
            raise ValueError(f"Video ended early: decoded {number} of {expected} advertised frames")
    finally:
        cap.release()


def scan_video(path) -> list[FrameInfo]:
    return [info for info, _ in decode_video(path)]


def selected_frames(path, frames: list[FrameInfo]):
    """Decode by frame number, avoiding approximate keyframe seeks."""
    wanted = {frame.number: frame for frame in frames}
    if len(wanted) != len(frames):
        raise ValueError("Selected frame numbers must be unique")
    if not wanted:
        return
    for info, rgb in decode_video(path):
        if info.number in wanted:
            expected = wanted.pop(info.number)
            if abs(info.seconds - expected.seconds) > 1e-6:
                raise ValueError("Video timestamps changed since indexing")
            yield info, rgb
            if not wanted:
                return
    if wanted:
        raise ValueError("Selected frames could not be decoded")
