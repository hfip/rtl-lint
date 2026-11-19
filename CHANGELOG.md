# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
