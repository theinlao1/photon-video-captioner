"""
Reads and validates /input/tasks.json
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger("task_loader")

KNOWN_STYLES = {"formal", "sarcastic", "humorous_tech", "humorous_non_tech"}


class TasksFileError(Exception):
    """tasks.json missing / broken JSON / not a list — nothing to recover."""


@dataclass(frozen=True)
class Task:
    task_id: str
    video_url: str
    styles: tuple[str, ...]


def _is_probably_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _validate_task(raw: object, index: int) -> Task | None:
    """Validates a single list element. On a problem, logs the reason and returns None."""
    if not isinstance(raw, dict):
        logger.warning("Task #%d skipped: element is not an object (%s)", index, type(raw).__name__)
        return None

    task_id = raw.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        logger.warning("Task #%d skipped: no valid task_id", index)
        return None

    video_url = raw.get("video_url")
    if not isinstance(video_url, str) or not _is_probably_url(video_url):
        logger.warning("Task %s skipped: video_url missing or does not look like a URL", task_id)
        return None

    styles_raw = raw.get("styles")
    if not isinstance(styles_raw, list) or not styles_raw:
        logger.warning("Task %s skipped: styles is empty or not a list", task_id)
        return None

    styles: list[str] = []
    seen: set[str] = set()
    for s in styles_raw:
        if not isinstance(s, str) or not s.strip():
            logger.warning("Task %s: skipped empty/non-string style %r", task_id, s)
            continue
        if s in seen:
            continue
        seen.add(s)
        if s not in KNOWN_STYLES:
            logger.warning(
                "Task %s: style %r is not one of the standard four, but we'll try to generate it as-is",
                task_id, s,
            )
        styles.append(s)

    if not styles:
        logger.warning("Task %s skipped: no valid styles left after cleaning", task_id)
        return None

    return Task(task_id=task_id, video_url=video_url, styles=tuple(styles))


def load_tasks(path: str | Path = "/input/tasks.json") -> list[Task]:
    """Reads and validates tasks.json, returns the list of valid tasks."""
    path = Path(path)

    if not path.exists():
        raise TasksFileError(f"file not found: {path}")

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise TasksFileError(f"could not read {path}: {e}") from e

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise TasksFileError(f"invalid JSON in {path}: {e}") from e

    if not isinstance(data, list):
        raise TasksFileError(f"top level of {path} must be a list, got {type(data).__name__}")

    if not data:
        raise TasksFileError(f"{path} contains an empty task list")

    tasks: list[Task] = []
    seen_ids: set[str] = set()
    for i, raw in enumerate(data):
        task = _validate_task(raw, i)
        if task is None:
            continue
        if task.task_id in seen_ids:
            logger.warning("Task %s: duplicate task_id, keeping the first occurrence", task.task_id)
            continue
        seen_ids.add(task.task_id)
        tasks.append(task)

    if not tasks:
        raise TasksFileError(f"no valid tasks left in {path} after validation")

    logger.info("Loaded %d valid tasks out of %d entries (%s)", len(tasks), len(data), path)
    return tasks


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    target = sys.argv[1] if len(sys.argv) > 1 else "/input/tasks.json"
    try:
        loaded = load_tasks(target)
    except TasksFileError as e:
        logger.error("could not load tasks: %s", e)
        sys.exit(1)

    for t in loaded:
        print(f"{t.task_id}: {t.video_url} -> {list(t.styles)}")