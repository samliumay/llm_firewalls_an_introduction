"""Flask application that serves the web UI and a small JSON API."""

import inspect
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

import requests
from flask import Flask, jsonify, request, send_from_directory

from firewall import BasicSQLFirewall, QueryBlockedError
from llm_integrations import Ollama

from .chat_session import WebChat

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_SESSIONS = 50
# Reuse the endpoint the existing integration talks to.
OLLAMA_CHAT_URL = inspect.signature(Ollama.__init__).parameters["url"].default
OLLAMA_TAGS_URL = OLLAMA_CHAT_URL.rsplit("/api/", 1)[0] + "/api/tags"


def _describe_error(error: Exception, model: str) -> str:
    """Turn common failures into messages a user can act on."""
    if isinstance(error, requests.ConnectionError):
        return (
            f"Could not reach Ollama at {OLLAMA_CHAT_URL}. "
            "Start it with 'ollama serve'."
        )
    if isinstance(error, requests.Timeout):
        return "Ollama did not answer in time. Try again or use a smaller model."
    if isinstance(error, requests.HTTPError):
        response = error.response
        detail = ""
        if response is not None:
            try:
                detail = response.json().get("error", "")
            except ValueError:
                detail = response.text[:200]
            if response.status_code == 404:
                return (
                    f"Ollama does not have the model '{model}'. "
                    f"Pull it with 'ollama pull {model}'. {detail}".strip()
                )
        return f"Ollama returned an error: {detail or error}"
    return str(error) or error.__class__.__name__


def create_app(default_model: str = "qwen3.6:35b") -> Flask:
    app = Flask(__name__, static_folder=None)
    sessions: "OrderedDict[str, WebChat]" = OrderedDict()
    sessions_lock = threading.Lock()
    firewall = BasicSQLFirewall()

    def get_session(session_id: str, model: str, firewall_on: bool) -> WebChat:
        """Return the chat for this browser tab, recreating it if settings changed."""
        with sessions_lock:
            chat = sessions.get(session_id)
            if (
                chat is None
                or chat.model != model
                or chat.control_status != firewall_on
            ):
                chat = WebChat(model=model, control_status=firewall_on)
                sessions[session_id] = chat
            sessions.move_to_end(session_id)
            while len(sessions) > MAX_SESSIONS:
                sessions.popitem(last=False)
            return chat

    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/static/<path:filename>")
    def static_files(filename: str):
        return send_from_directory(STATIC_DIR, filename)

    @app.get("/api/status")
    def status():
        """Report whether Ollama is reachable and which models it has."""
        info: dict[str, Any] = {"default_model": default_model, "ollama_url": OLLAMA_CHAT_URL}
        try:
            response = requests.get(OLLAMA_TAGS_URL, timeout=3)
            response.raise_for_status()
            models = response.json().get("models", [])
            info["ollama"] = "ok"
            info["models"] = [
                {"name": m.get("name"), "tools": "tools" in (m.get("capabilities") or ["tools"])}
                for m in models
            ]
        except requests.RequestException as error:
            info["ollama"] = "unreachable"
            info["ollama_error"] = _describe_error(error, default_model)
            info["models"] = []
        return jsonify(info)

    @app.post("/api/chat")
    def chat():
        body = request.get_json(silent=True) or {}
        message = str(body.get("message", "")).strip()
        session_id = str(body.get("session_id", "")).strip()
        model = str(body.get("model") or default_model).strip()
        firewall_on = body.get("firewall", True) is not False

        if not message:
            return jsonify({"error": "The message cannot be empty."}), 400
        if not session_id:
            return jsonify({"error": "Missing session_id."}), 400

        try:
            session = get_session(session_id, model, firewall_on)
        except ValueError as error:
            # Raised by DatabaseManagement when POSTGRES_PASSWORD is missing.
            return jsonify({"error": str(error), "firewall_events": []}), 500

        with session.lock:
            try:
                result = session.ask(message)
            except Exception as error:  # noqa: BLE001 - reported to the browser
                return jsonify(
                    {
                        "error": _describe_error(error, model),
                        "firewall_events": getattr(error, "firewall_events", []),
                    }
                ), 502
        result["model"] = model
        result["firewall"] = firewall_on
        return jsonify(result)

    @app.post("/api/reset")
    def reset():
        body = request.get_json(silent=True) or {}
        with sessions_lock:
            sessions.pop(str(body.get("session_id", "")), None)
        return jsonify({"ok": True})

    @app.post("/api/firewall/check")
    def check_sql():
        """Run SQL through the firewall only. Nothing is sent to the database."""
        body = request.get_json(silent=True) or {}
        query = str(body.get("query", ""))
        try:
            firewall.validate_query(query)
        except QueryBlockedError as error:
            return jsonify({"verdict": "blocked", "reason": str(error)})
        return jsonify({"verdict": "allowed", "reason": "The query passed inspection."})

    return app
