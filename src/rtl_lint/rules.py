"""Built-in RTL rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional, Pattern, Tuple

SWIFT = "swift"
XML = "xml"

FixFn = Callable[[re.Match], str]


@dataclass(frozen=True)
class Rule:
    code: str
    message: str
    severity: str
    pattern: Pattern[str]
    kinds: Tuple[str, ...]
    fix: Optional[FixFn] = None
    hint: str = ""

    @property
    def fixable(self) -> bool:
        return self.fix is not None


def _mirror(match: re.Match) -> str:
    """Turn physical left/right tokens into their directional equivalents."""
    text = match.group(0)
    return (
        text.replace("leftAnchor", "leadingAnchor")
        .replace("rightAnchor", "trailingAnchor")
        .replace("leftMargin", "leadingMargin")
        .replace("rightMargin", "trailingMargin")
        .replace(".left", ".leading")
        .replace(".right", ".trailing")
    )


RULES: Tuple[Rule, ...] = (
    Rule(
        code="RTL001",
        message="Physical alignment does not mirror in right-to-left layouts.",
        severity="error",
        pattern=re.compile(
            r"\b(?:textAlignment|contentHorizontalAlignment|alignment)"
            r"\s*[:=]\s*\.(?:left|right)\b"
        ),
        kinds=(SWIFT,),
        fix=_mirror,
        hint="Use .leading / .trailing instead of .left / .right.",
    ),
    Rule(
        code="RTL002",
        message="Explicit NSTextAlignment / ContentHorizontalAlignment value is physical.",
        severity="error",
        pattern=re.compile(
            r"\b(?:NSTextAlignment|UIControl\.ContentHorizontalAlignment)\.(?:left|right)\b"
        ),
        kinds=(SWIFT,),
        fix=_mirror,
        hint="Use .leading / .trailing.",
    ),
    Rule(
        code="RTL003",
        message="Left/right anchors and layout attributes are physical and never mirror.",
        severity="error",
        pattern=re.compile(
            r"\b(?:left|right)(?:Anchor|Margin)\b"
            r"|\bNSLayoutConstraint\.Attribute\.(?:left|right)\b"
            r"|\battribute:\s*\.(?:left|right)\b"
        ),
        kinds=(SWIFT,),
        fix=_mirror,
        hint="Use leadingAnchor / trailingAnchor, or .leading / .trailing.",
    ),
    Rule(
        code="RTL004",
        message="UIEdgeInsets is physical; Arabic layouts need directional insets.",
        severity="warning",
        pattern=re.compile(r"\bUIEdgeInsets\s*\("),
        kinds=(SWIFT,),
        hint="Prefer NSDirectionalEdgeInsets(top:leading:bottom:trailing:).",
    ),
    Rule(
        code="RTL005",
        message="Forcing a layout direction disables mirroring for this view.",
        severity="warning",
        pattern=re.compile(r"\.force(?:LeftToRight|RightToLeft)\b"),
        kinds=(SWIFT,),
        hint="Use .unspecified unless the content is genuinely LTR-only (code, numbers).",
    ),
    Rule(
        code="RTL006",
        message="Manual layout-direction branching duplicates what Auto Layout does for free.",
        severity="warning",
        pattern=re.compile(r"\b(?:effective)?[uU]serInterfaceLayoutDirection\b"),
        kinds=(SWIFT,),
        hint="Prefer leading/trailing constraints and NSDirectionalEdgeInsets.",
    ),
    Rule(
        code="RTL007",
        message="Manual image mirroring bypasses the system's RTL handling.",
        severity="warning",
        pattern=re.compile(r"CGAffineTransform\s*\(\s*scaleX:\s*-1"),
        kinds=(SWIFT,),
        hint="Use imageFlippedForRightToLeftLayoutDirection() instead.",
    ),
    Rule(
        code="RTL008",
        message="Storyboard text alignment is pinned to a physical side.",
        severity="warning",
        pattern=re.compile(r'textAlignment="(?:left|right)"'),
        kinds=(XML,),
        hint='Set the alignment to "natural" in the storyboard.',
    ),
    Rule(
        code="RTL009",
        message="Storyboard forces a layout direction, so the screen will not mirror.",
        severity="warning",
        pattern=re.compile(r'semanticContentAttribute="force(?:Left|Right)To(?:Left|Right)"'),
        kinds=(XML,),
        hint="Remove the forced semantic content attribute.",
    ),
)

RULES_BY_CODE = {rule.code: rule for rule in RULES}
