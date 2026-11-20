# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.1] - 2026-11-20

### Changed

- Migration output reads like English: "1 finding needing a decision", not "1 finding(s)".

## [0.2.0] - 2026-11-20

### Added

- `rtl-lint migrate`: writes `RTL-MIGRATION.md` with mechanical fixes, decisions and what the
  tool cannot check, including user-facing string literals.
- `migrate --apply` creates a branch and one commit per rule group, plus the plan, and refuses
  to run on a dirty tree or an existing branch.
- `--no-branch`, `--force`, `--report`, `--no-report` and `--json` for the migration command.
- 12 tests for the migration flow, 56 in total.

## [0.1.1] - 2026-11-19

### Added

- Composite GitHub Action (`action.yml`): `uses: hfip/rtl-lint@v1` with `paths` and `args`
  inputs, plus a CI job that dogfoods it against a clean fixture.

### Fixed

- Matches inside comments and string literals were reported, and `--fix` rewrote them —
  it could change a log message or a fixture. Only real code is scanned now (`//`,
  nested `/* */`, `"…"`, `"""…"""`, `#"…"#`, XML comments).
- `.rtllint.json` is now discovered by walking up from the current directory, so running
  from a subdirectory still finds the project configuration.
- 44 tests.

## [0.1.0] - 2026-11-19

### Added

- Nine rules covering physical alignment, anchors, layout attributes, edge insets,
  forced layout direction, manual direction branching, manual image mirroring and
  storyboard/xib attributes.
- Safe auto-fix for `RTL001`–`RTL003` with CRLF and byte-preserving rewrites.
- Swift, `.storyboard` and `.xib` scanning with dependency directories always skipped.
- Inline suppression: `// rtl-lint:ignore` and `// rtl-lint:ignore RTL001,RTL003`.
- `.rtllint.json` config: `exclude`, `ignore`, per-rule `severity`.
- Output formats: text, GitHub Actions annotations, JSON.
- 35 tests, zero runtime dependencies.
