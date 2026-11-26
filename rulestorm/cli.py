"""Terminal entry point. Calls the same core code the API and UI will use."""

import argparse
import json
import sys
from pathlib import Path

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
    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp1252, which can't print "→" or "…"
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="rulestorm")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("hello", help="print hello")

    policy = commands.add_parser("policy", help="policy input")
    policy_commands = policy.add_subparsers(dest="policy_command", required=True)
    example_cmd = policy_commands.add_parser("example", help="save a template's pre-filled example and print it")
    example_cmd.add_argument("--template", default="attendance", help="template name (default: attendance)")
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
    check_cmd.add_argument("--core", action="store_true",
                           help="the general engine (the only engine since slice L7; kept for the proofs)")

    llm = commands.add_parser("llm", help="model adapter")
    llm_commands = llm.add_subparsers(dest="llm_command", required=True)
    smoke_cmd = llm_commands.add_parser("smoke", help="real Bedrock call: auth, latency, tokens, quotas")
    smoke_cmd.add_argument("--model", help="Bedrock model ID (default: the configured model)")

    run = commands.add_parser("run", help="simulated terms")
    run_commands = run.add_subparsers(dest="run_command", required=True)
    local_cmd = run_commands.add_parser("local", help="run one real term here, with Bedrock agents")
    local_cmd.add_argument("--blueprint", required=True, help="an approved blueprint ID")
    export_cmd = run_commands.add_parser("export", help="save a finished run, its blueprint and policy to a file (slice 10)")
    export_cmd.add_argument("run_id", help="a finished run in the store")
    export_cmd.add_argument("--out", required=True, help="the file to write, e.g. rulestorm/fixtures/demo_run.json")
    export_cmd.add_argument("--hero", help="the finding shown as the hero (default: the run's first finding)")
    reset_cmd = commands.add_parser("reset-demo", help="restore the seeded demo run as run `demo` (no Bedrock)")
    reset_cmd.add_argument("--fixture", help="the demo file (default: rulestorm/fixtures/demo_run.json)")

    explore = commands.add_parser("explore", help="stress variants of an approved blueprint (slices 6c, L8)")
    explore_commands = explore.add_subparsers(dest="explore_command", required=True)
    propose_cmd = explore_commands.add_parser("propose", help="ask Bedrock for up to 3 harsher scenarios")
    propose_cmd.add_argument("blueprint_id", help="an approved blueprint ID")
    explore_run_cmd = explore_commands.add_parser("run", help="run every approved variant, one real term each")
    explore_run_cmd.add_argument("blueprint_id", help="the approved blueprint the variants vary")
    hunt_cmd = explore_commands.add_parser(
        "hunt", help="run the approved variants, then the parent, until a run has a finding (slice H)")
    hunt_cmd.add_argument("blueprint_id", help="the approved blueprint the variants vary")
    hunt_cmd.add_argument("--max-runs", type=int, default=10, help="stop after this many runs (default 10)")

    args = parser.parse_args(argv)
    if args.command == "hello":
        print("hello")
    elif args.command == "policy" and args.policy_command == "example":
        from rulestorm.core.model import load_template

        example = load_template(args.template).example_input
        saved = Store().save_policy(PolicyInput(**example.model_dump()))
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
        for line in describe_blueprint(record):
            print(line)
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
        from rulestorm.core.cases import run_case
        from rulestorm.core.model import load_template

        lines = run_case(case, load_template(case["template"]))
        for line in lines:
            print(line)
    elif args.command == "llm" and args.llm_command == "smoke":
        from rulestorm import smoke

        for line in smoke.run(args.model):
            print(line)

    elif args.command == "run" and args.run_command == "local":
        run_local_command(args.blueprint)
    elif args.command == "run" and args.run_command == "export":
        from rulestorm.fixture import FixtureError, export_run, write_fixture

        try:
            bundle = export_run(Store(), args.run_id, hero=args.hero)
        except FixtureError as exc:
            raise SystemExit(str(exc))
        path = write_fixture(bundle, args.out)
        hero = bundle["hero"]
        print(f"exported run {args.run_id} (schema {bundle['schema']}): {len(bundle['events'])} events, "
              f"{len(bundle['findings'])} findings, blueprint {bundle['blueprint']['id']}, policy {bundle['policy']['id']}")
        print(f"hero: {hero['finding_id']} {hero['kind']} {hero['person']}: {hero['title']}")
        print(f"wrote {path}")
    elif args.command == "reset-demo":
        from rulestorm.fixture import DEFAULT_PATH, FixtureError, restore_demo

        try:
            restored = restore_demo(Store(), args.fixture or DEFAULT_PATH)
        except FixtureError as exc:
            raise SystemExit(f"reset-demo refused: {exc}")
        print(f"restored run {restored['run_id']} (schema {restored['schema']}) with policy and blueprint")
        print(f"from {restored['source_run_id']}: {restored['events']} events, {restored['findings']} findings, "
              f"hero {restored['hero']}")
    elif args.command == "explore":
        explore_command(args.explore_command, args.blueprint_id, getattr(args, "max_runs", 10))


def describe_blueprint(record) -> list[str]:
    """A created blueprint in plain lines: the pick, the status, then every value with its label."""
    from rulestorm.blueprint import TemplateBlueprint
    from rulestorm.core.model import load_template

    lines = [f"id: {record.id}", f"policy: {record.policy_id}"]
    if record.template_id:
        lines.append(f"template: {record.template_id}@{record.template_version} (AI pick: {record.pick_reason})")
    elif record.status == "out_of_scope":
        lines.append(f"template: none (AI pick: {record.pick_reason})")
    lines.append(f"status: {record.status} | attempts: {record.attempts} | seconds: {record.seconds} | "
                 f"tokens: {record.input_tokens} in, {record.output_tokens} out")
    lines += [f"retried after: {r}" for r in record.retried]
    lines += [f"error: {e}" for e in record.errors]
    bp = record.blueprint
    if not isinstance(bp, TemplateBlueprint):
        return lines
    template = load_template(bp.template_id)
    for section in ("policy", "environment", "people"):
        lines.append(f"{section}:")
        for p in template.parameters:
            if p.kind != section:
                continue
            value = bp.values[p.name]
            if p.type == "disruptions":
                shown = "; ".join(f"{template.calendar.period_label} {d['period']} {d['kind']}: {d['description']}"
                                  for d in value)
            elif p.type == "profiles":
                shown = "; ".join(f"{pid}: {prof['description']}" for pid, prof in value.items())
            elif isinstance(value, dict):
                shown = ", ".join(f"{k} {v}" for k, v in value.items())
            else:
                shown = str(value).lower() if isinstance(value, bool) else str(value)
            label = bp.label_for(template, p.name)
            tag = f"  [{label[0]}: {label[1].statement}]" if label else "  [unlabelled]"
            lines.append(f"  {p.name}: {shown}{tag}")
    return lines


def explore_command(command: str, blueprint_id: str, max_runs: int = 10) -> None:
    from rulestorm import explore
    from rulestorm.policy import BlueprintNotApproved
    from rulestorm.runner import RunActive

    store = Store()
    try:
        if command == "propose":
            for line in describe_variants(explore.propose_variants(store, blueprint_id)):
                print(line)
        elif command == "hunt":
            if max_runs < 1:
                raise SystemExit("--max-runs must be at least 1")
            result = explore.hunt(store, blueprint_id, max_runs, on_run=lambda n, bp_id, variant: print(
                f"run {n}/{max_runs}: {bp_id} ({variant or 'the parent'})...", flush=True))
            for line in hunt_lines(result):
                print(line)
        else:
            rows = explore.run_variants(store, blueprint_id, on_variant=lambda v: print(
                f"running {v.id} ({v.variant})...", flush=True))
            for line in variant_table(rows):
                print(line)
    except BlueprintNotFound:
        raise SystemExit(f"blueprint not found: {blueprint_id}")
    except BlueprintNotApproved:
        raise SystemExit(f"blueprint not approved: {blueprint_id}")
    except DailyCapReached as exc:
        raise SystemExit(str(exc))
    except RunActive as exc:
        raise SystemExit(f"a run is already running: {exc.run_id}")
    except ValueError as exc:  # the template changed since the blueprint was made
        raise SystemExit(str(exc))


def hunt_lines(result) -> list[str]:
    """Each run's outcome, then the run found with its findings and their chains, or why none."""
    lines = [f"  {r.run_id}: {r.status}, {r.findings} finding{'s' * (r.findings != 1)}" for r in result.runs]
    if result.found:
        f = result.found
        lines.append(f"found: {f.run_id} ({f.variant or 'the parent'}, {f.blueprint_id}), status {f.status}")
        for finding in result.findings:
            lines.append(f"  {finding['finding_id']} {finding['kind']} {finding['person']}: {finding['title']}")
            lines.append(f"    chain: {' → '.join(finding['chain'])}")
    elif result.stopped:
        lines.append(f"stopped after {len(result.runs)} runs: {result.stopped}")
    elif any(r.findings for r in result.runs):  # slice M2: only near misses, which don't stop it
        lines.append(f"no harm in {len(result.runs)} runs (near misses only)")
    else:
        lines.append(f"no finding in {len(result.runs)} runs")
    return lines


def describe_variants(result) -> list[str]:
    """Each variant with only the environment values it changed, as stored and labelled."""
    from rulestorm.core.model import load_template

    lines = [f"parent: {result.parent_id}",
             f"status: {result.status} | attempts: {result.attempts} | seconds: {result.seconds}"]
    lines += [f"error: {e}" for e in result.errors]
    for v in result.variants:
        lines.append(f"- {v.id} [{v.status}] {v.variant}")
        lines.append(f"  weak point: {v.weak_point}")
        lines += [f"  error: {e}" for e in v.errors]
        if v.blueprint is None:
            continue
        template = load_template(v.blueprint.template_id)
        cal = template.calendar
        for label in v.blueprint.assumptions:
            if not label.statement.startswith("Stress variant"):
                continue
            value = v.blueprint.values[label.field]
            lines.append(f"  {label.field} [assumption: {label.statement}]")
            if isinstance(value, list):
                for d in value:
                    detail = [f"{cal.step_label}s {d['steps']}" if d["steps"] else "",
                              f"people {', '.join(d['people'])}" if d["people"] else "",
                              f"delay {d['delay']}" if d["delay"] else "",
                              f"capacity {d['capacity']}" if d["capacity"] is not None else ""]
                    lines.append(f"    {cal.period_label} {d['period']} {d['kind']}: {d['description']} "
                                 f"({'; '.join(x for x in detail if x)})")
            else:
                lines.append(f"    now {value}")
    lines.append("approve each variant to run with: python -m rulestorm.cli blueprint approve <id>")
    return lines


def variant_table(rows) -> list[str]:
    lines = ["variant | run | status | requests filed | queue over capacity | pending at check | failed check | broke"]
    for r in rows:
        lines.append(f"{r.blueprint_id} {r.variant} | {r.run_id or '-'} | {r.status} | {r.requests_filed} | "
                     f"{r.queue_over_capacity} | {r.pending_at_check} | {', '.join(r.check_failed) or '-'} | "
                     f"broke: {('yes' if r.broke else 'no') if r.run_id else '-'}")
    ran = [r for r in rows if r.run_id]
    lines.append(f"broke the policy: {sum(r.broke for r in ran)} of {len(ran)}")
    return lines


def run_local_command(blueprint_id: str) -> None:
    from rulestorm.agents import run_local
    from rulestorm.policy import BlueprintNotApproved

    try:
        run_id, summary, seconds, path = run_local(
            Store(), blueprint_id, on_period=lambda period: print(f"period {period} done", flush=True))
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
