#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://localhost:8080"
MODEL="llama-3.2-1b-instruct:q4_k_m"
REQUEST_TIMEOUT_SECONDS=120
EXIT_UNSUPPORTED_ON_TIMEOUT=false
UNSUPPORTED_EXIT_CODE=42

print_usage() {
  cat <<'USAGE'
Usage:
  ./test-localai-worker-mode.sh [options]

Options:
  --base-url URL | -BaseUrl URL
  --model NAME | -Model NAME
  --request-timeout-seconds N | -RequestTimeoutSeconds N
  --exit-unsupported-on-timeout
  --unsupported-exit-code N
  --help | -Help
USAGE
}

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: required command is not available in PATH: $cmd" >&2
    exit 1
  fi
}

print_standalone_endpoint_guidance() {
  local base_url="${1:-}"
  echo "This standalone smoke test does not automatically create the Kubernetes port-forward."
  echo "The specified BaseUrl must already be reachable before executing this script."
  echo "When running through the main launchers with http://localhost:8080, port-forwarding is managed automatically by the launcher layer."
  echo "If you are running this standalone script directly, prepare the endpoint first or create the port-forward to service/localai-server manually."
  if [[ -n "$base_url" ]]; then
    echo "Required BaseUrl: $base_url"
  fi
}

resolve_python_command() {
  if command -v python >/dev/null 2>&1 && python --version >/dev/null 2>&1; then
    printf '%s\n' python
    return 0
  fi
  if command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1; then
    printf '%s\n' python3
    return 0
  fi
  echo "No compatible Python interpreter is available in PATH. Verify that 'python' or 'python3' is available." >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url|-BaseUrl)
      BASE_URL="$2"
      shift 2
      ;;
    --model|-Model)
      MODEL="$2"
      shift 2
      ;;
    --request-timeout-seconds|-RequestTimeoutSeconds)
      REQUEST_TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    --exit-unsupported-on-timeout)
      EXIT_UNSUPPORTED_ON_TIMEOUT=true
      shift
      ;;
    --unsupported-exit-code)
      UNSUPPORTED_EXIT_CODE="$2"
      shift 2
      ;;
    --help|-Help)
      print_usage
      exit 0
      ;;
    *)
      echo "Unrecognized argument: $1" >&2
      print_usage >&2
      exit 1
      ;;
  esac
done

require_command curl
PYTHON_CMD="$(resolve_python_command)"

MODELS_TMP="$(mktemp)"
CHAT_TMP="$(mktemp)"
trap 'rm -f "$MODELS_TMP" "$CHAT_TMP"' EXIT

echo
echo "============================================="
echo " LocalAI Worker Mode Validation Script"
echo "============================================="
echo "Base URL : $BASE_URL"
echo "Model    : $MODEL"
echo
print_standalone_endpoint_guidance "$BASE_URL"
echo

echo "[1/3] Checking model availability through /v1/models ..."
set +e
curl -fsS   --connect-timeout 15   --max-time "$REQUEST_TIMEOUT_SECONDS"   "$BASE_URL/v1/models"   -o "$MODELS_TMP"
MODELS_CURL_EXIT_CODE=$?
set -e
if [[ $MODELS_CURL_EXIT_CODE -ne 0 ]]; then
  echo
  if [[ "$EXIT_UNSUPPORTED_ON_TIMEOUT" == "true" && $MODELS_CURL_EXIT_CODE -eq 28 ]]; then
    echo "SCENARIO UNSUPPORTED UNDER CURRENT CONSTRAINTS." >&2
    echo "API validation for model '$MODEL' did not complete within ${REQUEST_TIMEOUT_SECONDS} seconds." >&2
    echo "The condition is reported to the launcher as unsupported evidence; warm-up and measurement must be intentionally skipped." >&2
    exit "$UNSUPPORTED_EXIT_CODE"
  fi
  echo "API VALIDATION FAILED." >&2
  echo "Unable to obtain a valid response from $BASE_URL/v1/models" >&2
  print_standalone_endpoint_guidance "$BASE_URL" >&2
  exit 1
fi

if ! $PYTHON_CMD - "$MODELS_TMP" "$MODEL" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
required_model = sys.argv[2]

try:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
except Exception as exc:
    print(f"The /v1/models response is not valid JSON: {exc}", file=sys.stderr)
    raise SystemExit(1)

data = payload.get("data")
if not isinstance(data, list):
    print("The /v1/models response does not contain the 'data' field.", file=sys.stderr)
    raise SystemExit(1)

models = []
for item in data:
    if isinstance(item, dict) and isinstance(item.get("id"), str):
        models.append(item["id"])

print("Available models:")
for model in models:
    print(f" - {model}")

if required_model not in models:
    print(f"The requested model '{required_model}' is not present in the /v1/models response.", file=sys.stderr)
    raise SystemExit(1)
PY
then
  echo
  echo "API VALIDATION FAILED." >&2
  exit 1
fi

echo
echo "[2/3] Sending request to /v1/chat/completions ..."

REQUEST_BODY="$($PYTHON_CMD - "$MODEL" <<'PY'
import json
import sys
model = sys.argv[1]
payload = {
    "model": model,
    "messages": [
        {
            "role": "user",
            "content": "Reply with only READY.",
        }
    ],
    "temperature": 0.1,
}
print(json.dumps(payload, separators=(",", ":")))
PY
)"

set +e
curl -fsS \
  --connect-timeout 15 \
  --max-time "$REQUEST_TIMEOUT_SECONDS" \
  -H "Content-Type: application/json" \
  -X POST \
  -d "$REQUEST_BODY" \
  "$BASE_URL/v1/chat/completions" \
  -o "$CHAT_TMP"
CURL_EXIT_CODE=$?
set -e
if [[ $CURL_EXIT_CODE -ne 0 ]]; then
  echo
  if [[ "$EXIT_UNSUPPORTED_ON_TIMEOUT" == "true" && $CURL_EXIT_CODE -eq 28 ]]; then
    echo "SCENARIO UNSUPPORTED UNDER CURRENT CONSTRAINTS." >&2
    echo "API validation for model '$MODEL' did not complete within ${REQUEST_TIMEOUT_SECONDS} seconds." >&2
    echo "The condition is reported to the launcher as unsupported evidence; warm-up and measurement must be intentionally skipped." >&2
    exit "$UNSUPPORTED_EXIT_CODE"
  fi
  echo "API VALIDATION FAILED." >&2
  echo "Unable to obtain a valid response from $BASE_URL/v1/chat/completions" >&2
  print_standalone_endpoint_guidance "$BASE_URL" >&2
  exit 1
fi

MESSAGE_CONTENT="$($PYTHON_CMD - "$CHAT_TMP" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])

try:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
except Exception as exc:
    print(f"The /v1/chat/completions response is not valid JSON: {exc}", file=sys.stderr)
    raise SystemExit(1)

choices = payload.get("choices")
if not isinstance(choices, list) or not choices:
    print("The /v1/chat/completions response does not contain the 'choices' field.", file=sys.stderr)
    raise SystemExit(1)

choice = choices[0]
if not isinstance(choice, dict):
    print("The first 'choices' entry does not have a valid structure.", file=sys.stderr)
    raise SystemExit(1)

message = choice.get("message")
if not isinstance(message, dict):
    print("The response does not contain the 'message' field in the first choice.", file=sys.stderr)
    raise SystemExit(1)

content = message.get("content")
if not isinstance(content, str):
    print("The response does not contain 'message.content' as a string.", file=sys.stderr)
    raise SystemExit(1)

print(content)
PY
)" || {
  echo
  echo "API VALIDATION FAILED." >&2
  exit 1
}

echo
echo "[3/3] Response received successfully."
echo
echo "Generated message content:"
echo "---------------------------------------------"
printf '%s\n' "$MESSAGE_CONTENT"
echo "---------------------------------------------"
echo
echo "Full JSON response:"
$PYTHON_CMD -m json.tool "$CHAT_TMP"
echo
echo "API VALIDATION COMPLETED SUCCESSFULLY."
