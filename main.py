"""CLI entrypoint for the Mietrecht agent.

Usage:
    uv run python main.py setup-db
    uv run python main.py ingest-statutes [--force]
    uv run python main.py ingest-case-law [--dump-path PATH] [--max-decisions N] [--force]
    uv run python main.py ask -q "Wie hoch darf meine Kaution sein?" [--user NAME] [--role mieter]
    uv run python main.py chat --thread t1 [--user NAME] [--role mieter]
    uv run python main.py create-user --username NAME [--display-name NAME] [--role user|admin]
    uv run python main.py eval
    uv run python main.py serve [--host H] [--port P] [--reload]

The `ask`/`chat` subcommands take `--user` directly: the CLI is a trusted local tool
with direct graph/DB access and deliberately bypasses the API's JWT auth.
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid

from dotenv import load_dotenv

from src import config
from src.agent.prompts import ROLE_LABELS

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

_ROLE_CHOICES = list(ROLE_LABELS.keys())


def cmd_setup_db(args: argparse.Namespace) -> None:
    """Run the setup-db subcommand: idempotent Postgres schema setup."""
    from src.db import setup_db

    setup_db()
    print("Database setup complete.")


def cmd_ingest_statutes(args: argparse.Namespace) -> None:
    """Run the ingest-statutes subcommand: chunk and embed the statute corpus."""
    from src.ingest.statutes import ingest_statutes

    count = ingest_statutes(force=args.force)
    if count:
        print(f"Ingested {count} statute chunks.")
    else:
        print("Statutes already ingested (use --force to re-ingest).")


def cmd_ingest_case_law(args: argparse.Namespace) -> None:
    """Run the ingest-case-law subcommand: filter, chunk and embed court decisions."""
    from src.ingest.case_law import ingest_case_law

    report = ingest_case_law(
        dump_path=args.dump_path,
        max_decisions=args.max_decisions,
        force=args.force,
    )
    if "total" in report:
        print(
            f"Filter: {report['total']} decisions read, {report['regex_matches']} regex "
            f"matches, {report['keyword_matches']} keyword matches, {report['relevant']} "
            f"relevant, {report['kept']} kept."
        )
    if report["chunks_written"]:
        print(f"Ingested {report['chunks_written']} case-law chunks.")
    else:
        print("Case law already ingested (use --force to re-ingest).")


def cmd_ask(args: argparse.Namespace) -> None:
    """Run the ask subcommand: a single turn through the agent on an ephemeral thread."""
    from src.agent.graph import run

    thread_id = f"ask-{uuid.uuid4()}"
    answer = run(args.question, thread_id=thread_id, user_name=args.user, role=args.role)
    print("\nAntwort:\n")
    print(answer)


def cmd_chat(args: argparse.Namespace) -> None:
    """Run the chat subcommand: a multi-turn REPL backed by the checkpointer."""
    from src.agent.graph import run

    print(f"Chat-Sitzung '{args.thread}' (Rolle: {ROLE_LABELS[args.role]}). 'exit' zum Beenden.\n")
    while True:
        try:
            user_input = input("Sie: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break
        answer = run(user_input, thread_id=args.thread, user_name=args.user, role=args.role)
        print(f"\nAssistent:\n{answer}\n")


def cmd_create_user(args: argparse.Namespace) -> None:
    """Run the create-user subcommand: bootstrap an account without the admin UI."""
    import getpass

    from src.auth import create_user

    password = getpass.getpass("Passwort: ")
    if password != getpass.getpass("Passwort (wiederholen): "):
        print("Passwörter stimmen nicht überein.")
        sys.exit(1)
    try:
        user = create_user(args.username, args.display_name or args.username, password, role=args.role)
    except ValueError as exc:
        print(f"Fehler: {exc}")
        sys.exit(1)
    print(f"Benutzer '{user['username']}' ({user['role']}) angelegt.")


def cmd_eval(args: argparse.Namespace) -> None:
    """Run the eval subcommand: the consolidated RAGAs evaluation."""
    from src.eval.runner import run_eval

    run_eval()


def cmd_serve(args: argparse.Namespace) -> None:
    """Run the serve subcommand: the FastAPI backend for the React frontend."""
    import uvicorn

    uvicorn.run(
        "src.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate subcommand."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Mietrecht Agent – CLI entrypoint",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("setup-db", help="Idempotent Postgres schema setup.")

    ingest_statutes_parser = subparsers.add_parser(
        "ingest-statutes", help="Chunk and embed the statute corpus into the 'statutes' collection."
    )
    ingest_statutes_parser.add_argument(
        "--force", action="store_true", help="Clear and re-ingest even if already populated."
    )

    ingest_case_law_parser = subparsers.add_parser(
        "ingest-case-law", help="Filter, chunk and embed court decisions into the 'case_law' collection."
    )
    ingest_case_law_parser.add_argument(
        "--dump-path",
        default=config.CASE_LAW_DUMP_PATH,
        help="Local directory containing the court-decisions parquet shards.",
    )
    ingest_case_law_parser.add_argument(
        "--max-decisions",
        type=int,
        default=config.MAX_DECISIONS,
        help=(
            "Cap on keyword-only-match decisions (no direct statute citation, "
            "lower precision). Decisions citing a Mietrecht statute directly "
            "are always ingested in full regardless of this value."
        ),
    )
    ingest_case_law_parser.add_argument(
        "--force", action="store_true", help="Clear and re-ingest even if already populated."
    )

    ask_parser = subparsers.add_parser("ask", help="Ask the agent a single question (ephemeral thread).")
    ask_parser.add_argument(
        "-q", "--question", required=True, help="Question to ask (in German)."
    )
    ask_parser.add_argument("--user", default="anon", help="First name used as the memory namespace key.")
    ask_parser.add_argument("--role", default="mieter", choices=_ROLE_CHOICES, help="User role.")

    chat_parser = subparsers.add_parser("chat", help="Start a multi-turn chat session with the agent.")
    chat_parser.add_argument("--thread", required=True, help="Conversation thread id (persisted).")
    chat_parser.add_argument("--user", default="anon", help="First name used as the memory namespace key.")
    chat_parser.add_argument("--role", default="mieter", choices=_ROLE_CHOICES, help="User role.")

    subparsers.add_parser("eval", help="Run the consolidated RAGAs evaluation.")

    create_user_parser = subparsers.add_parser(
        "create-user", help="Create an account (prompts for the password)."
    )
    create_user_parser.add_argument("--username", required=True, help="Login name (lowercased).")
    create_user_parser.add_argument("--display-name", default="", help="Shown name (defaults to username).")
    create_user_parser.add_argument("--role", default="user", choices=["user", "admin"], help="Auth role.")

    serve_parser = subparsers.add_parser("serve", help="Run the FastAPI backend (React frontend API).")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Bind host.")
    serve_parser.add_argument("--port", type=int, default=8000, help="Bind port.")
    serve_parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes (dev).")

    args = parser.parse_args()
    if args.command == "setup-db":
        cmd_setup_db(args)
    elif args.command == "ingest-statutes":
        cmd_ingest_statutes(args)
    elif args.command == "ingest-case-law":
        cmd_ingest_case_law(args)
    elif args.command == "ask":
        cmd_ask(args)
    elif args.command == "chat":
        cmd_chat(args)
    elif args.command == "eval":
        cmd_eval(args)
    elif args.command == "create-user":
        cmd_create_user(args)
    elif args.command == "serve":
        cmd_serve(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
