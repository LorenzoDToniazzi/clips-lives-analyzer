from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from clips_lives_analyzer.config import AnalyzerConfig


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, config: AnalyzerConfig):
        self.config = config
        parsed = urllib.parse.urlparse(config.ollama_url)
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Por privacidade, ollama_url deve apontar para este computador.")
        self.base_url = config.ollama_url.rstrip("/")

    def _request(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        data = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None
        )
        request = urllib.request.Request(
            f"{self.base_url}{endpoint}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout or self.config.ollama_timeout_seconds,
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise OllamaError(
                "O Ollama local não respondeu. Abra o Ollama ou rode INSTALAR.bat."
            ) from exc
        except json.JSONDecodeError as exc:
            raise OllamaError("O Ollama retornou uma resposta inválida.") from exc

    def version(self) -> str:
        response = self._request("GET", "/api/version", timeout=10)
        return str(response.get("version", "desconhecida"))

    def installed_models(self) -> list[str]:
        response = self._request("GET", "/api/tags", timeout=20)
        return [
            str(item.get("name"))
            for item in response.get("models", [])
            if item.get("name")
        ]

    def require_models(self) -> None:
        installed = set(self.installed_models())
        missing = [
            model
            for model in {self.config.text_model, self.config.vision_model}
            if model not in installed
        ]
        if missing:
            raise OllamaError(
                "Modelo local ausente: "
                + ", ".join(missing)
                + ". Rode INSTALAR.bat novamente."
            )

    @staticmethod
    def _encoded_images(images: list[Path] | None) -> list[str]:
        return [
            base64.b64encode(path.read_bytes()).decode("ascii")
            for path in (images or [])
        ]

    def generate_json(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        images: list[Path] | None = None,
        temperature: float = 0.1,
        num_ctx: int | None = None,
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "system": system,
            "prompt": prompt,
            "images": self._encoded_images(images),
            "format": schema,
            "stream": False,
            "think": False,
            "keep_alive": "10m",
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx or self.config.ollama_context,
            },
        }
        response = self._request("POST", "/api/generate", payload)
        if response.get("error"):
            raise OllamaError(str(response["error"]))
        content = response.get("response")
        if not isinstance(content, str):
            raise OllamaError("O modelo local não retornou texto.")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise OllamaError(
                f"O modelo não respeitou o JSON obrigatório: {content[:400]}"
            ) from exc
