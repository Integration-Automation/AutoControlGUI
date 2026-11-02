"""``python -m je_auto_control.utils.mcp_server`` entry point.

Without flags this starts the stdio MCP server. With one of the
``--list-*`` flags it prints the requested catalogue to stdout and
exits — useful for inspection in CI or manual debugging.
"""
import argparse
import json
import sys
from typing import Any, Optional

from je_auto_control.utils.cli_output import utf8_stdout
from je_auto_control.utils.mcp_server.fake_backend import (
    install_fake_backend, maybe_install_from_env,
)
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
        "--search-tools", metavar="QUERY", help="Search permitted tool summaries and exit.",
    )
    parser.add_argument(
        "--tool-schema", metavar="NAME", help="Print one permitted tool descriptor and exit.",
    )
    parser.add_argument("--limit", type=int, default=10, help="Tool search result limit (1-50).")
    parser.add_argument("--tool-mode", choices=("full", "progressive", "static"), default=None,
                        help="Tool availability mode (default: environment or full).")
    parser.add_argument("--tool-profile", default=None, metavar="NAMES",
                        help="Comma-separated tool names for the initial/static profile.")
    parser.add_argument("--tool-page-size", type=int, default=None, help="Progressive/static list page size (1-100).")
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
    parser.add_argument(
        "--fake-backend", action="store_true",
        help=("Install the in-memory fake backend so tools record but "
              "don't drive the real OS. Useful for CI smoke tests."),
    )
    return parser


def main(argv: Optional[list] = None) -> None:
    """CLI entry point. Performs the requested action and returns ``None``."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.fake_backend:
        install_fake_backend()
    else:
        maybe_install_from_env()
    listing_modes = (args.list_tools, args.list_resources, args.list_prompts,
                     args.search_tools is not None, args.tool_schema is not None)
    if any(listing_modes):
        _print_listings(args)
        return
    start_mcp_stdio_server(read_only=True if args.read_only else None, **_server_options(args))


def _print_listings(args: argparse.Namespace) -> None:
    """Print the requested catalogues as one JSON document.

    One flag prints its array, as before; several print an object keyed by
    catalogue -- two arrays back to back were not one JSON document. The
    output is UTF-8 whatever the console's code page.
    """
    listings = _discovery_listings(args)
    if args.list_tools:
        listings["tools"] = [tool.to_descriptor() for tool in
                             build_default_tool_registry(read_only=True if args.read_only else None)]
    if args.list_resources:
        listings["resources"] = [item.to_descriptor() for item in default_resource_provider().list()]
    if args.list_prompts:
        listings["prompts"] = [item.to_descriptor() for item in default_prompt_provider().list()]
    document = next(iter(listings.values())) if len(listings) == 1 else listings
    utf8_stdout()
    json.dump(document, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _discovery_listings(args: argparse.Namespace) -> dict[str, Any]:
    from je_auto_control.utils.mcp_server.discovery import ToolIndex
    listings: dict[str, Any] = {}
    if args.search_tools is None and args.tool_schema is None:
        return listings
    index = ToolIndex(build_default_tool_registry(read_only=True if args.read_only else None))
    if args.search_tools is not None:
        listings["matches"] = index.search(args.search_tools, limit=args.limit)
    if args.tool_schema is not None:
        listings["schema"] = index.get_schema(args.tool_schema)
    return listings


def _server_options(args: argparse.Namespace) -> dict[str, Any]:
    options = {key: value for key, value in (("disclosure", args.tool_mode), ("page_size", args.tool_page_size))
               if value is not None}
    if args.tool_profile is not None:
        options["tool_profile"] = [item.strip() for item in args.tool_profile.split(",") if item.strip()]
    return options


if __name__ == "__main__":
    main()
