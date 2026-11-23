"""Terminal entry point. Calls the same core code the API and UI will use."""

import argparse


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="rulestorm")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("hello", help="print hello")

    args = parser.parse_args(argv)
    if args.command == "hello":
        print("hello")


if __name__ == "__main__":
    main()
