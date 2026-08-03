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
        model: str = "qwen3.6",
        control_status: bool = True,
        url: str = "http://127.0.0.1:11434/api/chat",
        timeout: float = 120,
        max_tool_rounds: int = 10,
    ) -> None:
        """Configure Ollama, database access, and conversation state.

        Args:
            model: Name of a locally installed, tool-capable Ollama model.
            control_status: Whether database queries pass through the firewall.
            url: Ollama chat API endpoint.
            timeout: Maximum seconds to wait for one Ollama HTTP response.
            max_tool_rounds: Maximum tool-call cycles for one user message.
        """
        self.model = model
        self.control_status = control_status
        self.url = url
        self.timeout = timeout
        self.max_tool_rounds = max_tool_rounds
        self.database = DatabaseManagement()
        # Messages are retained so Ollama receives the complete conversation
        # and can answer follow-up questions using earlier context.
        self.messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a banking assistant. Use execute_database_query "
                    "when database access is needed."
                ),
            }
        ]

    def send_message(self, user_message: str) -> str:
        """Send one user message and resolve its tool-call chain.

        The method repeatedly calls Ollama while tools are requested. It returns
        only when Ollama produces a normal assistant message without tool calls.

        Args:
            user_message: Text entered by the person using the application.

        Returns:
            Ollama's final natural-language answer.

        Raises:
            ValueError: If the user message is empty.
            RuntimeError: If Ollama exceeds the tool-call round limit.
        """
        if not user_message.strip():
            raise ValueError("The user message cannot be empty.")

        self.messages.append({"role": "user", "content": user_message})

        # One user message may require several database calls before Ollama has
        # enough information to produce its final answer.
        for _ in range(self.max_tool_rounds):
            assistant_message = self._request_chat_completion()
            # Ollama must receive its own tool request again in the next API call.
            self.messages.append(assistant_message)
            tool_calls = assistant_message.get("tool_calls") or []

            # No tool call means the assistant message is the final user answer.
            if not tool_calls:
                return str(assistant_message.get("content", ""))

            # Models can request multiple tools in a single response.
            for tool_call in tool_calls:
                tool_name, tool_result = self._execute_tool_call(tool_call)
                # A tool message connects the local result to the function name
                # Ollama requested. It becomes input to the next model call.
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
        """Read terminal input and print replies until the user exits.

        This is the outer conversation loop. send_message contains the separate
        inner loop responsible for resolving tool calls.
        """
        print("Type 'exit' or 'quit' to end the conversation.")

        while True:
            user_message = input("You: ").strip()

            if user_message.lower() in {"exit", "quit"}:
                return

            if not user_message:
                continue

            # A failed turn is reported without ending the complete conversation.
            try:
                answer = self.send_message(user_message)
            except (requests.RequestException, RuntimeError, ValueError) as error:
                print(f"Error: {error}")
                continue

            print(f"Ollama: {answer}")

    def _request_chat_completion(self) -> dict[str, Any]:
        """Send the current history and database tool schema to Ollama."""
        # stream=False returns one JSON document, which makes tool-call handling
        # simpler than accumulating streamed response chunks.
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
        # Convert HTTP errors such as 404 or 500 into Python exceptions.
        response.raise_for_status()

        response_body = response.json()
        assistant_message = response_body.get("message")

        # Fail clearly if the server response does not follow the chat format.
        if not isinstance(assistant_message, dict):
            raise RuntimeError("Ollama returned a response without a message.")

        return assistant_message

    def _execute_tool_call(
        self,
        tool_call: dict[str, Any],
    ) -> tuple[str, Any]:
        """Validate and execute one tool call requested by Ollama.

        Returns:
            A pair containing the requested tool name and either its result or
            an error object that can be sent back to Ollama.
        """
        function = tool_call.get("function") or {}
        tool_name = str(function.get("name", "unknown"))
        arguments = function.get("arguments") or {}

        # Current Ollama responses normally use an object, but parsing a JSON
        # string as a fallback makes the integration tolerant of model variants.
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return tool_name, {"error": "The tool arguments are not valid JSON."}

        # Never dispatch arbitrary function names supplied by the model.
        if tool_name != "execute_database_query":
            return tool_name, {"error": f"Unknown tool: {tool_name}"}

        if not isinstance(arguments, dict):
            return tool_name, {"error": "The tool arguments must be an object."}

        # The database tool requires exactly one meaningful SQL string.
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            return tool_name, {"error": "The query argument must be a SQL string."}

        # control_status belongs to the application and is never accepted from
        # model-generated tool arguments.
        try:
            result = self.database.execute_query(
                query=query,
                control_status=self.control_status,
            )
        except Exception as error:
            # Returning the error as a tool result lets Ollama explain a firewall
            # rejection or database failure to the user.
            return tool_name, {"error": str(error)}

        return tool_name, {"result": result}
