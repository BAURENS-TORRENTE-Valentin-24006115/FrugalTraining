"""Conversation client for a local or remote AI provider."""

import json
import urllib.error
import urllib.request
from collections.abc import Iterator

from settings import AI_ENDPOINTS, AI_MODELS


def _text_from_event(event: dict, provider: str) -> list[str]:
    """Extract assistant text from an OpenAI-compatible completion event."""
    if "error" in event:
        error = event["error"]
        message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        raise RuntimeError(f"Erreur {provider} : {message}")

    text = []
    for choice in event.get("choices", []):
        delta = choice.get("delta") or {}
        message = choice.get("message") or {}
        content = delta.get("content") or message.get("content") or ""
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        if content:
            text.append(content)
    return text


class AI:
    """Represent one AI instance with its own configuration and conversation history.

    ``model``, ``base_url``, ``api_key`` and ``system_prompt`` can be changed
    between calls to ``chat`` or ``stream_chat``.
    """

    def __init__(
        self,
        provider: str = "local",
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> None:
        provider = provider.lower()
        if provider not in AI_ENDPOINTS:
            raise ValueError(f"Fournisseur inconnu : {provider}")

        self.provider = provider
        self.model = model or AI_MODELS[provider]
        self.base_url = (base_url or AI_ENDPOINTS[provider]).rstrip("/")
        self.api_key = api_key or ""
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.messages: list[dict[str, str]] = []
        self.system_prompt = system_prompt

    @property
    def system_prompt(self) -> str | None:
        if self.messages and self.messages[0]["role"] == "system":
            return self.messages[0]["content"]
        return None

    @system_prompt.setter
    def system_prompt(self, content: str | None) -> None:
        if self.messages and self.messages[0]["role"] == "system":
            self.messages.pop(0)
        if content:
            self.messages.insert(0, {"role": "system", "content": content})

    def set_system_prompt(self, content: str) -> None:
        """Keep the method for callers using the older API."""
        self.system_prompt = content

    def clear_history(self, keep_system_prompt: bool = True) -> None:
        prompt = self.system_prompt if keep_system_prompt else None
        self.messages.clear()
        self.system_prompt = prompt

    def stream_chat(
        self,
        prompt: str,
        keep_history: bool = True,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        """Send a message and yield response fragments as they arrive."""
        if self.provider != "local" and not self.api_key:
            raise ValueError(f"Clé API manquante pour {self.provider}")

        payload = {
            "model": self.model,
            "messages": [*self.messages, {"role": "user", "content": prompt}],
            "stream": True,
            "temperature": self.temperature if temperature is None else temperature,
        }
        token_limit = self.max_tokens if max_tokens is None else max_tokens
        if token_limit is not None:
            payload["max_tokens"] = token_limit

        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
        )

        chunks: list[str] = []
        last_event: dict = {}
        response_type = "unknown"
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                response_type = response.headers.get_content_type()
                if response_type == "application/json":
                    event = json.load(response)
                    last_event = event
                    for chunk in _text_from_event(event, self.provider):
                        chunks.append(chunk)
                        yield chunk
                else:
                    for raw_line in response:
                        line = raw_line.decode("utf-8", errors="replace").strip().lstrip("\ufeff")
                        if line.startswith("data:"):
                            data = line[5:].strip()
                            if data == "[DONE]":
                                break
                        elif line.startswith("{"):
                            # Beacon can wrap an upstream JSON error in an SSE response.
                            data = line
                        else:
                            continue
                        if not data:
                            continue
                        event = json.loads(data)
                        last_event = event
                        for chunk in _text_from_event(event, self.provider):
                            chunks.append(chunk)
                            yield chunk
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Erreur HTTP {exc.code} ({self.provider}) : {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Connexion impossible à {self.provider} : {exc.reason}") from exc

        if not chunks:
            choices = last_event.get("choices", [])
            choice = choices[0] if choices else {}
            finish_reason = choice.get("finish_reason")
            delta_fields = sorted((choice.get("delta") or {}).keys())
            details = f"; response type={response_type}"
            if finish_reason:
                details += f"; finish_reason={finish_reason}"
            if delta_fields:
                details += f"; delta fields={', '.join(delta_fields)}"
            if not last_event:
                details += "; no completion event received"
            raise RuntimeError(
                f"{self.provider} a terminé la réponse sans générer de texte{details}"
            )

        if keep_history:
            self.messages.extend((
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "".join(chunks)},
            ))

    def chat(
        self,
        prompt: str,
        keep_history: bool = True,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Return the complete response."""
        return "".join(self.stream_chat(prompt, keep_history, temperature, max_tokens))
