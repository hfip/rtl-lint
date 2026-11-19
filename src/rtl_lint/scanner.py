"""File discovery, scanning and auto-fixing."""

from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .rules import RULES, Rule, SWIFT, XML

KIND_BY_SUFFIX = {".swift": SWIFT, ".xib": XML, ".storyboard": XML}

SKIP_DIRS = {
    ".git",
    ".build",
    ".swiftpm",
    "Pods",
    "Carthage",
    "DerivedData",
    "node_modules",
    "build",
    "vendor",
    ".venv",
    "venv",
}

SUPPRESS_RE = re.compile(r"rtl-lint:\s*ignore(?:\s+([A-Za-z0-9][A-Za-z0-9,\s]*))?", re.IGNORECASE)
MAX_FILE_SIZE = 2 * 1024 * 1024


class ConfigError(Exception):
    pass


@dataclass
class Config:
    exclude: Tuple[str, ...] = ()
    ignore: Tuple[str, ...] = ()
    severity: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        if path is not None:
            candidate = Path(path)
            if not candidate.exists():
                raise ConfigError("config file not found: %s" % candidate)
            return cls._from_file(candidate)

        # Walk up from the current directory so running from a subdirectory still
        # finds the project configuration.
        for directory in (Path.cwd(), *Path.cwd().parents):
            candidate = directory / ".rtllint.json"
            if candidate.is_file():
                return cls._from_file(candidate)
        return cls()

    @classmethod
    def _from_file(cls, candidate: Path) -> "Config":
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConfigError("cannot read %s: %s" % (candidate, error))
        if not isinstance(payload, dict):
            raise ConfigError("%s must contain a JSON object" % candidate)

        exclude = payload.get("exclude", [])
        ignore = payload.get("ignore", [])
        severity = payload.get("severity", {})
        if not isinstance(exclude, list) or not isinstance(ignore, list):
            raise ConfigError("'exclude' and 'ignore' must be lists")
        if not isinstance(severity, dict):
            raise ConfigError("'severity' must be an object")
        unknown = [code for code in severity if code not in {rule.code for rule in RULES}]
        if unknown:
            raise ConfigError("unknown rule code in severity: %s" % ", ".join(unknown))

        return cls(
            exclude=tuple(str(item) for item in exclude),
            ignore=tuple(str(item).upper() for item in ignore),
            severity={str(k).upper(): str(v) for k, v in severity.items()},
        )


@dataclass
class Issue:
    path: Path
    line: int
    column: int
    end_column: int
    code: str
    message: str
    severity: str
    source: str
    hint: str = ""
    replacement: Optional[str] = None

    @property
    def fixable(self) -> bool:
        return self.replacement is not None

    def to_dict(self, root: Optional[Path] = None) -> dict:
        return {
            "path": _display_path(self.path, root),
            "line": self.line,
            "column": self.column,
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "hint": self.hint,
            "fixable": self.fixable,
            "source": self.source,
        }


@dataclass
class ScanReport:
    issues: List[Issue] = field(default_factory=list)
    files_scanned: int = 0
    fixed: int = 0

    @property
    def errors(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    @property
    def fixable(self) -> int:
        return sum(1 for issue in self.issues if issue.fixable)

    @property
    def affected_files(self) -> int:
        return len({issue.path for issue in self.issues})


def _display_path(path: Path, root: Optional[Path]) -> str:
    if root is None:
        return str(path)
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _is_excluded(path: Path, patterns: Sequence[str]) -> bool:
    if not patterns:
        return False
    text = path.as_posix()
    name = path.name
    return any(
        fnmatch.fnmatch(text, pattern) or fnmatch.fnmatch(name, pattern) for pattern in patterns
    )


def discover(paths: Sequence[str], exclude: Sequence[str] = ()) -> List[Tuple[Path, str]]:
    """Collect (path, kind) pairs for every supported file."""
    found: List[Tuple[Path, str]] = []
    seen = set()

    def add(candidate: Path) -> None:
        kind = KIND_BY_SUFFIX.get(candidate.suffix.lower())
        if kind is None:
            return
        if _is_excluded(candidate, exclude):
            return
        try:
            if candidate.stat().st_size > MAX_FILE_SIZE:
                return
            key = candidate.resolve()
        except OSError:
            return
        if key in seen:
            return
        seen.add(key)
        found.append((candidate, kind))

    for raw in paths:
        target = Path(raw).expanduser()
        if target.is_dir():
            for root, dirnames, filenames in os.walk(target):
                dirnames[:] = sorted(
                    name for name in dirnames if name not in SKIP_DIRS and not name.startswith(".")
                )
                for filename in sorted(filenames):
                    add(Path(root) / filename)
        elif target.is_file():
            add(target)
        else:
            raise FileNotFoundError("no such file or directory: %s" % raw)

    return found


def _count_hashes(line: str, index: int) -> int:
    count = 0
    while index + count < len(line) and line[index + count] == "#":
        count += 1
    return count


def _is_raw_string_start(line: str, index: int) -> bool:
    count = _count_hashes(line, index)
    return index + count < len(line) and line[index + count] == '"'


def swift_code_mask(lines: Sequence[str]) -> List[List[bool]]:
    """Mark characters that are real code (not comments or string literals).

    Rewriting `.left` inside a comment or a string literal is never what a user
    wants, so matches in those regions are ignored by both reporting and `--fix`.
    Handles `//`, nested `/* */`, `"…"`, `\"` escapes, `\"\"\"…\"\"\"` and `#"…"#`.
    """
    masks: List[List[bool]] = []
    state = "code"
    depth = 0
    hashes = 0

    for line in lines:
        length = len(line)
        mask = [True] * length
        index = 0

        while index < length:
            if state == "code":
                if line.startswith("//", index):
                    for position in range(index, length):
                        mask[position] = False
                    index = length
                elif line.startswith("/*", index):
                    mask[index] = False
                    if index + 1 < length:
                        mask[index + 1] = False
                    state, depth = "block", 1
                    index += 2
                elif line.startswith('"""', index):
                    for position in range(index, min(index + 3, length)):
                        mask[position] = False
                    state = "multiline"
                    index += 3
                elif line[index] == "#" and _is_raw_string_start(line, index):
                    hashes = _count_hashes(line, index)
                    for position in range(index, min(index + hashes + 1, length)):
                        mask[position] = False
                    state = "raw"
                    index += hashes + 1
                elif line[index] == '"':
                    mask[index] = False
                    state = "string"
                    index += 1
                else:
                    index += 1
            elif state == "block":
                if line.startswith("*/", index):
                    mask[index] = False
                    if index + 1 < length:
                        mask[index + 1] = False
                    index += 2
                    depth -= 1
                    if depth == 0:
                        state = "code"
                elif line.startswith("/*", index):
                    mask[index] = False
                    if index + 1 < length:
                        mask[index + 1] = False
                    depth += 1
                    index += 2
                else:
                    mask[index] = False
                    index += 1
            elif state == "string":
                mask[index] = False
                if line[index] == "\\" and index + 1 < length:
                    mask[index + 1] = False
                    index += 2
                elif line[index] == '"':
                    state = "code"
                    index += 1
                else:
                    index += 1
            elif state == "multiline":
                if line.startswith('"""', index):
                    for position in range(index, min(index + 3, length)):
                        mask[position] = False
                    index += 3
                    state = "code"
                else:
                    mask[index] = False
                    index += 1
            else:  # raw string
                mask[index] = False
                if line.startswith('"' + "#" * hashes, index):
                    for position in range(index, min(index + 1 + hashes, length)):
                        mask[position] = False
                    index += 1 + hashes
                    state = "code"
                else:
                    index += 1

        masks.append(mask)
        if state == "string":
            # Swift strings cannot span lines; recover instead of masking the file.
            state = "code"

    return masks


def xml_code_mask(lines: Sequence[str]) -> List[List[bool]]:
    """Mark characters outside XML comments."""
    masks: List[List[bool]] = []
    in_comment = False

    for line in lines:
        length = len(line)
        mask = [True] * length
        index = 0

        if in_comment:
            end = line.find("-->")
            if end == -1:
                mask = [False] * length
                masks.append(mask)
                continue
            for position in range(0, end + 3):
                mask[position] = False
            in_comment = False
            index = end + 3

        while index < length:
            start = line.find("<!--", index)
            if start == -1:
                break
            end = line.find("-->", start + 4)
            if end == -1:
                for position in range(start, length):
                    mask[position] = False
                in_comment = True
                break
            for position in range(start, end + 3):
                mask[position] = False
            index = end + 3

        masks.append(mask)

    return masks


def _is_code(mask: Sequence[bool], start: int, end: int) -> bool:
    if start < 0 or end <= start or end > len(mask):
        return False
    return bool(mask[start]) and bool(mask[end - 1])


def _suppression(line: str) -> Union[None, bool, set]:
    match = SUPPRESS_RE.search(line)
    if match is None:
        return None
    codes = match.group(1)
    if not codes:
        return True
    return {part.strip().upper() for part in codes.split(",") if part.strip()}


def _overlaps(spans: Dict[int, List[Tuple[int, int]]], line: int, start: int, end: int) -> bool:
    for used_start, used_end in spans.get(line, ()):
        if start < used_end and used_start < end:
            return True
    return False


def scan_file(
    path: Path,
    kind: str,
    rules: Iterable[Rule] = RULES,
    severity_map: Optional[Dict[str, str]] = None,
) -> List[Issue]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if "\x00" in text[:2048]:
        return []

    severity_map = severity_map or {}
    issues: List[Issue] = []
    spans: Dict[int, List[Tuple[int, int]]] = {}

    lines = text.split("\n")
    masks = swift_code_mask(lines) if kind == SWIFT else xml_code_mask(lines)

    for number, line in enumerate(lines, start=1):
        mask = masks[number - 1]
        suppression = _suppression(line)
        if suppression is True:
            continue

        for rule in rules:
            if kind not in rule.kinds:
                continue
            if suppression and rule.code in suppression:
                continue
            for match in rule.pattern.finditer(line):
                if match.start() == match.end():
                    continue
                if not _is_code(mask, match.start(), match.end()):
                    continue
                if _overlaps(spans, number, match.start(), match.end()):
                    continue
                replacement = rule.fix(match) if rule.fix else None
                issues.append(
                    Issue(
                        path=path,
                        line=number,
                        column=match.start() + 1,
                        end_column=match.end() + 1,
                        code=rule.code,
                        message=rule.message,
                        severity=severity_map.get(rule.code, rule.severity),
                        source=match.group(0),
                        hint=rule.hint,
                        replacement=replacement,
                    )
                )
                spans.setdefault(number, []).append((match.start(), match.end()))

    return issues


def apply_fixes(issues: Sequence[Issue]) -> int:
    """Rewrite files in place. Returns the number of applied replacements."""
    by_path: Dict[Path, List[Issue]] = {}
    for issue in issues:
        if issue.replacement is None:
            continue
        by_path.setdefault(issue.path, []).append(issue)

    applied = 0
    for path, items in by_path.items():
        try:
            text = path.read_bytes().decode("utf-8", errors="surrogateescape")
        except OSError:
            continue

        newline = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(newline)
        changed = False

        for issue in sorted(items, key=lambda item: (item.line, item.column), reverse=True):
            index = issue.line - 1
            if index < 0 or index >= len(lines):
                continue
            line = lines[index]
            start, end = issue.column - 1, issue.end_column - 1
            if line[start:end] != issue.source:
                continue
            lines[index] = line[:start] + (issue.replacement or "") + line[end:]
            changed = True
            applied += 1

        if changed:
            try:
                path.write_bytes(newline.join(lines).encode("utf-8", errors="surrogateescape"))
            except OSError:
                continue

    return applied


def run(paths: Sequence[str], config: Optional[Config] = None, fix: bool = False) -> ScanReport:
    config = config or Config()
    files = discover(paths, config.exclude)
    ignored = set(config.ignore)
    rules = [rule for rule in RULES if rule.code not in ignored]

    issues: List[Issue] = []
    for path, kind in files:
        issues.extend(scan_file(path, kind, rules, config.severity))

    report = ScanReport(issues=issues, files_scanned=len(files))

    if fix and any(issue.fixable for issue in issues):
        report.fixed = apply_fixes(issues)
        if report.fixed:
            remaining: List[Issue] = []
            for path, kind in files:
                remaining.extend(scan_file(path, kind, rules, config.severity))
            report.issues = remaining

    return report
