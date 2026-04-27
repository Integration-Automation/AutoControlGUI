"""CLI: ``python -m je_auto_control.utils.config_bundle export|import <file>``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from je_auto_control.utils.config_bundle.config_bundle import (
    ConfigBundleError, default_bundle_root, export_config_bundle,
    import_config_bundle,
)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="je_auto_control.utils.config_bundle",
        description="Export / import AutoControl user configuration.",
    )
    sub = parser.add_subparsers(dest="action", required=True)

    export_p = sub.add_parser("export", help="Write a bundle JSON file.")
    export_p.add_argument("output", type=Path,
                          help="bundle file to write")
    export_p.add_argument("--root", type=Path, default=None,
                          help="config root (default: ~/.je_auto_control)")

    import_p = sub.add_parser("import", help="Apply a bundle JSON file.")
    import_p.add_argument("input", type=Path,
                          help="bundle file to read")
    import_p.add_argument("--root", type=Path, default=None,
                          help="config root (default: ~/.je_auto_control)")
    import_p.add_argument("--dry-run", action="store_true",
                          help="report what would change without writing")
    return parser


def main(argv: Optional[list] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if args.action == "export":
        return _do_export(args.output, args.root)
    return _do_import(args.input, args.root, args.dry_run)


def _do_export(output: Path, root: Optional[Path]) -> int:
    bundle = export_config_bundle(root=root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote bundle to {output.resolve()}")
    print(f"  source root: {bundle['manifest']['source_root']}")
    print(f"  files included: {len(bundle['files'])}")
    for name in sorted(bundle["files"]):
        print(f"    - {name}")
    return 0


def _do_import(source: Path, root: Optional[Path], dry_run: bool) -> int:
    try:
        bundle = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"failed to read {source}: {error}", file=sys.stderr)
        return 2
    try:
        report = import_config_bundle(bundle, root=root, dry_run=dry_run)
    except ConfigBundleError as error:
        print(f"bundle rejected: {error}", file=sys.stderr)
        return 2
    target_root = root or default_bundle_root()
    print(f"{'(dry run) ' if dry_run else ''}Applied bundle to {target_root}")
    print(f"  written: {len(report.written)}")
    for name in sorted(report.written):
        backup = report.backups.get(name)
        if backup:
            print(f"    - {name}  (backup: {backup})")
        else:
            print(f"    - {name}")
    if report.skipped:
        print(f"  skipped: {len(report.skipped)}")
        for name in sorted(report.skipped):
            print(f"    - {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
