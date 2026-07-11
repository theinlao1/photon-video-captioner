"""
Container entrypoint.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, wait

from dotenv import load_dotenv

load_dotenv()

from captioner import caption_video
from frames import extract_frames
from result_writer import build_result, write_results
from task_loader import Task, TasksFileError, load_tasks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stderr, 
)
logger = logging.getLogger("main")

MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "5"))
SOFT_DEADLINE_S = float(os.environ.get("MAX_RUNTIME_S", "510"))
TASKS_PATH = os.environ.get("TASKS_PATH", "/input/tasks.json")
RESULTS_PATH = os.environ.get("RESULTS_PATH", "/output/results.json")


GENERIC_FALLBACKS = {
    "formal": "The video shows a scene with movement and visual detail.",
    "sarcastic": "Something clearly happened in this video — shame we're a bit short on specifics.",
    "humorous_tech": "Looks like our VLM threw an exception right in the middle of analyzing the scene.",
    "humorous_non_tech": "There was definitely something worth watching here — too bad we blinked and missed it.",
}


def _fallback_for(style: str) -> str:
    return GENERIC_FALLBACKS.get(style, f"Could not generate a caption in the {style} style.")


def _fallback_captions(styles: tuple[str, ...]) -> dict[str, str]:
    return {s: _fallback_for(s) for s in styles}


def process_task(task: Task) -> dict:
    """Frames -> caption_video for one task. Any error is not propagated outward —
    the task simply gets fallback captions, but there is always a result."""
    logger.info("Processing %s: %s", task.task_id, task.video_url)
    t0 = time.monotonic()
    frames = None
    try:
        frames = extract_frames(task.video_url)
        captions = caption_video(frames.paths, list(task.styles))
    except Exception as e:
        logger.error("Task %s: pipeline failure (%s), using fallbacks", task.task_id, e)
        captions = _fallback_captions(task.styles)
    finally:
        if frames is not None:
            frames.cleanup()
    logger.info("Task %s done in %.1fs", task.task_id, time.monotonic() - t0)
    return build_result(task.task_id, captions)


def main() -> int:
    start = time.monotonic()

    try:
        tasks = load_tasks(TASKS_PATH)
    except TasksFileError as e:
        logger.error("Could not load %s: %s", TASKS_PATH, e)
        write_results([], RESULTS_PATH)
        return 1

    results: list[dict] = []
    pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    future_to_task = {pool.submit(process_task, t): t for t in tasks}

    remaining = max(1.0, SOFT_DEADLINE_S - (time.monotonic() - start))
    done, not_done = wait(list(future_to_task), timeout=remaining)

    for f in done:
        t = future_to_task[f]
        try:
            results.append(f.result())
        except Exception as e:  # process_task already catches its own errors, but just in case
            logger.error("Task %s failed unexpectedly (%s), using fallbacks", t.task_id, e)
            results.append(build_result(t.task_id, _fallback_captions(t.styles)))

    for f in not_done:
        t = future_to_task[f]
        logger.error("Task %s did not finish in the allotted time, using fallbacks", t.task_id)
        results.append(build_result(t.task_id, _fallback_captions(t.styles)))

    pool.shutdown(wait=False, cancel_futures=True)

    write_results(results, RESULTS_PATH)
    logger.info("Done: %d tasks in %.1fs", len(results), time.monotonic() - start)
    return 0


if __name__ == "__main__":
    exit_code = 1
    try:
        exit_code = main()
    except Exception:
        logger.exception("Unexpected top-level failure")
        exit_code = 1
        try:
            write_results([], RESULTS_PATH)
        except Exception:
            logger.exception("Could not write even an empty results.json")
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(exit_code) 
        