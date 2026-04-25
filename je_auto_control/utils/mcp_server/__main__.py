"""``python -m je_auto_control.utils.mcp_server`` entry point.

Without flags this starts the stdio MCP server. With one of the
``--list-*`` flags it prints the requested catalogue to stdout and
exits — useful for inspection in CI or manual debugging.
"""
import argparse
import json
import sys

from je_auto_control.utils.mcp_server.prompts import default_prompt_provider
from je_auto_control.utils.mcp_server.resources import (
    default_resource_provider,
)
from je_auto_control.utils.mcp_server.server import start_mcp_stdio_server
from je_auto_control.utils.mcp_server.tools import (
    build_default_tool_registry,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="je_auto_control_mcp",
        description="Run AutoControl's MCP server (stdio) or list its catalogue.",
    )
    parser.add_argument(
        "--list-tools", action="store_true",
        help="Print all tool descriptors as JSON and exit.",
    )
    parser.add_argument(
        "--list-resources", action="store_true",
        help="Print all resource descriptors as JSON and exit.",
    )
    parser.add_argument(
        "--list-prompts", action="store_true",
        help="Print all prompt descriptors as JSON and exit.",
    )
    parser.add_argument(
        "--read-only", action="store_true",
        help="Restrict tools to those marked readOnlyHint=true.",
    )
    return parser


def main(argv: list = None) -> int:
    """CLI entry point. Returns the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    listing_modes = (args.list_tools, args.list_resources, args.list_prompts)
    if any(listing_modes):
        _print_listings(args)
        return 0
    start_mcp_stdio_server()
    return 0


def _print_listings(args: argparse.Namespace) -> None:
    if args.list_tools:
        registry = build_default_tool_registry(read_only=args.read_only)
        json.dump([tool.to_descriptor() for tool in registry],
                   sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    if args.list_resources:
        provider = default_resource_provider()
        json.dump([resource.to_descriptor() for resource in provider.list()],
                   sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    if args.list_prompts:
        provider = default_prompt_provider()
        json.dump([prompt.to_descriptor() for prompt in provider.list()],
                   sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")


if __name__ == "__main__":
    sys.exit(main())
