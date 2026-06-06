"""Interactive CLI: a portable chat over Databricks-hosted models."""

import argparse

from dotenv import load_dotenv

from dbx_llm.client import chat, list_models
from dbx_llm.prompts import list_prompts, load_prompt


def main() -> None:
    load_dotenv(override=True)

    parser = argparse.ArgumentParser(
        prog="dbx-llm",
        description="Chat with Databricks-hosted models from your terminal.",
    )
    parser.add_argument("--model", help="Serving endpoint name to use.")
    parser.add_argument("--prompt", default="default", help="Prompt file in prompts/.")
    parser.add_argument("--list-models", action="store_true", help="List models and exit.")
    parser.add_argument("--list-prompts", action="store_true", help="List prompts and exit.")
    args = parser.parse_args()

    if args.list_models:
        print("\n".join(list_models()))
        return
    if args.list_prompts:
        print("\n".join(list_prompts()))
        return

    models = list_models()
    if not models:
        print("No serving endpoints found. Run 'databricks auth login' first.")
        return

    model = args.model or models[0]
    system = load_prompt(args.prompt)
    history: list[dict] = [{"role": "system", "content": system}]

    print(f"Model:  {model}")
    print(f"Prompt: {args.prompt}")
    print("Type your message. Ctrl-C to exit.\n")

    while True:
        try:
            user = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        history.append({"role": "user", "content": user})
        reply = chat(model, history)
        history.append({"role": "assistant", "content": reply})
        print(f"\n{reply}\n")


if __name__ == "__main__":
    main()
