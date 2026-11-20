import json
import subprocess

from rtl_lint.cli import main
from rtl_lint.migrate import MigrationPlan, build_markdown, find_hardcoded_strings
from rtl_lint.scanner import Config, run

SOURCE = """import UIKit

final class ProfileView: UIView {
    func setup() {
        titleLabel.textAlignment = .left
        titleLabel.leftAnchor.constraint(equalTo: leftAnchor).isActive = true
        avatarView.semanticContentAttribute = .forceLeftToRight
    }
}
"""


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    )


def make_repo(tmp_path, files):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.com")
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")


def test_build_markdown_lists_both_sections(tmp_path):
    path = tmp_path / "View.swift"
    path.write_text(SOURCE, encoding="utf-8")
    scan = run([str(path)], Config())
    plan = MigrationPlan(files_scanned=scan.files_scanned, issues=scan.issues)
    text = build_markdown(plan, tmp_path)

    assert "# RTL migration plan" in text
    assert "## 1. Mechanical fixes (3)" in text
    assert "## 2. Needs a decision (1)" in text
    assert "RTL003" in text
    assert "## Checklist" in text


def test_markdown_mentions_user_facing_literals(tmp_path):
    path = tmp_path / "View.swift"
    path.write_text('Text("Hello")\nButton("Save") {}\n', encoding="utf-8")
    plan = MigrationPlan(
        files_scanned=1, issues=[], strings=find_hardcoded_strings([str(path)], Config())
    )
    text = build_markdown(plan, tmp_path)
    assert "User-facing literals (2)" in text
    assert "| View.swift | 2 |" in text


def test_find_hardcoded_strings_skips_comments_and_numbers(tmp_path):
    path = tmp_path / "View.swift"
    path.write_text(
        '// Text("commented out")\nText("Hello")\nText("123")\nText(verbatim: "raw")\n',
        encoding="utf-8",
    )
    found = find_hardcoded_strings([str(path)], Config())
    assert [item.text for item in found] == ["Hello"]


def test_migrate_without_apply_writes_only_the_report(tmp_path, monkeypatch, capsys):
    make_repo(tmp_path, {"Sources/View.swift": SOURCE})
    monkeypatch.chdir(tmp_path)

    assert main(["migrate", "Sources"]) == 0
    assert (tmp_path / "RTL-MIGRATION.md").exists()
    assert ".left" in (tmp_path / "Sources/View.swift").read_text(encoding="utf-8")
    assert "Nothing was changed" in capsys.readouterr().out
    assert git(tmp_path, "branch", "--list", "rtl-prep").stdout.strip() == ""


def test_migrate_apply_creates_branch_and_commits(tmp_path, monkeypatch):
    make_repo(tmp_path, {"Sources/View.swift": SOURCE})
    monkeypatch.chdir(tmp_path)

    assert main(["migrate", "Sources", "--apply"]) == 0

    branches = git(tmp_path, "branch", "--list", "rtl-prep").stdout
    assert "rtl-prep" in branches

    current = git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    assert current == "rtl-prep"

    log = git(tmp_path, "log", "--oneline").stdout.splitlines()
    assert len(log) >= 3
    assert any("alignment" in line for line in log)
    assert any("migration plan" in line for line in log)

    fixed = git(tmp_path, "show", "rtl-prep:Sources/View.swift").stdout
    assert ".leading" in fixed
    assert "leadingAnchor" in fixed
    assert ".left" not in fixed.replace(".leading", "")


def test_migrate_refuses_dirty_tree(tmp_path, monkeypatch, capsys):
    make_repo(tmp_path, {"Sources/View.swift": SOURCE})
    (tmp_path / "Sources/View.swift").write_text("changed", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["migrate", "Sources", "--apply"]) == 2
    assert "not clean" in capsys.readouterr().err


def test_migrate_force_accepts_dirty_tree(tmp_path, monkeypatch):
    make_repo(tmp_path, {"Sources/View.swift": SOURCE})
    (tmp_path / "notes.txt").write_text("draft", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["migrate", "Sources", "--apply", "--force", "--branch", "rtl-2"]) == 0
    assert "rtl-2" in git(tmp_path, "branch", "--list", "rtl-2").stdout


def test_migrate_rejects_existing_branch(tmp_path, monkeypatch, capsys):
    make_repo(tmp_path, {"Sources/View.swift": SOURCE})
    git(tmp_path, "branch", "rtl-prep")
    monkeypatch.chdir(tmp_path)

    assert main(["migrate", "Sources", "--apply"]) == 2
    assert "already exists" in capsys.readouterr().err


def test_migrate_apply_needs_a_repository(tmp_path, monkeypatch, capsys):
    (tmp_path / "View.swift").write_text(SOURCE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["migrate", ".", "--apply"]) == 2
    assert "needs a git repository" in capsys.readouterr().err


def test_migrate_json_summary(tmp_path, monkeypatch, capsys):
    make_repo(tmp_path, {"Sources/View.swift": SOURCE})
    monkeypatch.chdir(tmp_path)

    assert main(["migrate", "Sources", "--json", "--no-report"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mechanical"] == 3
    assert payload["decisions"] == 1
    assert "RTL005" in payload["rules"]


def test_migrate_no_report_flag(tmp_path, monkeypatch):
    make_repo(tmp_path, {"Sources/View.swift": SOURCE})
    monkeypatch.chdir(tmp_path)

    assert main(["migrate", "Sources", "--no-report"]) == 0
    assert not (tmp_path / "RTL-MIGRATION.md").exists()


def test_migrate_no_branch_applies_in_place(tmp_path, monkeypatch):
    make_repo(tmp_path, {"Sources/View.swift": SOURCE})
    monkeypatch.chdir(tmp_path)

    assert main(["migrate", "Sources", "--apply", "--no-branch"]) == 0
    assert git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"
    assert ".leading" in (tmp_path / "Sources/View.swift").read_text(encoding="utf-8")
