<p align="center">
  <img src="assets/photon_logo.png" alt="Photon Video Captioner" width="480">
</p>

<p align="center">
  A multimodal agent that watches a short video clip and generates captions in four distinct styles.
</p>

<p align="center">
  AMD Developer Hackathon (ACT II) — Track 2: Video Captioning Agent
</p>

---

## Overview

Photon is a Dockerized agent that reads captioning tasks from `/input/tasks.json`,
processes each video, and writes captions for every requested style to
`/output/results.json`. It runs headless, requires no interaction, and exits with
status code `0` on success.

For each clip the agent produces captions in four styles:

| Style | Description |
| --- | --- |
| `formal` | Professional, objective, factual tone |
| `sarcastic` | Dry, ironic, lightly mocking |
| `humorous_tech` | Humorous, with a technology or programming reference |
| `humorous_non_tech` | Humorous, everyday tone with no technical jargon |

## How it works

The pipeline separates *understanding* the video from *styling* the caption, which
keeps the humorous variants grounded in what is actually on screen.

1. **Frame sampling** — `ffmpeg` extracts 8–20 evenly spaced frames (adapted to clip
   length) and resizes them to 768&nbsp;px. If frame seeking over the URL fails, the
   clip is downloaded and sampled locally.
2. **Factual description** — a vision-language model produces a single, strictly
   factual description of the scene (no opinions, no style).
3. **Style generation** — a second request converts that factual description into all
   four styled captions, returned as a single JSON object.
4. **Validation and fallbacks** — every requested style is guaranteed to be present.
   If any stage fails, a safe fallback caption is used so the output is always valid.

Tasks are processed in parallel with a soft time budget, and the agent always writes a
well-formed `results.json`.

## Project structure

```
.
├── app/
│   ├── main.py            # Entry point: read tasks, orchestrate, write results
│   ├── task_loader.py     # Parse and validate /input/tasks.json
│   ├── frames.py          # ffmpeg frame extraction and resizing
│   ├── captioner.py       # Two-stage prompting: description -> styled captions
│   ├── llm_client.py      # OpenAI-compatible client with provider fallback
│   └── result_writer.py   # Build and write /output/results.json
├── streamlit_app.py       # Interactive web demo
├── examples_results.json  # Precomputed captions used by the demo
├── Dockerfile
├── requirements.txt
├── scripts/run_local.sh   # Build the image and run against test_input/
├── test_input/tasks.json  # Sample input
└── assets/                # Logo
```

## Input and output format

Input — `/input/tasks.json`:

```json
[
  {
    "task_id": "v1",
    "video_url": "https://storage.example.com/clips/clip1.mp4",
    "styles": ["formal", "sarcastic", "humorous_tech", "humorous_non_tech"]
  }
]
```

Output — `/output/results.json`:

```json
[
  {
    "task_id": "v1",
    "captions": {
      "formal": "...",
      "sarcastic": "...",
      "humorous_tech": "...",
      "humorous_non_tech": "..."
    }
  }
]
```

## Configuration

Credentials and models are read from the environment. Copy `.env.example` to `.env`
and fill in your values before building the image.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `PRIMARY_BASE_URL` | Yes | — | Base URL of the primary OpenAI-compatible API |
| `PRIMARY_API_KEY` | Yes | — | API key for the primary provider |
| `PRIMARY_VISION_MODEL` | Yes | — | Vision model used to describe frames |
| `PRIMARY_TEXT_MODEL` | No | `PRIMARY_VISION_MODEL` | Text model used to generate styles |
| `FALLBACK_BASE_URL` | No | — | Base URL of a fallback provider |
| `FALLBACK_API_KEY` | No | — | API key for the fallback provider |
| `FALLBACK_VISION_MODEL` | No | — | Fallback vision model |
| `FALLBACK_TEXT_MODEL` | No | — | Fallback text model |
| `MAX_WORKERS` | No | `5` | Number of clips processed in parallel |
| `MAX_RUNTIME_S` | No | `510` | Soft time budget for the whole run, in seconds |
| `DISABLE_REASONING` | No | `1` | Suppress reasoning output on models that support it |
| `TASKS_PATH` | No | `/input/tasks.json` | Input file path |
| `RESULTS_PATH` | No | `/output/results.json` | Output file path |

## Running with Docker

The evaluation environment runs `linux/amd64`. Build for that platform explicitly:

```bash
docker build --platform linux/amd64 -t photon-video-captioner .
```

Run the agent, mounting an input directory and an output directory:

```bash
docker run --rm \
  -v "$(pwd)/test_input:/input:ro" \
  -v "$(pwd)/local_output:/output" \
  photon-video-captioner
```

The script `scripts/run_local.sh` performs both steps and prints the resulting
`results.json`.

## Running locally without Docker

Requires Python 3.12 and `ffmpeg` on the system path.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your keys

TASKS_PATH=./test_input/tasks.json \
RESULTS_PATH=./local_output/results.json \
python app/main.py
```

## Web demo

An interactive demo is available as a Streamlit application (`streamlit_app.py`). It
shows precomputed captions for example clips and can generate captions live for any
direct video URL.

Run it locally:

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Provide the same credentials through Streamlit secrets to enable live generation.

## Constraints

- Video inputs must be direct video files (for example `.mp4` URLs); web pages such as
  YouTube links are not supported.
- All captions are produced in English.
- The container is designed to start within 60 seconds and complete a run within the
  evaluation time limit.

## Team

Zhangirkhan and Nurzhanat.
