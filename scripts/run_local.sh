set -euo pipefail
cd "$(dirname "$0")/.."


if [[ "$(uname -s 2>/dev/null || true)" == MINGW* || "$(uname -s 2>/dev/null || true)" == MSYS* ]]; then
  export MSYS_NO_PATHCONV=1
fi

IMAGE_NAME="video-captioning-agent:local"

if [ ! -f .env ]; then
  echo "No .env — first run: cp .env.example .env && fill in your keys" >&2
  exit 1
fi

echo "==> Building the image (linux/amd64, as on the judge)..."
docker build --platform linux/amd64 -t "$IMAGE_NAME" .

mkdir -p local_output
rm -f local_output/results.json

echo "==> Running against test_input/tasks.json..."
docker run --rm \
  -v "$(pwd)/test_input:/input:ro" \
  -v "$(pwd)/local_output:/output" \
  "$IMAGE_NAME"

echo "==> Done. Result:"
cat local_output/results.json | python3 -m json.tool