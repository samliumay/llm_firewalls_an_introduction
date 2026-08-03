"""Command-line entry point for the LLM firewall demonstration."""

import argparse

from llm_integrations import Ollama


def parse_arguments() -> argparse.Namespace:
    """Read command-line configuration for the demonstration."""
    parser = argparse.ArgumentParser(
        description="Run the LLM firewall proof-of-concept banking assistant."
    )
    parser.add_argument(
        "--model",
        default="qwen3.6",
        help="Name of the local Ollama model to use (default: qwen3).",
    )
    parser.add_argument(
        "--disable-firewall",
        action="store_true",
        help="Execute model-generated SQL without firewall inspection.",
    )
    return parser.parse_args()


def main() -> None:
    """Configure and start the interactive Ollama conversation."""
    arguments = parse_arguments()
    firewall_enabled = not arguments.disable_firewall
    mode = "protected" if firewall_enabled else "unprotected"

    print(f"Starting the banking assistant in {mode} mode.")
    print(f"Model: {arguments.model}")

    if not firewall_enabled:
        print("WARNING: Model-generated SQL can modify the database.")

    chat = Ollama(
        model=arguments.model,
        control_status=firewall_enabled,
    )

    try:
        chat.chat_loop()
    except KeyboardInterrupt:
        print("\nConversation ended.")


if __name__ == "__main__":
    main()
