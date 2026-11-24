"""Terminal entry point. Calls the same core code the API and UI will use."""

import argparse
import json
from pathlib import Path

from rulestorm.education import EXAMPLE_POLICY
from rulestorm.policy import (
    BlueprintInvalid,
    BlueprintNotFound,
    DailyCapReached,
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
    save_cmd = policy_commands.add_parser("save", help="save your own policy texts and print them")
    save_cmd.add_argument("--text", required=True, help="the policy rule (max 2,000 characters)")
    save_cmd.add_argument("--purpose", required=True, help="why it exists (max 2,000 characters)")
    save_cmd.add_argument("--environment", required=True, help="where it applies (max 2,000 characters)")

    blueprint = commands.add_parser("blueprint", help="AI blueprint of a stored policy")
    blueprint_commands = blueprint.add_subparsers(dest="blueprint_command", required=True)
    create_cmd = blueprint_commands.add_parser("create", help="interpret a policy through Bedrock")
    create_cmd.add_argument("--policy", required=True, help="policy ID from `policy example`")
    approve_cmd = blueprint_commands.add_parser("approve", help="approve and freeze a valid blueprint")
    approve_cmd.add_argument("blueprint_id")

    template = commands.add_parser("template", help="rule-world templates (data)")
    template_commands = template.add_subparsers(dest="template_command", required=True)
    template_check_cmd = template_commands.add_parser("check", help="check a template the engine can trust")
    template_check_cmd.add_argument("template", help="a shipped template name (attendance) or a JSON file path")

    engine = commands.add_parser("engine", help="deterministic rule engine")
    engine_commands = engine.add_subparsers(dest="engine_command", required=True)
    check_cmd = engine_commands.add_parser("check", help="play a fixed test case through the engine")
    check_cmd.add_argument("--case", required=True, help="case JSON file, e.g. tests/cases/student_c.json")
    check_cmd.add_argument("--core", action="store_true", help="use the general engine and the case's template")

    llm = commands.add_parser("llm", help="model adapter")
    llm_commands = llm.add_subparsers(dest="llm_command", required=True)
    smoke_cmd = llm_commands.add_parser("smoke", help="real Bedrock call: auth, latency, tokens, quotas")
    smoke_cmd.add_argument("--model", help="Bedrock model ID (default: the configured model)")

    run = commands.add_parser("run", help="simulated terms")
    run_commands = run.add_subparsers(dest="run_command", required=True)
    local_cmd = run_commands.add_parser("local", help="run one real term here, with Bedrock agents")
    local_cmd.add_argument("--blueprint", required=True, help="an approved blueprint ID")

    explore = commands.add_parser("explore", help="stress variants of an approved blueprint (slice 6c)")
    explore_commands = explore.add_subparsers(dest="explore_command", required=True)
    propose_cmd = explore_commands.add_parser("propose", help="ask Bedrock for up to 3 harsher scenarios")
    propose_cmd.add_argument("blueprint_id", help="an approved blueprint ID")
    explore_run_cmd = explore_commands.add_parser("run", help="run every approved variant, one real term each")
    explore_run_cmd.add_argument("blueprint_id", help="the approved blueprint the variants vary")

    args = parser.parse_args(argv)
    if args.command == "hello":
        print("hello")
    elif args.command == "policy" and args.policy_command == "example":
        saved = Store().save_policy(PolicyInput(**EXAMPLE_POLICY))
        print(saved.model_dump_json(indent=2))
    elif args.command == "policy" and args.policy_command == "save":
        from pydantic import ValidationError

        try:
            policy_input = PolicyInput(text=args.text, purpose=args.purpose, environment=args.environment)
        except ValidationError as exc:
            raise SystemExit(f"invalid policy: {exc.errors()[0]['loc'][0]}: {exc.errors()[0]['msg']}")
        print(Store().save_policy(policy_input).model_dump_json(indent=2))
    elif args.command == "blueprint" and args.blueprint_command == "create":
        try:
            record = create_blueprint(Store(), args.policy)
        except PolicyNotFound:
            raise SystemExit(f"policy not found: {args.policy}")
        except DailyCapReached as exc:
            raise SystemExit(str(exc))
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
    elif args.command == "template" and args.template_command == "check":
        from rulestorm.core.model import check_file

        result = check_file(args.template)
        for line in result.lines():
            print(line)
        if not result.valid:
            raise SystemExit(1)
    elif args.command == "engine" and args.engine_command == "check":
        case = json.loads(Path(args.case).read_text(encoding="utf-8"))
        if args.core:
            from rulestorm.core.engine import run_case as run_core_case
            from rulestorm.core.model import load_template

            lines = run_core_case(case, load_template(case["template"]))
        else:
            from rulestorm.engine import run_case

            lines = run_case(case)
        for line in lines:
            print(line)
    elif args.command == "llm" and args.llm_command == "smoke":
        from rulestorm import smoke

        for line in smoke.run(args.model):
            print(line)

    elif args.command == "run" and args.run_command == "local":
        run_local_command(args.blueprint)
    elif args.command == "explore":
        explore_command(args.explore_command, args.blueprint_id)


def explore_command(command: str, blueprint_id: str) -> None:
    from rulestorm import explore
    from rulestorm.policy import BlueprintNotApproved

    store = Store()
    try:
        if command == "propose":
            result = explore.propose_variants(store, blueprint_id)
            print(f"parent: {result.parent_id}")
            print(f"status: {result.status} | attempts: {result.attempts} | seconds: {result.seconds}")
            for error in result.errors:
                print(f"error: {error}")
            for v in result.variants:
                print(f"- {v.id} [{v.status}] {v.variant}")
                print(f"  weak point: {v.weak_point}")
                if v.blueprint:
                    sc = v.blueprint.scenario
                    print(f"  admin capacity {sc.admin_capacity_per_week} a week | checkpoint week {sc.checkpoint_week}")
                    for d in sc.disruptions:
                        extra = (f"delay {d.delay_min} min, affects {', '.join(d.affected)}" if d.type == "transport"
                                 else f"capacity {d.admin_capacity_during} that week")
                        print(f"    week {d.week} {d.type}: {d.description} ({extra})")
                    print("  labelled as AI assumptions: "
                          + ", ".join(a.field for a in v.blueprint.assumptions if a.statement.startswith("Stress variant")))
                for error in v.errors:
                    print(f"  error: {error}")
            print("approve each variant to run with: python -m rulestorm.cli blueprint approve <id>")
        else:
            rows = explore.run_variants(store, blueprint_id, on_variant=lambda v: print(f"running {v.id} ({v.variant})...", flush=True))
            print("variant | run | status | requests filed | queue over capacity | pending at checkpoint | not eligible | broke")
            for r in rows:
                print(f"{r.blueprint_id} {r.variant} | {r.run_id or '-'} | {r.status} | {r.requests_filed} | "
                      f"{r.queue_over_capacity} | {r.pending_at_checkpoint} | {', '.join(r.not_eligible) or '-'} | "
                      f"{'yes' if r.broke else 'no'}")
            ran = [r for r in rows if r.run_id]
            print(f"broke the policy: {sum(r.broke for r in ran)} of {len(ran)} variants run")
    except BlueprintNotFound:
        raise SystemExit(f"blueprint not found: {blueprint_id}")
    except BlueprintNotApproved:
        raise SystemExit(f"blueprint not approved: {blueprint_id}")
    except DailyCapReached as exc:
        raise SystemExit(str(exc))


def run_local_command(blueprint_id: str) -> None:
    from rulestorm.agents import run_local
    from rulestorm.policy import BlueprintNotApproved

    try:
        run_id, summary, seconds, path = run_local(
            Store(), blueprint_id, on_week=lambda week: print(f"week {week} done", flush=True))
    except BlueprintNotFound:
        raise SystemExit(f"blueprint not found: {blueprint_id}")
    except BlueprintNotApproved:
        raise SystemExit(f"blueprint not approved: {blueprint_id}")
    print(f"run_id: {run_id}")
    print(f"status: {summary.status}")
    print(f"model: {summary.model_id}")
    print(f"seconds: {seconds}")
    print(f"llm_calls: {summary.llm_calls} (cap {summary.llm_cap})")
    print(f"llm_errors: {summary.llm_errors} (timeouts {summary.timeouts})")
    print(f"cap_hits: {summary.cap_hits}")
    print(f"tokens: {summary.input_tokens} in, {summary.output_tokens} out")
    print(f"decisions: {summary.decisions} ({summary.no_actions} no action)")
    for agent, n in summary.decisions_by_agent.items():
        print(f"  {agent}: {n}")
    print(f"rejected: {len(summary.rejected)}")
    for r in summary.rejected:
        print(f"  {r.event_id} {r.agent} {r.action}: {r.reason}")
    print(f"event log: {path}")


if __name__ == "__main__":
    main()
