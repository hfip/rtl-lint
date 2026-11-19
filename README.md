<p align="center">
  <img src="assets/header.svg" alt="rtl-lint annotating a left alignment on ruled paper" width="100%">
</p>

<p>
  <a href="https://github.com/hfip/rtl-lint/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/hfip/rtl-lint/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="MIT" src="https://img.shields.io/badge/license-MIT-2f6f4f">
</p>

# rtl-lint

A linter for the half of your UI that only breaks in Arabic.

```
Sources/ProfileView.swift
  9:20   error    RTL001  Physical alignment does not mirror in right-to-left layouts.  (fixable)
  14:20  error    RTL003  Left/right anchors and layout attributes are physical and never mirror.  (fixable)
  15:47  warning  RTL005  Forcing a layout direction disables mirroring for this view.

3 issue(s) in 1 file(s) · 2 error(s) · 1 warning(s) · 2 auto-fixable, run rtl-lint --fix
```

None of those three lines fails to compile. None of them looks wrong in an English build.
Two of them simply never mirror, and the third turns mirroring off for everything below it.

## Rules

| Code | Severity | Looks for |
| --- | --- | --- |
| `RTL001` | error | `textAlignment`, `contentHorizontalAlignment`, `alignment` set to `.left` / `.right` |
| `RTL002` | error | explicit `NSTextAlignment.left`, `UIControl.ContentHorizontalAlignment.right` |
| `RTL003` | error | `leftAnchor`, `rightAnchor`, `leftMargin`, `NSLayoutConstraint.Attribute.left`, `attribute: .right` |
| `RTL004` | warning | `UIEdgeInsets(top:left:bottom:right:)` |
| `RTL005` | warning | `.forceLeftToRight` / `.forceRightToLeft` |
| `RTL006` | warning | manual `userInterfaceLayoutDirection` branching |
| `RTL007` | warning | manual mirroring with `CGAffineTransform(scaleX: -1)` |
| `RTL008` | warning | storyboard `textAlignment="left"` / `"right"` |
| `RTL009` | warning | storyboard `semanticContentAttribute="force…"` |

`--fix` only rewrites `RTL001`–`RTL003`, where the replacement is mechanical. Directional
decisions (`RTL005`–`RTL009`) are reported and left to you.

Only real code is scanned. `//`, nested `/* */`, `"…"`, `"""…"""`, `#"…"#` and XML comments
are skipped, so `--fix` will not edit a log message or a test fixture.

## Install

```bash
git clone https://github.com/hfip/rtl-lint.git
cd rtl-lint
pipx install .
```

Python 3.9+, no dependencies. A pytest suite covers 44 cases.

## Usage

```bash
rtl-lint Sources/
rtl-lint --fix Sources/
rtl-lint --explain MyView.swift     # include the reasoning per finding
rtl-lint --list-rules
rtl-lint --format json .            # or --format github for annotations
```

Exit codes: `0` clean, `1` findings, `2` bad path or config.

## Skipping things

Inline, when a physical value is deliberate:

```swift
// rtl-lint:ignore
label.textAlignment = .left

// rtl-lint:ignore RTL001,RTL003
label.leftAnchor.constraint(equalTo: view.leftAnchor).isActive = true
```

Project-wide, in `.rtllint.json` (searched from the current directory upward, or passed
with `--config`):

```json
{
  "exclude": ["**/*+Generated.swift", "ThirdParty/**"],
  "ignore": ["RTL004"],
  "severity": { "RTL008": "error" }
}
```

`Pods/`, `Carthage/`, `.build/`, `DerivedData/` and `node_modules/` are always skipped, as
are files over 2 MB.

## In CI

```yaml
- uses: actions/checkout@v4
- uses: hfip/rtl-lint@v1
  with:
    paths: Sources
```

The action installs the tagged version and runs with `--format github`, so every finding
lands on the right line of the pull request diff. The repository dogfoods both `./` and
the published `@v1` tag on every push.

## What it will not catch

- Values computed at runtime (`alignment = userPreference`), and anything inside a string
  interpolation like `\(label.textAlignment)`.
- Truncation, Arabic line breaking, or a layout that mirrors correctly but reads badly.
- Semantic problems: an icon that should mirror but doesn't, a number that should stay LTR.

It is a grep with opinions, not a test suite. Run the app in Arabic.

## بالعربي

<div dir="rtl" align="right">

`ar.lproj` وترجمة النصوص ما يكفون. `.left` و`leftAnchor` و`forceLeftToRight` كلها تترجم
بنجاح وتشتغل تمام بالإنجليزي، وبالعربي يا إما ما تنعكس يا إما تعطّل الانعكاس للي تحتها.

الأداة تمسك التسع حالات هذي وتصلّح الآمن منها:

```bash
rtl-lint Sources/
rtl-lint --fix Sources/
```

وتشتغل على الـ PR مباشرة:

```yaml
- uses: hfip/rtl-lint@v1
```

ملاحظة: الأداة ما تقرأ التعليقات ولا النصوص، ولا تحلّل قيم وقت التشغيل. تظل تحتاج تفتح
التطبيق بالعربي وتشوف بعينك.

</div>

## License

MIT. See [LICENSE](LICENSE).
