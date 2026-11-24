"""Terminal entry point. Calls the same core code the API and UI will use."""

import argparse

from rulestorm.education import EXAMPLE_POLICY
from rulestorm.policy import PolicyInput
from rulestorm.store import Store


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="rulestorm")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("hello", help="print hello")

    policy = commands.add_parser("policy", help="policy input")
    policy_commands = policy.add_subparsers(dest="policy_command", required=True)
    policy_commands.add_parser("example", help="save the pre-filled 80%% example and print it")

    args = parser.parse_args(argv)
    if args.command == "hello":
        print("hello")
    elif args.command == "policy" and args.policy_command == "example":
        saved = Store().save_policy(PolicyInput(**EXAMPLE_POLICY))
        print(saved.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
