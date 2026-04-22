#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://localhost:8080"
MODEL="llama-3.2-1b-instruct:q4_k_m"
ITERATIONS=5
PAUSE_SECONDS=2
OUTPUT_PREFIX=""
METRIC_SET_CONFIG=""

print_usage() {
  cat <<'USAGE'
Usage:
  ./export-validation-metrics.sh [options]

Options:
  --base-url URL | -BaseUrl URL
  --model NAME | -Model NAME
  --iterations N | -Iterations N
  --pause-seconds N | -PauseSeconds N
  --output-prefix PREFIX | -OutputPrefix PREFIX
  --metric-set-config PATH | -MetricSetConfig PATH
  --help | -Help
USAGE
}

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Errore: il comando richiesto non è disponibile nel PATH: $cmd" >&2
    exit 1
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
  echo "Nessun interprete Python compatibile e disponibile nel PATH. Verificare la disponibilita' di 'python' oppure 'python3'." >&2
  exit 1
}

resolve_repo_root() {
  local script_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  cd -- "$script_dir/../../.." && pwd
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
    --iterations|-Iterations)
      ITERATIONS="$2"
      shift 2
      ;;
    --pause-seconds|-PauseSeconds)
      PAUSE_SECONDS="$2"
      shift 2
      ;;
    --output-prefix|-OutputPrefix)
      OUTPUT_PREFIX="$2"
      shift 2
      ;;
    --metric-set-config|-MetricSetConfig)
      METRIC_SET_CONFIG="$2"
      shift 2
      ;;
    --help|-Help)
      print_usage
      exit 0
      ;;
    *)
      echo "Argomento non riconosciuto: $1" >&2
      print_usage >&2
      exit 1
      ;;
  esac
done

PYTHON_CMD="$(resolve_python_command)"

REPO_ROOT="$(resolve_repo_root)"

if [[ -z "$OUTPUT_PREFIX" ]]; then
  OUTPUT_PREFIX="$REPO_ROOT/results/validation/minimal-metrics"
fi

if [[ -z "$METRIC_SET_CONFIG" ]]; then
  METRIC_SET_CONFIG="$REPO_ROOT/config/metric-set/MS1.json"
fi

if [[ ! -f "$METRIC_SET_CONFIG" ]]; then
  echo "Il file di metric set non esiste: $METRIC_SET_CONFIG" >&2
  exit 1
fi

OUTPUT_DIRECTORY="$(dirname -- "$OUTPUT_PREFIX")"
mkdir -p -- "$OUTPUT_DIRECTORY"

echo "============================================="
echo " LocalAI Minimal Metrics Validation"
echo "============================================="
echo "Repository   : $REPO_ROOT"
echo "Base URL     : $BASE_URL"
echo "Model        : $MODEL"
echo "Iterations   : $ITERATIONS"
echo "Pause (sec)  : $PAUSE_SECONDS"
echo "OutputPrefix : $OUTPUT_PREFIX"
echo "Metric set   : $METRIC_SET_CONFIG"
echo

BASE_URL="$BASE_URL" \
MODEL="$MODEL" \
ITERATIONS="$ITERATIONS" \
PAUSE_SECONDS="$PAUSE_SECONDS" \
OUTPUT_PREFIX="$OUTPUT_PREFIX" \
METRIC_SET_CONFIG="$METRIC_SET_CONFIG" \
"$PYTHON_CMD" <<'PY'
import csv
import json
import os
import time
import urllib.request
from datetime import datetime, timezone


def percentile(values, p):
    if not values:
        return None
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return round(sorted_values[0], 2)
    rank = (p / 100) * (len(sorted_values) - 1)
    lower_index = int(rank)
    upper_index = lower_index if rank.is_integer() else lower_index + 1
    if lower_index == upper_index:
        return round(sorted_values[lower_index], 2)
    weight = rank - lower_index
    value = sorted_values[lower_index] + (sorted_values[upper_index] - sorted_values[lower_index]) * weight
    return round(value, 2)


base_url = os.environ["BASE_URL"]
model = os.environ["MODEL"]
iterations = int(os.environ["ITERATIONS"])
pause_seconds = int(os.environ["PAUSE_SECONDS"])
output_prefix = os.environ["OUTPUT_PREFIX"]
metric_set_config = os.environ["METRIC_SET_CONFIG"]

with open(metric_set_config, "r", encoding="utf-8-sig") as fh:
    metric_set_profile = json.load(fh)

results = []
batch_start = time.perf_counter()

for i in range(1, iterations + 1):
    prompt = f"Reply with only READY-{i}."
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }
    encoded_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
    timestamp = datetime.now(timezone.utc).astimezone().isoformat()
    start = time.perf_counter()

    row = {
        "iteration": i,
        "timestamp": timestamp,
        "success": False,
        "latency_ms": None,
        "model": model,
        "finish_reason": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "prompt": prompt,
        "response_content": None,
        "error_message": None,
    }

    request = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/v1/chat/completions",
        data=encoded_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw_payload = response.read().decode("utf-8")
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        payload = json.loads(raw_payload)

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("Response JSON does not contain a non-empty 'choices' array")

        choice = choices[0]
        if not isinstance(choice, dict):
            raise ValueError("First choice is not a valid object")

        message = choice.get("message")
        if not isinstance(message, dict):
            raise ValueError("Response JSON does not contain 'message' in first choice")

        content = message.get("content")
        if not isinstance(content, str):
            raise ValueError("Response JSON does not contain assistant message content")

        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}

        row.update(
            {
                "success": True,
                "latency_ms": latency_ms,
                "model": payload.get("model", model),
                "finish_reason": choice.get("finish_reason"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "response_content": content,
            }
        )
        print(f"[{i}/{iterations}] OK - latency: {latency_ms} ms - response: {content}")
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        row.update({"latency_ms": latency_ms, "error_message": str(exc)})
        print(f"[{i}/{iterations}] ERROR - latency: {latency_ms} ms - error: {exc}")

    results.append(row)

    if i < iterations:
        time.sleep(pause_seconds)

success_rows = [row for row in results if row["success"]]
latencies = [row["latency_ms"] for row in success_rows if row["latency_ms"] is not None]
successful_requests = len(success_rows)
failed_requests = len(results) - successful_requests
success_rate_percent = round((successful_requests / iterations) * 100, 2) if iterations > 0 else 0
elapsed_seconds = round(time.perf_counter() - batch_start, 4)
throughput_rps = round(successful_requests / elapsed_seconds, 4) if elapsed_seconds > 0 else None
mean_response_time = round(sum(latencies) / len(latencies), 2) if latencies else None

summary = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "base_url": base_url,
    "model": model,
    "metric_set_profile_id": metric_set_profile.get("profileId"),
    "iterations": iterations,
    "request_count": len(results),
    "successful_requests": successful_requests,
    "failed_requests": failed_requests,
    "failure_count": failed_requests,
    "success_rate_percent": success_rate_percent,
    "mean_response_time_ms": mean_response_time,
    "p50_response_time_ms": percentile(latencies, 50),
    "p95_response_time_ms": percentile(latencies, 95),
    "p99_response_time_ms": percentile(latencies, 99),
    "throughput_rps": throughput_rps,
    "avg_latency_ms": mean_response_time,
    "min_latency_ms": round(min(latencies), 2) if latencies else None,
    "max_latency_ms": round(max(latencies), 2) if latencies else None,
    "p50_latency_ms": percentile(latencies, 50),
    "p95_latency_ms": percentile(latencies, 95),
    "total_prompt_tokens": sum((row["prompt_tokens"] or 0) for row in success_rows),
    "total_completion_tokens": sum((row["completion_tokens"] or 0) for row in success_rows),
    "total_tokens": sum((row["total_tokens"] or 0) for row in success_rows),
}

csv_path = f"{output_prefix}-results.csv"
json_path = f"{output_prefix}-summary.json"

with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
    fieldnames = list(results[0].keys()) if results else [
        "iteration", "timestamp", "success", "latency_ms", "model", "finish_reason",
        "prompt_tokens", "completion_tokens", "total_tokens", "prompt", "response_content", "error_message"
    ]
    writer = csv.DictWriter(fh, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(results)

with open(json_path, "w", encoding="utf-8-sig") as fh:
    json.dump(summary, fh, indent=2)
    fh.write("\n")

print("")
print("==================== SUMMARY ====================")
for key, value in summary.items():
    print(f"{key}: {value}")
print("=================================================")
print("")
print(f"Risultati salvati in: {csv_path}")
print(f"Riepilogo salvato in: {json_path}")
PY
