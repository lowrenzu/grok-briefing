#!/usr/bin/env python3
"""Réglages du cerveau IA de JARVIS : fournisseurs, clés et modèles.

Ce module est le seul endroit qui connaît les clés. Elles restent dans
`config.json`, côté serveur : le navigateur ne reçoit jamais qu'une version
masquée (`••••…4f2a`). Aucune clé ne transite par la page web.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MAX_ANSWER_CHARS = 6000
MAX_HISTORY_MESSAGES = 10
REQUEST_TIMEOUT = 45

# Un libellé, une famille d'API et une adresse par défaut. `kind` décide du format
# de la requête : `anthropic` (API Messages) ou `openai` (chat/completions, le
# standard de fait, aussi parlé par Ollama, LM Studio et OpenRouter).
PROVIDERS: dict[str, dict[str, Any]] = {
    "anthropic": {
        "default_model": "claude-sonnet-5-5",
        "label": "Anthropic (Claude)",
        "kind": "anthropic",
        "url": "https://api.anthropic.com/v1/messages",
        "needs_key": True,
        "editable_url": False,
        "key_url": "https://console.anthropic.com/settings/keys",
        "hint": "Clé « sk-ant-… » créée dans la console Anthropic.",
    },
    "openai": {
        "default_model": "gpt-4o-mini",
        "label": "OpenAI (GPT)",
        "kind": "openai",
        "url": "https://api.openai.com/v1/chat/completions",
        "needs_key": True,
        "editable_url": False,
        "key_url": "https://platform.openai.com/api-keys",
        "hint": "Clé « sk-… » créée dans la plateforme OpenAI.",
    },
    "mistral": {
        "default_model": "mistral-small-latest",
        "label": "Mistral AI",
        "kind": "openai",
        "url": "https://api.mistral.ai/v1/chat/completions",
        "needs_key": True,
        "editable_url": False,
        "key_url": "https://console.mistral.ai/api-keys",
        "hint": "Clé créée dans la console Mistral.",
    },
    "groq": {
        "default_model": "llama-3.3-70b-versatile",
        "label": "Groq (rapide)",
        "kind": "openai",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "needs_key": True,
        "editable_url": False,
        "key_url": "https://console.groq.com/keys",
        "hint": "Clé « gsk_… » créée dans la console Groq.",
    },
    "ollama": {
        "default_model": "llama3.2",
        "label": "Ollama (sur votre PC)",
        "kind": "openai",
        "url": "http://127.0.0.1:11434/v1/chat/completions",
        "needs_key": False,
        "editable_url": True,
        "key_url": "https://ollama.com/download",
        "hint": "Gratuit et hors ligne. Lancez « ollama serve » puis choisissez un modèle installé.",
    },
    "custom": {
        "default_model": "",
        "label": "Autre service (compatible OpenAI)",
        "kind": "openai",
        "url": "",
        "needs_key": False,
        "editable_url": True,
        "key_url": "",
        "hint": "LM Studio, OpenRouter, vLLM… indiquez l’adresse complète en …/v1/chat/completions.",
    },
}

DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-opus-4-8"
PLACEHOLDER_KEYS = {"put-your-key-here", "votre-cle-api-ici", "changeme", "your-key-here"}
MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/@-]{0,119}")
KEY_PATTERN = re.compile(r"[\x21-\x7e]{4,300}")
ENV_KEYS = ("JARVIS_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")


class SettingsError(ValueError):
    """Erreur lisible par l'utilisateur (message affiché tel quel dans le panneau)."""


def provider_spec(name: str) -> dict[str, Any]:
    return PROVIDERS.get(name, PROVIDERS[DEFAULT_PROVIDER])


def check_base_url(url: str) -> str:
    """Valide une adresse d'API : http(s) uniquement, sans identifiants embarqués."""
    url = (url or "").strip()
    if not url:
        raise SettingsError("Indiquez l’adresse de l’API (…/v1/chat/completions).")
    if len(url) > 400:
        raise SettingsError("L’adresse de l’API est trop longue.")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise SettingsError("L’adresse doit commencer par http:// ou https://.")
    if not parts.hostname:
        raise SettingsError("Cette adresse ne contient pas de nom de machine valide.")
    if parts.username or parts.password:
        raise SettingsError("N’inscrivez pas d’identifiants dans l’adresse : utilisez le champ clé.")
    return url


def check_api_key(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.casefold() in PLACEHOLDER_KEYS:
        raise SettingsError("Remplacez l’exemple par votre véritable clé.")
    if not KEY_PATTERN.fullmatch(value):
        raise SettingsError("La clé contient des caractères inattendus (espaces ou retours à la ligne ?).")
    return value


def mask_key(value: str) -> str:
    if not value:
        return ""
    tail = value[-4:] if len(value) > 8 else ""
    return f"••••••••{tail}"


class AiSettings:
    """Réglages vivants : modifiables depuis l'interface, appliqués sans redémarrage."""

    def __init__(self, config_path: Path) -> None:
        self.path = config_path
        self._lock = threading.RLock()
        self._values: dict[str, Any] = {}
        self._raw: dict[str, Any] = {}
        self.reload()

    # --- lecture -----------------------------------------------------------
    def reload(self) -> None:
        raw: dict[str, Any] = {}
        if self.path.is_file():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    raw = loaded
            except (OSError, json.JSONDecodeError):
                raw = {}
        with self._lock:
            self._raw = raw
            provider = str(raw.get("provider") or DEFAULT_PROVIDER).strip().casefold()
            if provider not in PROVIDERS:
                provider = DEFAULT_PROVIDER
            spec = PROVIDERS[provider]
            fallback = str(spec.get("default_model") or DEFAULT_MODEL)
            model = str(raw.get("model") or fallback).strip()
            if not MODEL_PATTERN.fullmatch(model):
                model = fallback
            key = str(raw.get("api_key") or "").strip()
            if key.casefold() in PLACEHOLDER_KEYS:
                key = ""
            base_url = str(raw.get("base_url") or "").strip() or spec["url"]
            self._values = {
                "provider": provider,
                "model": model,
                "api_key": key,
                "base_url": base_url,
                "notes_dir": str(raw.get("notes_dir") or ""),
            }

    @property
    def provider(self) -> str:
        return self._values["provider"]

    @property
    def spec(self) -> dict[str, Any]:
        return provider_spec(self.provider)

    @property
    def model(self) -> str:
        return self._values["model"]

    @property
    def base_url(self) -> str:
        return self._values["base_url"]

    @property
    def notes_dir(self) -> str:
        return self._values["notes_dir"]

    @property
    def key(self) -> str:
        """Clé effective : celle de l'environnement prime sur config.json."""
        for name in ENV_KEYS:
            value = os.environ.get(name, "").strip()
            if value:
                return value
        return self._values["api_key"]

    @property
    def key_from_env(self) -> str:
        for name in ENV_KEYS:
            if os.environ.get(name, "").strip():
                return name
        return ""

    @property
    def configured(self) -> bool:
        if self.spec["needs_key"] and not self.key:
            return False
        return bool(self._values["model"]) and bool(self.base_url)

    def public(self) -> dict[str, Any]:
        """Vue envoyée au navigateur : jamais la clé, seulement sa trace."""
        key = self.key
        env = self.key_from_env
        return {
            "provider": self.provider,
            "providerLabel": self.spec["label"],
            "model": self.model,
            "baseUrl": self.base_url,
            "urlEditable": bool(self.spec["editable_url"]),
            "needsKey": bool(self.spec["needs_key"]),
            "keyUrl": self.spec["key_url"],
            "hint": self.spec["hint"],
            "notesDir": self._values["notes_dir"],
            "keyConfigured": bool(key),
            "keyMasked": mask_key(key),
            "keyFromEnv": env,
            "configured": self.configured,
            "providers": [
                {
                    "id": name,
                    "label": spec["label"],
                    "needsKey": spec["needs_key"],
                    "defaultModel": spec.get("default_model") or "",
                    "keyUrl": spec["key_url"],
                    "hint": spec["hint"],
                }
                for name, spec in PROVIDERS.items()
            ],
        }

    # --- écriture ----------------------------------------------------------
    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Valide puis enregistre. Les champs absents conservent leur valeur."""
        with self._lock:
            provider = str(payload.get("provider") or self.provider).strip().casefold()
            if provider not in PROVIDERS:
                raise SettingsError("Ce fournisseur n’est pas reconnu.")
            spec = PROVIDERS[provider]

            model = str(payload.get("model", self.model)).strip()
            if not model:
                raise SettingsError("Indiquez le nom du modèle (celui de votre compte, ou installé sur votre PC).")
            if not MODEL_PATTERN.fullmatch(model):
                raise SettingsError("Le nom du modèle est invalide (lettres, chiffres, . _ / : - seulement).")

            base_url = self.base_url
            if spec["editable_url"]:
                raw_url = payload.get("baseUrl", base_url if provider == self.provider else spec["url"])
                base_url = check_base_url(str(raw_url))
            else:
                base_url = spec["url"]

            key = self._values["api_key"]
            if "apiKey" in payload:
                incoming = payload.get("apiKey")
                key = "" if incoming is None else check_api_key(str(incoming))
            if spec["needs_key"] and not key and not self.key_from_env:
                raise SettingsError("Ce fournisseur demande une clé API.")
            if provider != "anthropic" and key and key.startswith("sk-ant-"):
                # Petite garde : une clé Anthropic ne fonctionne pas ailleurs.
                raise SettingsError("Cette clé ressemble à une clé Anthropic : choisissez le fournisseur Anthropic.")

            notes_dir = self._values["notes_dir"]
            if "notesDir" in payload:
                candidate = str(payload.get("notesDir") or "").strip()
                notes_dir = self._check_notes_dir(candidate)

            values = {
                "provider": provider,
                "model": model,
                "api_key": key,
                "base_url": base_url,
                "notes_dir": notes_dir,
            }
            self._write(values)
            self._values = values
            return values

    @staticmethod
    def _check_notes_dir(value: str) -> str:
        from build import ROOT, resolve_notes_dir  # import tardif : évite un cycle

        if not value:
            return ""
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = ROOT / path
        path = path.resolve()
        if not path.is_dir():
            raise SettingsError(f"Dossier introuvable : {path}")
        return value

    def _write(self, values: dict[str, Any]) -> None:
        """Écrit config.json de façon atomique, avec des droits propriétaire seulement."""
        data = dict(self._raw)
        data["provider"] = values["provider"]
        data["model"] = values["model"]
        data["base_url"] = values["base_url"]
        if values["api_key"]:
            data["api_key"] = values["api_key"]
        else:
            data.pop("api_key", None)
        if values["notes_dir"]:
            data["notes_dir"] = values["notes_dir"]
        else:
            data.pop("notes_dir", None)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(self.path.parent), prefix=".config-", suffix=".json", delete=False
        )
        try:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        os.chmod(handle.name, 0o600)
        os.replace(handle.name, self.path)
        self._raw = data


def _http_error_message(code: int, provider: str) -> str:
    common = {
        400: "requête refusée (modèle inconnu ?)",
        401: "clé refusée",
        402: "crédit épuisé sur ce compte",
        403: "accès interdit à ce modèle",
        404: "adresse ou modèle introuvable",
        413: "question trop longue",
        429: "trop de requêtes, réessayez dans un instant",
        500: "le service a renvoyé une erreur interne",
        503: "le service est momentanément indisponible",
    }
    detail = common.get(code, "réponse inattendue du service")
    return f"{provider} : {detail} (HTTP {code})"


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], provider: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"content-type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Le corps d'erreur du fournisseur n'est jamais renvoyé au navigateur.
        raise RuntimeError(_http_error_message(exc.code, provider)) from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"{provider} injoignable ({type(exc).__name__})") from None
    except json.JSONDecodeError:
        raise RuntimeError(f"{provider} a renvoyé une réponse illisible") from None


def _extract(spec: dict[str, Any], data: dict[str, Any]) -> str:
    if spec["kind"] == "anthropic":
        texts = [part.get("text", "") for part in data.get("content", []) if part.get("type") == "text"]
        answer = "\n".join(text for text in texts if text).strip()
    else:
        choices = data.get("choices") or []
        message = (choices[0] or {}).get("message", {}) if choices else {}
        content = message.get("content")
        if isinstance(content, list):  # certains services renvoient des blocs
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        answer = str(content or "").strip()
    if not answer:
        raise RuntimeError("Le modèle n’a pas renvoyé de texte")
    return answer[:MAX_ANSWER_CHARS]


def ask(question: str, system: str, history: list[dict[str, str]], settings: AiSettings) -> str:
    """Envoie la question au fournisseur configuré et renvoie le texte de la réponse."""
    if not settings.key and settings.spec["needs_key"]:
        raise RuntimeError("Aucune clé API enregistrée")
    messages = list(history[-MAX_HISTORY_MESSAGES:])
    messages.append({"role": "user", "content": question})
    spec = settings.spec
    if spec["kind"] == "anthropic":
        payload = {"model": settings.model, "max_tokens": 420, "system": system, "messages": messages}
        headers = {"x-api-key": settings.key, "anthropic-version": "2023-06-01"}
    else:
        payload = {
            "model": settings.model,
            "max_tokens": 420,
            "temperature": 0.3,
            "messages": [{"role": "system", "content": system}, *messages],
        }
        headers = {"authorization": f"Bearer {settings.key}"} if settings.key else {}
    data = _post_json(settings.base_url, payload, headers, spec["label"])
    return _extract(spec, data)


def test_connection(settings: AiSettings) -> str:
    """Petit aller-retour réel pour valider clé, adresse et modèle."""
    system = "Tu es un test de connexion. Réponds exactement : OK."
    answer = ask("Réponds uniquement par OK.", system, [], settings)
    return answer[:80]
