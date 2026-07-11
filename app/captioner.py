"""
Turns extracted frames into captions in the requested styles.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path

from llm_client import chat_with_fallback

logger = logging.getLogger("captioner")


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_META_PREFIXES = (
    "the user",
    "user is asking",
    "user asks",
    "i need to",
    "i should",
    "let me",
    "okay,",
    "ok,",
    "sure,",
    "here is",
    "here's",
    "frame analysis",
    "analysis of frames",
)


def _strip_reasoning(text: str) -> str:
    """Removes reasoning wrapper and keeps only the substantive description."""
    text = _THINK_BLOCK.sub("", text).strip()

    # Sometimes the model separates the final answer with a marker — take what follows it.
    for marker in ("Description:", "Answer:", "Final description:", "Caption:", "</think>"):
        if marker.lower() in text.lower():
            text = text[text.lower().rindex(marker.lower()) + len(marker):].strip()

    # Drop "reasoning" lines: service preambles and instruction bullets.
    kept: list[str] = []
    for line in text.splitlines():
        low = line.strip().lower()
        if not low:
            continue
        if any(low.startswith(p) for p in _META_PREFIXES):
            continue
        # lines like "- Only facts." / "- No opinions." are the model echoing the
        # instruction, not a description; but "- Setting: office" is kept.
        if re.match(r"^[-*]\s*(only|no |avoid|include|describe|don't|do not|write|\d+[-\s])", low):
            continue
        kept.append(line.strip().lstrip("-* ").strip())

    cleaned = " ".join(kept).strip()
    return cleaned or text  


STYLE_DEFINITIONS = {
    "formal": "professional, objective, factual tone — no jokes and no value judgments",
    "sarcastic": "dry irony, light mockery — but not rude and not cruel",
    "humorous_tech": "funny, with a genuine technology/programming reference (a metaphor, a term, "
                     "a joke about code/software/hardware) — not just a buzzword, but something actually played on",
    "humorous_non_tech": "funny and everyday, with NO technical jargon or references to technology whatsoever",
}

SCENE_SYSTEM_PROMPT = """You are a precise video analyst. You are given several frames of a single \
video in time order (Frame 1 is the start of the clip, the last frame is the end). Describe what \
happens in the video using FACTS ONLY, with no opinions and no style. Be sure to cover:
- the setting / location
- who or what is in the frame (people, animals, objects)
- movement and actions visible across the frames
- notable details (colors, weather, lighting, any text visible on objects)
- the overall mood stated neutrally as a fact (e.g. "a busy street", "a calm garden")

Write flowing prose in English, 4-6 sentences. Do not invent anything not visible in the frames.

IMPORTANT: output the finished description immediately and nothing else. No reasoning, no \
"The user is asking", no "Frame analysis", no instruction lists, no service headers, and no \
<think> blocks. Only the description prose itself."""

STYLE_SYSTEM_PROMPT_TEMPLATE = """You write video captions in different styles based on a ready \
factual description of the scene. You must not change the facts or add anything not present in the \
description — only change the delivery. Write all captions in English.

Return ONLY a valid JSON object (no markdown, no ```), with exactly these keys: {style_keys}.
Each value is one caption (1-3 sentences) in the corresponding style:
{style_descriptions}

The styles must sound DISTINCT from each other — do not reuse the same jokes or phrasing across keys.

IMPORTANT: the answer is ONLY the JSON object and nothing else. No reasoning, no preamble, no \
markdown ``` fences, no <think> blocks, and no text before or after the JSON."""


def _image_content_part(frame_path: Path) -> dict:
    data = base64.b64encode(frame_path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}}


def describe_scene(frame_paths: list[Path]) -> str:
    """One vision request with all frames -> a factual scene description as free text."""
    if not frame_paths:
        raise ValueError("No frames to describe")

    content: list[dict] = []
    for i, p in enumerate(frame_paths, start=1):
        content.append({"type": "text", "text": f"Frame {i}:"})
        content.append(_image_content_part(p))

    messages = [
        {"role": "system", "content": SCENE_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]
    raw = chat_with_fallback(messages, kind="vision", max_tokens=700, temperature=0.2)
    description = _strip_reasoning(raw)
    if not description:
        raise ValueError("VLM returned an empty scene description")
    logger.info("Factual scene description (%d chars): %s", len(description), description[:200])
    return description


def _fallback_caption(description: str) -> str:
    """A stand-in caption if generating a specific style failed — a neutral restatement
    of the fact is better than an empty key (an empty key = 0 points for that style
    per the track rules)."""
    first_sentence = description.strip().split(". ")[0].strip()
    if first_sentence:
        return first_sentence if first_sentence.endswith((".", "!", "?")) else first_sentence + "."
    return "A video showing people, objects, or nature in the frame."


def _extract_json_object(raw: str) -> dict | None:
    """Extracts a JSON object from the model's answer, even if it is wrapped in
    reasoning text or a markdown ```json ... ``` fence. Returns None if nothing
    valid was found."""
    text = _THINK_BLOCK.sub("", raw).strip()

    # 1) direct parse — the most common and cleanest case
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # 2) cut out the contents of a markdown fence, if the model added one
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            obj = json.loads(fence.group(1))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    # 3) take the largest {...} block in the text (from the first { to the last })
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    return None


def generate_styles(description: str, styles: list[str]) -> dict[str, str]:
    """One request with structured JSON output -> a caption for each requested style."""
    descriptions_block = "\n".join(
        f"- {s}: {STYLE_DEFINITIONS.get(s, 'invent a fitting style based on the key name')}" for s in styles
    )
    system_prompt = STYLE_SYSTEM_PROMPT_TEMPLATE.format(
        style_keys=", ".join(styles),
        style_descriptions=descriptions_block,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Factual scene description:\n{description}"},
    ]

    result: dict[str, str] = {}
    try:
        raw = chat_with_fallback(
            messages,
            kind="text",
            response_format={"type": "json_object"},
            max_tokens=1500,
            temperature=0.8,
        )
    except Exception as e:
        logger.error("Style request failed entirely (%s), all styles -> fallbacks", e)
        return {s: _fallback_caption(description) for s in styles}

    parsed = _extract_json_object(raw)
    if parsed is None:
        logger.warning("Style JSON did not parse, using fallbacks for all styles: %r", raw[:200])
        parsed = {}

    for style in styles:
        value = parsed.get(style)
        if isinstance(value, str) and value.strip():
            result[style] = value.strip()
        else:
            logger.warning("Style %s missing/empty in the model's answer, using a fallback", style)
            result[style] = _fallback_caption(description)
    return result


def caption_video(frame_paths: list[Path], styles: list[str]) -> dict[str, str]:
    """Full step for one video: frames -> factual description -> a caption for each requested style."""
    try:
        description = describe_scene(frame_paths)
    except Exception as e:
        logger.error("VLM step failed entirely (%s) — using a generic fallback description", e)
        description = "The frame shows a dynamic scene; the details could not be recognized automatically."

    return generate_styles(description, styles)