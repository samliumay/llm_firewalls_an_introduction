"""Launch the browser UI for the LLM firewall demonstration."""

import argparse
import os

from webui import create_app, launch_options

# Local only. The unprotected mode can modify the database. The Hugging Face
# Space overrides this inside its isolated container.
HOST = os.environ.get("GRADIO_SERVER_NAME", "127.0.0.1")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the LLM firewall web UI.")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000).")
    parser.add_argument(
        "--model",
        default="qwen3.6:35b",
        help="Default Ollama model shown in the UI (default: qwen3.6:35b).",
    )
    arguments = parser.parse_args()

    app = create_app(default_model=arguments.model)
    app.queue(default_concurrency_limit=1).launch(
        server_name=HOST,
        server_port=arguments.port,
        **launch_options(),
    )


if __name__ == "__main__":
    main()
