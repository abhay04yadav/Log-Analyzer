"""LLM provider adapter (Gemini via REST).

Only this module knows about the provider, so switching to another LLM means adding one class with
the same `generate_json` method.  Inputs are already secret-masked by the normaliser.
"""
import json
import time

import httpx

from app.core.config import get_settings

settings = get_settings()


class LLMError(RuntimeError):
    pass


class GeminiClient:
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str, timeout: float):
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def generate_json(self, system: str, prompt: str, schema: dict | None = None) -> tuple[dict, int]:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        }
        if schema:
            body["generationConfig"]["responseSchema"] = schema
        t0 = time.perf_counter()
        try:
            r = httpx.post(self.URL.format(model=self.model), json=body, timeout=self.timeout,
                           headers={"x-goog-api-key": self.api_key})
        except httpx.HTTPError as e:
            raise LLMError(f"Gemini request failed: {e}") from e
        ms = int((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            try:
                msg = r.json().get("error", {}).get("message", r.text)
            except ValueError:
                msg = r.text
            raise LLMError(f"Gemini HTTP {r.status_code}: {msg[:300]}")
        try:
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text), ms
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError(f"Gemini returned an unexpected response: {str(r.text)[:300]}") from e


class FallbackLLM:
    """Tries the primary model, then the fallback model (timeouts, quota errors, retired models)."""

    def __init__(self, clients: list[GeminiClient]):
        self.clients = clients
        self.model = clients[0].model

    def generate_json(self, system: str, prompt: str, schema: dict | None = None) -> tuple[dict, int]:
        errors = []
        for c in self.clients:
            try:
                result = c.generate_json(system, prompt, schema)
                self.model = c.model                   # report the model that actually answered
                return result
            except LLMError as e:
                errors.append(f"{c.model}: {e}")
        raise LLMError("; ".join(errors))


def get_llm() -> FallbackLLM | None:
    if not settings.llm_enabled:
        return None
    models = [settings.gemini_model] + [m for m in [settings.gemini_fallback_model]
                                        if m and m != settings.gemini_model]
    return FallbackLLM([GeminiClient(settings.gemini_api_key, m, settings.llm_timeout_seconds) for m in models])
