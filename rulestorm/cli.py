"""Terminal entry point. Calls the same core code the API and UI will use."""

import argparse

from rulestorm.education import EXAMPLE_POLICY
from rulestorm.policy import (
    BlueprintInvalid,
    BlueprintNotFound,
    PolicyInput,
    PolicyNotFound,
    approve_blueprint,
    create_blueprint,
)
from rulestorm.store import Store


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="rulestorm")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("hello", help="print hello")

    policy = commands.add_parser("policy", help="policy input")
    policy_commands = policy.add_subparsers(dest="policy_command", required=True)
    policy_commands.add_parser("example", help="save the pre-filled 80%% example and print it")

    blueprint = commands.add_parser("blueprint", help="AI blueprint of a stored policy")
    blueprint_commands = blueprint.add_subparsers(dest="blueprint_command", required=True)
    create_cmd = blueprint_commands.add_parser("create", help="interpret a policy through Bedrock")
    create_cmd.add_argument("--policy", required=True, help="policy ID from `policy example`")
    approve_cmd = blueprint_commands.add_parser("approve", help="approve and freeze a valid blueprint")
    approve_cmd.add_argument("blueprint_id")

    llm = commands.add_parser("llm", help="model adapter")
    llm_commands = llm.add_subparsers(dest="llm_command", required=True)
    smoke_cmd = llm_commands.add_parser("smoke", help="real Bedrock call: auth, latency, tokens, quotas")
    smoke_cmd.add_argument("--model", help="Bedrock model ID (default: the configured model)")

    args = parser.parse_args(argv)
    if args.command == "hello":
        print("hello")
    elif args.command == "policy" and args.policy_command == "example":
        saved = Store().save_policy(PolicyInput(**EXAMPLE_POLICY))
        print(saved.model_dump_json(indent=2))
    elif args.command == "blueprint" and args.blueprint_command == "create":
        try:
            record = create_blueprint(Store(), args.policy)
        except PolicyNotFound:
            raise SystemExit(f"policy not found: {args.policy}")
        print(record.model_dump_json(indent=2))
    elif args.command == "blueprint" and args.blueprint_command == "approve":
        try:
            record = approve_blueprint(Store(), args.blueprint_id)
        except BlueprintNotFound:
            raise SystemExit(f"blueprint not found: {args.blueprint_id}")
        except BlueprintInvalid:
            raise SystemExit(f"blueprint not valid, so it cannot be approved: {args.blueprint_id}")
        print(f"id: {record.id}")
        print(f"status: {record.status}")
        print(f"approved: {str(record.approved).lower()}")
    elif args.command == "llm" and args.llm_command == "smoke":
        from rulestorm import smoke

        for line in smoke.run(args.model):
            print(line)


if __name__ == "__main__":
    main()
