"""
OpenRouter chat-completions backend for multimodal image judging.
"""

import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-5.5"


class ModelUnavailableError(RuntimeError):
    """Raised when OpenRouter rejects a model slug."""


class OpenRouterJudge:
    def __init__(
        self,
        model,
        max_batch_size=24,
        max_new_tokens=4096,
        api_key=None,
        base_url=DEFAULT_OPENROUTER_BASE_URL,
        request_timeout=120,
        site_url=None,
        site_title="Image Bench",
        max_retries=3,
    ):
        self.model = model
        self.max_batch_size = max_batch_size
        self.max_new_tokens = max_new_tokens
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.request_timeout = request_timeout
        self.site_url = site_url or os.getenv("OPENROUTER_SITE_URL")
        self.site_title = site_title or os.getenv("OPENROUTER_SITE_TITLE") or "Image Bench"
        self.max_retries = max_retries

        if not self.api_key:
            raise ValueError(
                "OpenRouter API key not provided. Set OPENROUTER_API_KEY or pass --openrouter-api-key."
            )

    def generate_batch(self, items):
        """
        Execute a list of independent judge requests and return outputs in input order.
        """
        if not items:
            return []

        outputs = [None] * len(items)
        max_workers = max(1, min(self.max_batch_size, len(items)))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(self._generate_one, item): index
                for index, item in enumerate(items)
            }
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                outputs[index] = future.result()

        return outputs

    def _generate_one(self, item):
        messages = [
            {"role": "system", "content": item["system_prompt"]},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": item["user_text"]},
                    {
                        "type": "image_url",
                        "image_url": {"url": item["image_data_url"]},
                    },
                ],
            },
        ]

        try:
            return self._request_completion(self.model, messages)
        except ModelUnavailableError as exc:
            raise RuntimeError(str(exc)) from exc

    def _request_completion(self, model, messages):
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": self.max_new_tokens,
            "temperature": 0,
            "top_p": 1,
            "stream": False,
        }

        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers=self._headers(),
            method="POST",
        )

        delay_seconds = 1.0
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
                    data = json.load(response)
                return self._extract_text(data)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if self._is_model_unavailable(exc.code, detail):
                    raise ModelUnavailableError(
                        f"OpenRouter rejected model '{model}': {detail.strip()}"
                    ) from exc
                if exc.code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    last_error = exc
                    time.sleep(delay_seconds)
                    delay_seconds *= 2
                    continue
                raise RuntimeError(
                    f"OpenRouter request failed with HTTP {exc.code}: {detail.strip()}"
                ) from exc
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(delay_seconds)
                    delay_seconds *= 2
                    continue
                raise RuntimeError(f"OpenRouter request failed: {exc}") from exc

        raise RuntimeError(f"OpenRouter request failed after retries: {last_error}")

    def _headers(self):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.site_title:
            headers["X-OpenRouter-Title"] = self.site_title
        return headers

    @staticmethod
    def _extract_text(data):
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"OpenRouter response did not include choices: {data}")

        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
            if text_parts:
                return "".join(text_parts)

        raise RuntimeError(f"OpenRouter response did not include text content: {data}")

    @staticmethod
    def _is_model_unavailable(status_code, detail):
        if status_code not in {400, 404}:
            return False
        normalized = detail.lower()
        if "model" not in normalized:
            return False
        return (
            "not found" in normalized
            or "does not exist" in normalized
            or "invalid" in normalized
            or "unsupported" in normalized
        )
