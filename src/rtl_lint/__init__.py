"""rtl-lint - catch RTL layout bugs in Swift and storyboards."""

from .rules import RULES, Rule
from .scanner import Config, Issue, ScanReport, apply_fixes, discover, run, scan_file

__version__ = "0.2.0"

__all__ = [
    "RULES",
    "Config",
    "Issue",
    "Rule",
    "ScanReport",
    "apply_fixes",
    "discover",
    "run",
    "scan_file",
    "__version__",
]
