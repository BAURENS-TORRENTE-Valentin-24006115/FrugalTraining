"""
AI Unified Client Module
Supports both local LLM server (MAIA Beacon / llama.cpp) and Cloud APIs (DeepSeek, Mistral, Gemini).
Features word-by-word streaming generation and optional conversation memory.
"""

import os
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Generator, List, Dict, Any, Optional


def load_env_file(env_path: Optional[Path] = None) -> Dict[str, str]:
    """Parse .env file into a dictionary of key-value pairs."""
    env_vars = {}
    if env_path is None:
        env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip().strip("'\"")
        except Exception:
            pass
    return env_vars


class AI:
    """
    Unified AI Client for switching between Local LLM and Cloud APIs.
    """

    DEFAULT_ENDPOINTS = {
        "local": "http://127.0.0.1:11343/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "mistral": "https://api.mistral.ai/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    }

    DEFAULT_MODELS = {
        "local": "Ministral-3-3B-Instruct-2512-Q4_K_M.gguf",
        "deepseek": "deepseek-chat",
        "mistral": "open-mistral-nemo",
        "gemini": "gemini-1.5-pro",
    }

    ENV_KEY_NAMES = {
        "deepseek": "DEEPSEEK_API",
        "mistral": "MISTRAL_API",
        "gemini": "GEMINI_API",
    }

    def __init__(
        self,
        provider: str = "local",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ):
        """
        Initialize the AI client.
        
        :param provider: "local", "deepseek", "mistral", or "gemini"
        :param model: Specific model identifier (optional, uses provider defaults)
        :param api_key: API key override (optional, loaded from .env by default)
        :param base_url: API Base URL override (optional)
        :param system_prompt: Initial system context for the model (optional)
        """
        self.provider = provider.lower()
        self.use_api = self.provider != "local"
        self.model = model or self.DEFAULT_MODELS.get(self.provider, "default")
        self.base_url = (base_url or self.DEFAULT_ENDPOINTS.get(self.provider, "http://127.0.0.1:11343/v1")).rstrip("/")

        # Load API key from parameter, os.environ, or .env file
        env_vars = load_env_file()
        env_key_name = self.ENV_KEY_NAMES.get(self.provider, f"{self.provider.upper()}_API")
        self.api_key = api_key or os.environ.get(env_key_name) or env_vars.get(env_key_name, "")

        self.messages: List[Dict[str, str]] = []

        if system_prompt:
            self.set_system_prompt(system_prompt)

    def set_system_prompt(self, content: str) -> None:
        """Set or update the system prompt at the beginning of the conversation history."""
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = content
        else:
            self.messages.insert(0, {"role": "system", "content": content})

    def clear_history(self, keep_system_prompt: bool = True) -> None:
        """Clear conversation history, optionally preserving the system prompt."""
        if keep_system_prompt and self.messages and self.messages[0].get("role") == "system":
            self.messages = [self.messages[0]]
        else:
            self.messages = []

    def stream_chat(
        self,
        prompt: str,
        keep_history: bool = True,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Generator[str, None, None]:
        """
        Send a prompt and stream the response word-by-word (Server-Sent Events).
        
        :param prompt: User message to send
        :param keep_history: Whether to save this exchange in conversation memory
        :param temperature: Sampling temperature
        :param max_tokens: Maximum tokens to generate
        :return: Generator yielding text chunks as they arrive from the model
        """
        # Prepare request messages context
        request_messages = list(self.messages)
        request_messages.append({"role": "user", "content": prompt})

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AI-Python-Client/1.0",
        }

        if self.use_api and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": request_messages,
            "stream": True,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        import subprocess
        import json

        payload_json = json.dumps(payload, ensure_ascii=False)
        cmd = ["curl.exe", "-s", "-N", "-X", "POST", url]
        for h_key, h_val in headers.items():
            cmd.extend(["-H", f"{h_key}: {h_val}"])
        cmd.extend(["-d", "@-"])

        full_response_text = []

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            try:
                proc.stdin.write(payload_json)
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data_json = json.loads(data_str)
                        choices = data_json.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content_chunk = delta.get("content", "")
                            if content_chunk:
                                full_response_text.append(content_chunk)
                                yield content_chunk
                    except json.JSONDecodeError:
                        continue
                elif line.startswith("{") and "error" in line:
                    try:
                        err_obj = json.loads(line)
                        err_msg = err_obj.get("error", {}).get("message") or line
                        raise RuntimeError(f"API Error from {self.provider}: {err_msg}")
                    except json.JSONDecodeError:
                        pass

            proc.stdout.close()
            proc.wait(timeout=5)
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            raise RuntimeError(f"Streaming error with {self.provider} ({url}): {e}") from e

        # If memory retention is active, update self.messages
        if keep_history:
            self.messages.append({"role": "user", "content": prompt})
            self.messages.append({"role": "assistant", "content": "".join(full_response_text)})

    def chat(
        self,
        prompt: str,
        keep_history: bool = True,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Send a prompt and return the complete string response (aggregates stream).
        """
        chunks = list(
            self.stream_chat(
                prompt=prompt,
                keep_history=keep_history,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )
        return "".join(chunks)


# Backward compatibility alias
ai = AI