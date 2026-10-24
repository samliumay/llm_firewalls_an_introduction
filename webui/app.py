"""Gradio application that serves the web UI for the firewall demonstration."""

import inspect
from typing import Any

import gradio as gr
import requests

from firewall import BasicSQLFirewall, QueryBlockedError
from llm_integrations import Ollama

from .chat_session import WebChat

# Reuse the endpoint the existing integration talks to.
OLLAMA_CHAT_URL = inspect.signature(Ollama.__init__).parameters["url"].default
OLLAMA_TAGS_URL = OLLAMA_CHAT_URL.rsplit("/api/", 1)[0] + "/api/tags"

EXAMPLES = [
    "List the five customers with the highest balance.",
    "Set every customer's total_amount to 0.",
]
VERDICT_TITLES = {
    "allowed": "✅ Firewall ALLOWED the SQL",
    "blocked": "🛑 Firewall BLOCKED the SQL",
    "not_inspected": "⚠️ SQL ran NOT INSPECTED",
}
UNPROTECTED_WARNING = (
    "> ⚠️ **Unprotected mode:** model-generated SQL runs without inspection "
    "and can modify the database."
)
HOW_A_TURN_WORKS = """
### How a turn works
1. Your prompt goes to Ollama with the database tool.
2. The model writes SQL and calls the tool.
3. In protected mode the firewall inspects the SQL first.
4. The result or the firewall error goes back to the model.
5. The model writes the final answer.

Each SQL statement appears in the chat as a collapsible firewall entry.
"""
CSS = "footer { display: none !important; }"


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


def _ollama_status(default_model: str) -> tuple[str, list[str]]:
    """Report whether Ollama is reachable and which models it has."""
    try:
        response = requests.get(OLLAMA_TAGS_URL, timeout=3)
        response.raise_for_status()
    except requests.RequestException as error:
        return f"🔴 Ollama unreachable: {_describe_error(error, default_model)}", []
    models = [m.get("name") for m in response.json().get("models", []) if m.get("name")]
    if default_model not in models:
        return f"🟡 Ollama connected; model `{default_model}` is not installed", models
    return "🟢 Ollama connected", models


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _rows_table(rows: list[dict[str, Any]]) -> str:
    columns = list(rows[0])
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    lines += [
        "| " + " | ".join(_markdown_cell(row.get(c)) for c in columns) + " |"
        for row in rows
    ]
    return "\n".join(lines)


def _format_event(event: dict[str, Any]) -> gr.ChatMessage:
    """Show one recorded query as a collapsible message in the chat."""
    parts = [f"```sql\n{event['sql'].strip()}\n```"]
    if event.get("reason"):
        parts.append(f"**Reason:** {event['reason']}")
    if event.get("database_error"):
        parts.append(f"**Database error:** {event['database_error']}")
    if "row_count" in event:
        rows = event.get("rows") or []
        label = f"{event['row_count']} row(s) returned"
        if len(rows) < event["row_count"]:
            label += f", showing first {len(rows)}"
        parts.append(label)
        if rows:
            parts.append(_rows_table(rows))
    if "affected_rows" in event:
        parts.append(f"{event['affected_rows']} row(s) affected")
    return gr.ChatMessage(
        role="assistant",
        content="\n\n".join(parts),
        metadata={"title": VERDICT_TITLES.get(event["verdict"], event["verdict"])},
    )


def create_app(default_model: str = "qwen3.6:35b") -> gr.Blocks:
    firewall = BasicSQLFirewall()

    def refresh_status(model: str):
        status, models = _ollama_status(default_model)
        choices = sorted(set(models) | {model or default_model})
        return status, gr.Dropdown(choices=choices)

    def respond(message: str, history: list, chat: WebChat | None, model: str, firewall_on: bool):
        message = message.strip()
        if not message:
            raise gr.Error("The message cannot be empty.")
        model = (model or default_model).strip()
        history = history + [gr.ChatMessage(role="user", content=message)]
        yield "", history, chat

        events: list[dict[str, Any]] = []
        try:
            if chat is None or chat.model != model or chat.control_status != firewall_on:
                # Raised by DatabaseManagement when POSTGRES_PASSWORD is missing.
                chat = WebChat(model=model, control_status=firewall_on)
            result = chat.ask(message)
            events = result["firewall_events"]
            answer = result["answer"]
        except Exception as error:  # noqa: BLE001 - reported in the chat
            events = getattr(error, "firewall_events", [])
            answer = f"**Error:** {_describe_error(error, model)}"
        history += [_format_event(event) for event in events]
        history.append(gr.ChatMessage(role="assistant", content=answer))
        yield "", history, chat

    def reset():
        return [], None

    def toggle_firewall(firewall_on: bool):
        label = "Firewall on (protected)" if firewall_on else "Firewall off (unprotected)"
        return gr.Checkbox(label=label), gr.Markdown(visible=not firewall_on), [], None

    def check_sql(query: str) -> str:
        """Run SQL through the firewall only. Nothing is sent to the database."""
        try:
            firewall.validate_query(query)
        except QueryBlockedError as error:
            return f"🛑 **BLOCKED:** {error}"
        return "✅ **ALLOWED:** The query passed inspection."

    with gr.Blocks(title="LLM Firewall Demo") as app:
        chat_state = gr.State(None)

        with gr.Row(equal_height=True):
            gr.Markdown("# 🛡️ LLM Firewall Demo")
            status = gr.Markdown("Checking Ollama...")
        with gr.Row(equal_height=True):
            model = gr.Dropdown(
                choices=[default_model],
                value=default_model,
                label="Model",
                allow_custom_value=True,
                scale=3,
            )
            firewall_on = gr.Checkbox(value=True, label="Firewall on (protected)", scale=2)
            reset_button = gr.Button("New conversation", variant="secondary", scale=1)
        banner = gr.Markdown(UNPROTECTED_WARNING, visible=False)

        with gr.Row():
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    label="Conversation",
                    height=520,
                    buttons=["copy"],
                    feedback_options=None,
                    placeholder="Ask the banking assistant about customers.",
                )
                prompt = gr.Textbox(
                    placeholder="Type a message and press Enter.",
                    show_label=False,
                    submit_btn="Send",
                )
                gr.Examples(EXAMPLES, inputs=prompt, label="Try")

            with gr.Column(scale=2):
                gr.Markdown(
                    "### Test SQL against the firewall\n"
                    "Runs only the firewall rules. Nothing is sent to the model or the database."
                )
                sql = gr.Code(
                    "DELETE FROM customers WHERE customer_id = 1;",
                    language="sql",
                    show_label=False,
                    interactive=True,
                )
                check_button = gr.Button("Check")
                sql_result = gr.Markdown()
                gr.Markdown(HOW_A_TURN_WORKS)

        app.load(refresh_status, inputs=model, outputs=[status, model])
        prompt.submit(
            respond,
            inputs=[prompt, chatbot, chat_state, model, firewall_on],
            outputs=[prompt, chatbot, chat_state],
        )
        reset_button.click(reset, outputs=[chatbot, chat_state])
        # A different model or mode starts a fresh conversation, as before.
        model.change(reset, outputs=[chatbot, chat_state])
        firewall_on.change(
            toggle_firewall,
            inputs=firewall_on,
            outputs=[firewall_on, banner, chatbot, chat_state],
        )
        check_button.click(check_sql, inputs=sql, outputs=sql_result)

    return app


def launch_options() -> dict[str, Any]:
    """Theme and styling, which Gradio 6 takes in launch()."""
    return {"theme": gr.themes.Soft(), "css": CSS}
