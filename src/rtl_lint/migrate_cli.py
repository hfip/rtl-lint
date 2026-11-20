"""Command line interface for `rtl-lint migrate`."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional

from . import __version__
from .migrate import (
    MigrationError,
    MigrationPlan,
    apply_plan,
    build_markdown,
    find_hardcoded_strings,
    migration_json,
    repository_root,
)
from .scanner import Config, ConfigError, run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rtl-lint migrate",
        description="Turn a scan into a migration plan, and optionally a branch with fixes.",
        epilog="example: rtl-lint migrate Sources/ --apply --branch rtl-prep",
    )
    parser.add_argument(
        "paths", nargs="*", help="files or directories (default: current directory)"
    )
    parser.add_argument("--apply", action="store_true", help="apply safe fixes and commit them")
    parser.add_argument(
        "--branch",
        default="rtl-prep",
        help="branch to create when applying (default: rtl-prep)",
    )
    parser.add_argument("--no-branch", action="store_true", help="apply on the current branch")
    parser.add_argument(
        "--report",
        default="RTL-MIGRATION.md",
        metavar="FILE",
        help="where to write the plan (default: RTL-MIGRATION.md)",
    )
    parser.add_argument("--no-report", action="store_true", help="do not write the markdown file")
    parser.add_argument("--force", action="store_true", help="apply even with a dirty working tree")
    parser.add_argument("--json", action="store_true", help="machine-readable summary")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("-V", "--version", action="version", version="rtl-lint " + __version__)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        config = Config.load()
    except ConfigError as error:
        print("error: %s" % error, file=sys.stderr)
        return 2

    paths: List[str] = args.paths or ["."]
    try:
        scan = run(paths, config)
    except FileNotFoundError as error:
        print("error: %s" % error, file=sys.stderr)
        return 2

    plan = MigrationPlan(files_scanned=scan.files_scanned, issues=scan.issues)
    plan.strings = find_hardcoded_strings(paths, config)

    root = repository_root(paths)
    report_path = None
    if not args.no_report:
        report_path = Path(args.report)
        if not report_path.is_absolute() and root is not None:
            report_path = root / report_path

    report_text = build_markdown(plan, root)

    if args.json:
        print(json.dumps(migration_json(plan, root), indent=2, ensure_ascii=False))

    if args.apply:
        if root is None:
            print("error: --apply needs a git repository", file=sys.stderr)
            return 2
        try:
            commits, _ = apply_plan(
                paths,
                config,
                root,
                None if args.no_branch else args.branch,
                report_path,
                report_text,
                force=args.force,
            )
        except MigrationError as error:
            print("error: %s" % error, file=sys.stderr)
            return 2
        except subprocess.CalledProcessError as error:
            print(
                "error: git %s failed: %s" % (" ".join(error.cmd[1:]), error.stderr.strip()),
                file=sys.stderr,
            )
            return 2

        if not args.json:
            print("Scanned %d file(s)." % plan.files_scanned)
            print("  %d mechanical fix(es)" % len(plan.mechanical))
            print("  %d finding(s) that need a decision" % len(plan.decisions))
            if plan.strings:
                print("  %d user-facing literal(s)" % len(plan.strings))
            print()
            if args.no_branch:
                print("Applied on the current branch.")
            else:
                print("Created branch %s" % args.branch)
            for index, commit in enumerate(commits, start=1):
                print("  %d. %s" % (index, commit))
            print()
            if report_path is not None:
                print("Plan written to %s" % report_path.name)
            print("Next: open a pull request and review the diff.")
        return 0

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_text, encoding="utf-8")

    if not args.json:
        print("Scanned %d file(s)." % plan.files_scanned)
        print(
            "  %d mechanical fix(es) in %d group(s)"
            % (len(plan.mechanical), len({issue.code for issue in plan.mechanical}))
        )
        print("  %d finding(s) that need a decision" % len(plan.decisions))
        if plan.strings:
            print("  %d user-facing literal(s)" % len(plan.strings))
        print()
        if report_path is not None:
            print("Plan written to %s" % report_path)
        print("Nothing was changed. Review the plan, then run:")
        print("  rtl-lint migrate %s --apply" % " ".join(paths if paths != ["."] else [""]).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
