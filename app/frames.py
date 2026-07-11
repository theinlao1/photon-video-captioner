"""
Extracts frames from a video URL via ffmpeg/ffprobe.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("frames")

MIN_FRAMES = 8
MAX_FRAMES = 20
SECONDS_PER_FRAME = 5
FRAME_MAX_WIDTH = 768 
FFMPEG_TIMEOUT_S = 60  
DOWNLOAD_TIMEOUT_S = 120 


class FrameExtractionError(Exception):
    """Could not get a single frame from the video — neither seek nor download worked."""


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def probe_duration(video_path_or_url: str) -> float:
    """Returns the video duration in seconds via ffprobe. 0.0 if it could not be determined."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path_or_url,
    ]
    try:
        result = _run(cmd, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError) as e:
        logger.warning("ffprobe could not determine duration of %s: %s", video_path_or_url, e)
    return 0.0


def _target_count(duration_s: float) -> int:
    if duration_s <= 0:
        return MIN_FRAMES
    n = round(duration_s / SECONDS_PER_FRAME)
    return max(MIN_FRAMES, min(MAX_FRAMES, n))


def _timestamps(duration_s: float, count: int) -> list[float]:
    """Evenly distributes `count` timestamps, staying away from the very start/end
    (the first/last frame is sometimes black or a transition)."""
    if duration_s <= 0 or count <= 0:
        return []
    margin = min(duration_s * 0.03, 1.0)
    start, end = margin, max(margin, duration_s - margin)
    if count == 1 or end <= start:
        return [duration_s / 2]
    step = (end - start) / (count - 1)
    return [start + i * step for i in range(count)]


def _extract_one_frame(source: str, timestamp_s: float, out_path: Path, timeout: int) -> bool:
    """Grabs a single frame via input-seeking. `source` may be a URL or a local path —
    for ffmpeg it's the same mechanism."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{timestamp_s:.2f}",
        "-i", source,
        "-frames:v", "1",
        "-vf", f"scale={FRAME_MAX_WIDTH}:-2",
        "-q:v", "4",
        str(out_path),
    ]
    try:
        result = _run(cmd, timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg timeout at t=%.1fs (%s)", timestamp_s, source)
        return False
    return result.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0


def _extract_many(source: str, timestamps: list[float], out_dir: Path, timeout: int) -> list[Path]:
    frames: list[Path] = []
    for i, ts in enumerate(timestamps):
        out_path = out_dir / f"frame_{i:03d}.jpg"
        if _extract_one_frame(source, ts, out_path, timeout):
            frames.append(out_path)
    return frames


def _download_video(video_url: str, dest_dir: Path) -> Path | None:
    """Fallback: downloads the video once in full (stream copy, no re-encoding)."""
    dest = dest_dir / "source.mp4"
    cmd = ["ffmpeg", "-y", "-i", video_url, "-c", "copy", str(dest)]
    try:
        result = _run(cmd, timeout=DOWNLOAD_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        logger.error("Video download exceeded the timeout: %s", video_url)
        return None
    if result.returncode != 0 or not dest.exists() or dest.stat().st_size == 0:
        err_tail = (result.stderr or "")[-500:]
        logger.error("Could not download video %s: %s", video_url, err_tail)
        return None
    return dest


@dataclass
class ExtractedFrames:
    paths: list[Path]
    tmp_dir: Path

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)


def extract_frames(video_url: str, tmp_root: str | Path = "/tmp/frames") -> ExtractedFrames:
    """
    Extracts 8-20 frames from a video URL (or a local path — used in tests and
    as the internal fallback stage of this function).
    """
    tmp_root = Path(tmp_root)
    tmp_root.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(dir=tmp_root))

    frames: list[Path] = []
    duration = probe_duration(video_url)

    if duration > 0:
        count = _target_count(duration)
        timestamps = _timestamps(duration, count)
        frames = _extract_many(video_url, timestamps, work_dir, FFMPEG_TIMEOUT_S)
        if len(frames) < len(timestamps) / 2:
            logger.info(
                "URL seek produced only %d/%d frames — downloading the full video and cutting locally",
                len(frames), len(timestamps),
            )
            for f in frames:
                f.unlink(missing_ok=True)
            frames = []

    if not frames:
        local_video = _download_video(video_url, work_dir)
        if local_video is None:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise FrameExtractionError(f"Could neither read via URL nor download the video: {video_url}")

        local_duration = probe_duration(str(local_video)) or duration or 60.0
        count = _target_count(local_duration)
        timestamps = _timestamps(local_duration, count)
        frames = _extract_many(str(local_video), timestamps, work_dir, FFMPEG_TIMEOUT_S)
        local_video.unlink(missing_ok=True)

    if not frames:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise FrameExtractionError(f"Could not extract a single frame from {video_url}")

    logger.info("Extracted %d frames from %s", len(frames), video_url)
    return ExtractedFrames(paths=frames, tmp_dir=work_dir)
