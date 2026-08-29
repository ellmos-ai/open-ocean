"""Provider-specific user bootstrap without putting passwords in process arguments."""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ocean-runtime-user")
    parser.add_argument("--runtime-id", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", required=True, choices=["admin", "user"])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    password = sys.stdin.readline().rstrip("\r\n")
    if not password:
        print("Kein Passwort über den geschützten Eingabekanal empfangen.", file=sys.stderr)
        return 2
    if args.runtime_id != "ellmos-core":
        print(f"Kein Benutzeradapter für Runtime {args.runtime_id!r} registriert.", file=sys.stderr)
        return 3

    from ellmos_core.cli import cmd_init_user

    args.password = password
    cmd_init_user(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
