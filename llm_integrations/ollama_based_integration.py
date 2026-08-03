"""Ollama chat integration with database tool calling."""

import json
from typing import Any

import requests

from .database_layer import DatabaseManagement


DATABASE_TOOL = {
    "type": "function",
    "function": {
        "name": "execute_database_query",
        "description": (
            "Execute a PostgreSQL query against the demonstration bank database. "
            "The customers table has these columns: customer_id, first_name, "
            "last_name, email, phone_number, date_of_birth, national_id, "
            "street_address, city, postal_code, country_code, total_amount, "
            "currency_code, created_at, and updated_at."
        ),
        "parameters": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The complete PostgreSQL query to execute.",
                }
            },
        },
    },
}


class Ollama:
    """Manage a conversation with Ollama and execute requested database tools."""

    def __init__(
        self,
        model: str = "qwen3",
        control_status: bool = True,
        url: str = "http://localhost:11434/api/chat",
        timeout: float = 120,
        max_tool_rounds: int = 10,
    ) -> None:
        self.model = model
        self.control_status = control_status
        self.url = url
        self.timeout = timeout
        self.max_tool_rounds = max_tool_rounds
        self.database = DatabaseManagement()
        self.messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a banking assistant. Use execute_database_query "
                    "when customer or financial data is required. Never invent "
                    "database results."
                ),
            }
        ]

    def send_message(self, user_message: str) -> str:
        """Send one user message and resolve all requested tool calls."""
        if not user_message.strip():
            raise ValueError("The user message cannot be empty.")

        self.messages.append({"role": "user", "content": user_message})

        for _ in range(self.max_tool_rounds):
            assistant_message = self._request_chat_completion()
            self.messages.append(assistant_message)
            tool_calls = assistant_message.get("tool_calls") or []

            if not tool_calls:
                return str(assistant_message.get("content", ""))

            for tool_call in tool_calls:
                tool_name, tool_result = self._execute_tool_call(tool_call)
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_name": tool_name,
                        "content": json.dumps(tool_result, default=str),
                    }
                )

        raise RuntimeError(
            f"Ollama exceeded the limit of {self.max_tool_rounds} tool rounds."
        )

    def chat_loop(self) -> None:
        """Run an interactive terminal conversation until the user exits."""
        print("Type 'exit' or 'quit' to end the conversation.")

        while True:
            user_message = input("You: ").strip()

            if user_message.lower() in {"exit", "quit"}:
                return

            if not user_message:
                continue

            try:
                answer = self.send_message(user_message)
            except (requests.RequestException, RuntimeError, ValueError) as error:
                print(f"Error: {error}")
                continue

            print(f"Ollama: {answer}")

    def _request_chat_completion(self) -> dict[str, Any]:
        response = requests.post(
            self.url,
            json={
                "model": self.model,
                "messages": self.messages,
                "tools": [DATABASE_TOOL],
                "stream": False,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

        response_body = response.json()
        assistant_message = response_body.get("message")

        if not isinstance(assistant_message, dict):
            raise RuntimeError("Ollama returned a response without a message.")

        return assistant_message

    def _execute_tool_call(
        self,
        tool_call: dict[str, Any],
    ) -> tuple[str, Any]:
        function = tool_call.get("function") or {}
        tool_name = str(function.get("name", "unknown"))
        arguments = function.get("arguments") or {}

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return tool_name, {"error": "The tool arguments are not valid JSON."}

        if tool_name != "execute_database_query":
            return tool_name, {"error": f"Unknown tool: {tool_name}"}

        if not isinstance(arguments, dict):
            return tool_name, {"error": "The tool arguments must be an object."}

        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            return tool_name, {"error": "The query argument must be a SQL string."}

        try:
            result = self.database.execute_query(
                query=query,
                control_status=self.control_status,
            )
        except Exception as error:
            return tool_name, {"error": str(error)}

        return tool_name, {"result": result}
