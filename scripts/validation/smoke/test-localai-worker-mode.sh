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
    echo "Errore: il comando richiesto non è disponibile nel PATH: $cmd" >&2
    exit 1
  fi
}

print_standalone_endpoint_guidance() {
  local base_url="${1:-}"
  echo "Questo smoke test standalone non crea automaticamente il port-forward Kubernetes."
  echo "Il BaseUrl specificato deve essere già raggiungibile prima dell'esecuzione dello script."
  echo "Se stai eseguendo la pipeline tramite i launcher principali e usi http://localhost:8080, il port-forward viene gestito automaticamente a livello di launcher."
  echo "Se invece stai eseguendo direttamente questo script standalone, prepara prima l'endpoint oppure crea manualmente il port-forward verso service/localai-server."
  if [[ -n "$base_url" ]]; then
    echo "BaseUrl richiesto: $base_url"
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
      echo "Argomento non riconosciuto: $1" >&2
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

echo "[1/3] Verifica disponibilita' del modello tramite /v1/models ..."
if ! curl -fsS "$BASE_URL/v1/models" -o "$MODELS_TMP"; then
  echo
  echo "ERRORE DURANTE LA VALIDAZIONE API." >&2
  echo "Impossibile ottenere una risposta valida da $BASE_URL/v1/models" >&2
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
    print(f"La risposta di /v1/models non è un JSON valido: {exc}", file=sys.stderr)
    raise SystemExit(1)

data = payload.get("data")
if not isinstance(data, list):
    print("La risposta di /v1/models non contiene il campo 'data'.", file=sys.stderr)
    raise SystemExit(1)

models = []
for item in data:
    if isinstance(item, dict) and isinstance(item.get("id"), str):
        models.append(item["id"])

print("Modelli disponibili:")
for model in models:
    print(f" - {model}")

if required_model not in models:
    print(f"Il modello richiesto '{required_model}' non è presente nella risposta di /v1/models.", file=sys.stderr)
    raise SystemExit(1)
PY
then
  echo
  echo "ERRORE DURANTE LA VALIDAZIONE API." >&2
  exit 1
fi

echo
echo "[2/3] Invio richiesta a /v1/chat/completions ..."

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
    echo "SCENARIO OPERATIVAMENTE NON SUPPORTATO." >&2
    echo "La richiesta di smoke test verso /v1/chat/completions per il modello '$MODEL' non ha restituito una risposta entro ${REQUEST_TIMEOUT_SECONDS} secondi." >&2
    echo "Il modello viene classificato come non supportato operativamente nella configurazione corrente." >&2
    exit "$UNSUPPORTED_EXIT_CODE"
  fi
  echo "ERRORE DURANTE LA VALIDAZIONE API." >&2
  echo "Impossibile ottenere una risposta valida da $BASE_URL/v1/chat/completions" >&2
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
    print(f"La risposta di /v1/chat/completions non è un JSON valido: {exc}", file=sys.stderr)
    raise SystemExit(1)

choices = payload.get("choices")
if not isinstance(choices, list) or not choices:
    print("La risposta di /v1/chat/completions non contiene il campo 'choices'.", file=sys.stderr)
    raise SystemExit(1)

choice = choices[0]
if not isinstance(choice, dict):
    print("La prima entry di 'choices' non ha una struttura valida.", file=sys.stderr)
    raise SystemExit(1)

message = choice.get("message")
if not isinstance(message, dict):
    print("La risposta non contiene il campo 'message' nella prima choice.", file=sys.stderr)
    raise SystemExit(1)

content = message.get("content")
if not isinstance(content, str):
    print("La risposta non contiene 'message.content' come stringa.", file=sys.stderr)
    raise SystemExit(1)

print(content)
PY
)" || {
  echo
  echo "ERRORE DURANTE LA VALIDAZIONE API." >&2
  exit 1
}

echo
echo "[3/3] Risposta ricevuta correttamente."
echo
echo "Contenuto del messaggio generato:"
echo "---------------------------------------------"
printf '%s\n' "$MESSAGE_CONTENT"
echo "---------------------------------------------"
echo
echo "Risposta JSON completa:"
$PYTHON_CMD -m json.tool "$CHAT_TMP"
echo
echo "VALIDAZIONE API COMPLETATA CON SUCCESSO."
