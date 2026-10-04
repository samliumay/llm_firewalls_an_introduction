"""Thin wrappers that record firewall activity for the web UI.

Nothing here reimplements the firewall or the Ollama tool loop. The classes
subclass the existing ones and only observe what happens, so the browser can
show which SQL the model generated, whether the firewall allowed it, and what
the database returned.
"""

import json
import threading
from typing import Any

from firewall import QueryBlockedError
from llm_integrations import DatabaseManagement, Ollama

MAX_PREVIEW_ROWS = 20


def _json_safe(value: Any) -> Any:
    """Convert dates, decimals and similar values into JSON-friendly types."""
    return json.loads(json.dumps(value, default=str))


class RecordingDatabase(DatabaseManagement):
    """DatabaseManagement that remembers every query routed through it."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict[str, Any]] = []

    def execute_query(self, query, parameters=None, control_status=False):
        event: dict[str, Any] = {
            "sql": query,
            "firewall_enabled": control_status,
        }
        passed = "allowed" if control_status else "not_inspected"
        try:
            result = super().execute_query(query, parameters, control_status)
        except QueryBlockedError as error:
            event.update(verdict="blocked", reason=str(error))
            self.events.append(event)
            raise
        except Exception as error:
            # The firewall (if enabled) let the query through, but the database
            # itself failed, e.g. PostgreSQL is not running.
            event.update(verdict=passed, database_error=str(error))
            self.events.append(event)
            raise

        event["verdict"] = passed
        if isinstance(result, list):
            event["row_count"] = len(result)
            event["rows"] = _json_safe(result[:MAX_PREVIEW_ROWS])
        else:
            event["affected_rows"] = result
        self.events.append(event)
        return result


class WebChat(Ollama):
    """One browser conversation, backed by the existing Ollama integration."""

    def __init__(self, model: str, control_status: bool) -> None:
        super().__init__(model=model, control_status=control_status)
        self.database = RecordingDatabase()
        self.lock = threading.Lock()

    def ask(self, user_message: str) -> dict[str, Any]:
        """Send one message and return the answer plus the firewall trace.

        Exceptions propagate to the caller. The trace collected before the
        failure is attached to the exception as ``firewall_events`` and the
        failed turn is removed from history so the conversation stays usable.
        """
        self.database.events = []
        history_length = len(self.messages)
        try:
            answer = self.send_message(user_message)
        except Exception as error:
            del self.messages[history_length:]
            error.firewall_events = list(self.database.events)  # type: ignore[attr-defined]
            raise
        return {"answer": answer, "firewall_events": list(self.database.events)}
