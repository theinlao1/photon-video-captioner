# Video Captioning Agent — Track 2 (AMD Developer Hackathon: ACT II)

The container reads `/input/tasks.json`, for each clip it pulls frames, gets a
factual scene description from a VLM and captions in all 4 styles from an LLM
(`formal`, `sarcastic`, `humorous_tech`, `humorous_non_tech`), and writes
`/output/results.json`.

```
video → ffmpeg (8–20 frames) → VLM (factual description, 1 request)
                                       → LLM (4 styles, 1 JSON request)
```

## Project structure

```
video-captioning-agent/
├── Dockerfile
├── requirements.txt
├── .env.example          # env var template — copy to .env
├── .env                   # NOT in git; created locally, copied INTO the image
├── .dockerignore
├── .gitignore
├── README.md
├── app/                    # all code that goes into the image as /app
│   ├── main.py             # entrypoint: orchestration, deadline, writing results.json
│   ├── task_loader.py       # reading and validating /input/tasks.json
│   ├── frames.py             # ffmpeg: frame extraction (URL seek + fallback)
│   ├── llm_client.py          # HTTP client for the VLM/LLM with retries and a fallback provider
│   ├── captioner.py            # factual description -> 4 styles
│   └── result_writer.py         # atomic write + validation of results.json
├── test_input/
│   └── tasks.json           # test tasks using the 3 example clips from the track spec
└── scripts/
    └── run_local.sh          # build + local run in one command
```

## Quick start

```bash
cp .env.example .env
# fill in PRIMARY_API_KEY and the other variables in .env

./scripts/run_local.sh
```

This builds the image for `linux/amd64` (that's the architecture the judge
harness pulls images on — one of the typical reasons other people's submissions
failed with "container crashed during evaluation"), mounts `test_input/` as
`/input` and a local `local_output/` folder as `/output`, and prints the result.

## Deploy

```bash
docker buildx build --platform linux/amd64 \
  -t <registry>/video-captioning-agent:latest . --push
```

## How it works

- **Frames** (`frames.py`): roughly 1 frame per 5 seconds of video, but no fewer
  than 8 and no more than 20. It first tries `ffmpeg -ss` directly against the
  URL (fast for 4K without a full download, if the source supports range
  requests — GCS does). If that produced fewer than half the frames, it
  downloads the file once in full and cuts locally.
- **VLM step** (`captioner.describe_scene`): one request with all frames at once
  (labeled `Frame 1`, `Frame 2`…), asking for facts only, no style.
- **LLM step** (`captioner.generate_styles`): one request with
  `response_format={"type": "json_object"}`, rewriting the factual description
  into all requested styles as a single JSON object.
- **Resilience**: at every level (a single style, the whole video, the whole
  provider) there is a fallback instead of an empty/missing value — an empty key
  is scored by the track as a missing style (0 points), while any relevant text
  has a chance at partial points. `main.py` keeps a soft internal deadline
  (`MAX_RUNTIME_S`, default 8.5 minutes) with a margin before the track's
  10-minute limit — tasks that don't finish get fallbacks instead of bringing
  down the whole run.
- **Providers**: `llm_client.py` knows nothing about specific Fireworks/Groq —
  it just hits an OpenAI-compatible `/chat/completions` with `base_url`/`api_key`/
  `model` from environment variables. `PRIMARY_*` is required, `FALLBACK_*` is
  optional and kicks in if the main provider is unavailable/rate-limited right
  during judging.

## Choosing a model on Fireworks

The vision model **must be Serverless-supported** on Fireworks (check the model
page — it should say "Serverless: Supported" and "Image Input: Supported").
Non-serverless models require an On-Demand GPU deploy and will return `404` on
the serverless endpoint. A `404` here means "no such model", not "you need to
deploy" — don't create a deploy, just pick a serverless model and put its exact
Model ID (format `accounts/fireworks/models/...`) into `.env`.

## About keys in a public image

The track spec explicitly says: the harness does not inject environment
variables, you have to bake the keys into the container yourself. Since the
image is public, the key is theoretically extractable from it (`docker history`,
`docker save` + unpack). So:

- use a **separate** key for the hackathon (e.g. the free Fireworks credit
  granted separately from your personal account), not your regular "production"
  key;
- if the provider supports a spend limit/quota, set it on this key;
- `.env` is in `.gitignore`, so it won't end up in git history even if the repo
  is public — but it is still deliberately copied into the Docker image, which
  is required for the container to work.

## Tuning for your own clips

- Prompts — the `SCENE_SYSTEM_PROMPT` / `STYLE_SYSTEM_PROMPT_TEMPLATE` /
  `STYLE_DEFINITIONS` constants in `captioner.py`. The track is explicitly about
  "prompt and have fun" — that's the place to experiment the most.
- Frame count — `MIN_FRAMES` / `MAX_FRAMES` / `SECONDS_PER_FRAME` in `frames.py`.
- Don't test only on the 3 examples in `test_input/` — per the spec the hidden
  set covers nature/urban/animals/people/sports/food/weather/technology, so add
  your own clips from categories not present in the examples.