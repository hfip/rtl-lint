"""Command line interface for rtl-lint."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterable, List, Optional

from . import __version__
from .rules import RULES
from .scanner import Config, ConfigError, Issue, ScanReport, run

GREEN = "32"
RED = "31"
YELLOW = "33"
DIM = "2"
BOLD = "1"


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


class Painter:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def __call__(self, code: str, text: str) -> str:
        if not self.enabled:
            return text
        return "\x1b[%sm%s\x1b[0m" % (code, text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rtl-lint",
        description="Catch left/right layout assumptions in Swift and storyboards "
        "before your Arabic users do.",
        epilog="example: rtl-lint --fix Sources/",
    )
    parser.add_argument(
        "paths", nargs="*", help="files or directories (default: current directory)"
    )
    parser.add_argument("-f", "--fix", action="store_true", help="rewrite safe, physical values")
    parser.add_argument(
        "--format",
        choices=("text", "github", "json"),
        default="text",
        help="output format (github emits workflow annotations)",
    )
    parser.add_argument(
        "--ignore", action="append", default=[], metavar="CODE", help="ignore a rule"
    )
    parser.add_argument(
        "--exclude", action="append", default=[], metavar="GLOB", help="skip matching paths"
    )
    parser.add_argument("--config", metavar="FILE", help="path to .rtllint.json")
    parser.add_argument("--explain", action="store_true", help="show the fix hint under each issue")
    parser.add_argument("--list-rules", action="store_true", help="print every rule and exit")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    parser.add_argument("-q", "--quiet", action="store_true", help="print issues only")
    parser.add_argument("-V", "--version", action="version", version="rtl-lint " + __version__)
    return parser


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _severity_label(issue: Issue) -> str:
    return "error" if issue.severity == "error" else "warning"


def render_text(
    report: ScanReport,
    paint: Painter,
    explain: bool = False,
    quiet: bool = False,
) -> None:
    if not report.issues:
        if not quiet:
            print(
                paint(GREEN, "No RTL issues found")
                + paint(DIM, " in %d file(s)." % report.files_scanned)
            )
        return

    current: Optional[str] = None
    for issue in sorted(report.issues, key=lambda item: (str(item.path), item.line, item.column)):
        path = display_path(issue.path)
        if path != current:
            if current is not None:
                print()
            print(paint(BOLD, path))
            current = path

        location = "%d:%d" % (issue.line, issue.column)
        label = _severity_label(issue)
        color = RED if issue.severity == "error" else YELLOW
        suffix = paint(DIM, "  (fixable)") if issue.fixable else ""
        print(
            "  %s  %s  %s  %s%s"
            % (
                paint(DIM, location.ljust(9)),
                paint(color, label.ljust(7)),
                paint(BOLD, issue.code),
                issue.message,
                suffix,
            )
        )
        if explain:
            print("              %s" % paint(DIM, issue.hint))


def render_summary(report: ScanReport, paint: Painter, fix_command: bool = True) -> None:
    if report.fixed:
        print(paint(GREEN, "Fixed %d issue(s)." % report.fixed))
    if not report.issues:
        return
    parts = [
        "%d issue(s) in %d file(s)" % (len(report.issues), report.affected_files),
        "%d error(s)" % report.errors,
        "%d warning(s)" % report.warnings,
    ]
    if report.fixable and fix_command:
        parts.append("%d auto-fixable, run rtl-lint --fix" % report.fixable)
    print()
    print(paint(BOLD, " · ".join(parts)))


def render_github(report: ScanReport) -> None:
    for issue in report.issues:
        level = "error" if issue.severity == "error" else "warning"
        message = issue.message if not issue.hint else "%s %s" % (issue.message, issue.hint)
        print(
            "::%s file=%s,line=%d,col=%d,title=%s::%s"
            % (level, display_path(issue.path), issue.line, issue.column, issue.code, message)
        )


def render_json(report: ScanReport) -> None:
    payload = {
        "version": __version__,
        "files": report.files_scanned,
        "fixed": report.fixed,
        "issues": [issue.to_dict(Path.cwd()) for issue in report.issues],
        "summary": {
            "issues": len(report.issues),
            "errors": report.errors,
            "warnings": report.warnings,
            "fixable": report.fixable,
            "affected_files": report.affected_files,
        },
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def render_rules() -> None:
    print("%-8s %-9s %s" % ("CODE", "SEVERITY", "DESCRIPTION"))
    for rule in RULES:
        print("%-8s %-9s %s" % (rule.code, rule.severity, rule.message))


def main(argv: Optional[Iterable[str]] = None) -> int:
    raw = list(argv) if argv is not None else sys.argv[1:]
    if raw and raw[0] == "migrate":
        from .migrate_cli import main as migrate_main

        return migrate_main(raw[1:])

    parser = build_parser()
    args = parser.parse_args(raw)

    if args.list_rules:
        render_rules()
        return 0

    paint = Painter(_supports_color() and not args.no_color and args.format == "text")

    try:
        config = Config.load(Path(args.config) if args.config else None)
    except ConfigError as error:
        print(paint(RED, "error: " + str(error)), file=sys.stderr)
        return 2

    config.ignore = tuple(sorted(set(config.ignore) | {code.upper() for code in args.ignore}))
    config.exclude = config.exclude + tuple(args.exclude)

    paths: List[str] = args.paths or ["."]
    try:
        report = run(paths, config, fix=args.fix)
    except FileNotFoundError as error:
        print(paint(RED, "error: " + str(error)), file=sys.stderr)
        return 2

    if args.format == "json":
        render_json(report)
    elif args.format == "github":
        render_github(report)
    else:
        render_text(report, paint, explain=args.explain, quiet=args.quiet)
        if not args.quiet:
            render_summary(report, paint)

    return 1 if report.issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
