"""
Pre-validated writing of /output/results.json.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("result_writer")


def build_result(task_id: str, captions: dict[str, str]) -> dict:
    return {"task_id": task_id, "captions": captions}


def validate_results(results: list[dict]) -> None:
    if not isinstance(results, list):
        raise ValueError("results must be a list")

    seen_ids: set[str] = set()
    for r in results:
        if not isinstance(r, dict) or "task_id" not in r or "captions" not in r:
            raise ValueError(f"each element must have task_id and captions, got: {r!r}")

        task_id = r["task_id"]
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError(f"invalid task_id: {task_id!r}")
        if task_id in seen_ids:
            raise ValueError(f"duplicate task_id in results: {task_id}")
        seen_ids.add(task_id)

        captions = r["captions"]
        if not isinstance(captions, dict) or not captions:
            raise ValueError(f"captions must be a non-empty object ({task_id})")
        for style, text in captions.items():
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"empty/invalid caption: {task_id}/{style}")


def write_results(results: list[dict], out_path: str | Path = "/output/results.json") -> None:
    """Validates the shape and atomically writes results.json."""
    validate_results(results)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")

    tmp_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, out_path)  # atomic within a single filesystem

    logger.info("Wrote %d results to %s", len(results), out_path)