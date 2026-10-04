"""Launch the browser UI for the LLM firewall demonstration."""

import argparse

from webui import create_app

HOST = "127.0.0.1"  # Local only. The unprotected mode can modify the database.


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
    print(f"Open http://{HOST}:{arguments.port} in your browser.")
    app.run(host=HOST, port=arguments.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
