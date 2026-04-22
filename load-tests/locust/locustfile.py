import os
from locust import HttpUser, task, constant

MODEL_NAME = os.getenv("LOCALAI_MODEL", "llama-3.2-1b-instruct:q4_k_m")
TEMPERATURE = float(os.getenv("LOCALAI_TEMPERATURE", "0.1"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("LOCALAI_REQUEST_TIMEOUT_SECONDS", "120"))
PROMPT_TEXT = os.getenv("LOCALAI_PROMPT", "Reply with only READY.")
STARTUP_MODEL_CHECK_ENABLED = os.getenv("LOCALAI_STARTUP_MODEL_CHECK_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


class LocalAIWorkerModeUser(HttpUser):
    wait_time = constant(2)

    def on_start(self) -> None:
        if not STARTUP_MODEL_CHECK_ENABLED:
            return

        with self.client.get(
            "/v1/models",
            name="GET /v1/models (startup check)",
            catch_response=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Unexpected status code from /v1/models: {response.status_code}")
                return

            try:
                payload = response.json()
            except Exception as exc:
                response.failure(f"Invalid JSON from /v1/models: {exc}")
                return

            models = payload.get("data", [])
            model_ids = {item.get("id") for item in models if isinstance(item, dict)}
            if MODEL_NAME not in model_ids:
                response.failure(f"Model '{MODEL_NAME}' not exposed by /v1/models")
            else:
                response.success()

    @task
    def chat_completion(self) -> None:
        body = {
            "model": MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": PROMPT_TEXT,
                }
            ],
            "temperature": TEMPERATURE,
        }

        with self.client.post(
            "/v1/chat/completions",
            json=body,
            name="POST /v1/chat/completions",
            catch_response=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Unexpected status code: {response.status_code} | body={response.text}")
                return

            try:
                payload = response.json()
            except Exception as exc: 
                response.failure(f"Invalid JSON from chat completion: {exc}")
                return

            choices = payload.get("choices")
            if not isinstance(choices, list) or not choices:
                response.failure("Response JSON does not contain a non-empty 'choices' array")
                return

            message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                response.failure("Response JSON does not contain assistant message content")
                return

            response.success()
