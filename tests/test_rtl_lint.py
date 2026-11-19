import json

import pytest

from rtl_lint import Config, run
from rtl_lint.cli import main


def scan(tmp_path, source, name="View.swift"):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return run([str(path)], Config())


def codes(report):
    return [issue.code for issue in report.issues]


def test_detects_physical_alignment(tmp_path):
    report = scan(tmp_path, "label.textAlignment = .left\n")
    assert codes(report) == ["RTL001"]
    assert report.issues[0].fixable
    assert report.issues[0].column == 7


def test_detects_explicit_text_alignment_enum(tmp_path):
    report = scan(tmp_path, "label.textAlignment = NSTextAlignment.right\n")
    assert codes(report) == ["RTL002"]


def test_leading_and_trailing_are_clean(tmp_path):
    report = scan(
        tmp_path,
        "label.textAlignment = .leading\nlabel.textAlignment = .trailing\n",
    )
    assert report.issues == []


def test_detects_physical_anchors(tmp_path):
    report = scan(tmp_path, "label.leftAnchor.constraint(equalTo: view.leftAnchor)\n")
    assert [issue.code for issue in report.issues] == ["RTL003", "RTL003"]
    assert all(issue.replacement == "leadingAnchor" for issue in report.issues)


def test_detects_layout_attribute(tmp_path):
    report = scan(tmp_path, "NSLayoutConstraint(item: a, attribute: .right, relatedBy: .equal)\n")
    assert codes(report) == ["RTL003"]


def test_warns_about_physical_edge_insets(tmp_path):
    report = scan(tmp_path, "let insets = UIEdgeInsets(top: 8, left: 16, bottom: 8, right: 16)\n")
    assert codes(report) == ["RTL004"]
    assert report.warnings == 1


def test_warns_when_direction_is_forced(tmp_path):
    report = scan(tmp_path, "view.semanticContentAttribute = .forceLeftToRight\n")
    assert codes(report) == ["RTL005"]


def test_warns_on_manual_direction_branch(tmp_path):
    report = scan(tmp_path, "if view.effectiveUserInterfaceLayoutDirection == .rightToLeft {\n")
    assert codes(report) == ["RTL006"]


def test_warns_on_manual_image_mirroring(tmp_path):
    report = scan(tmp_path, "imageView.transform = CGAffineTransform(scaleX: -1, y: 1)\n")
    assert codes(report) == ["RTL007"]


def test_scans_storyboards(tmp_path):
    source = '<label textAlignment="right" id="abc"/>\n'
    report = scan(tmp_path, source, name="Main.storyboard")
    assert codes(report) == ["RTL008"]


def test_scans_forced_semantic_attribute_in_storyboard(tmp_path):
    source = '<view semanticContentAttribute="forceLeftToRight" id="abc"/>\n'
    report = scan(tmp_path, source, name="Main.xib")
    assert codes(report) == ["RTL009"]


def test_reports_each_occurrence_once(tmp_path):
    report = scan(tmp_path, "a.textAlignment = NSTextAlignment.left\n")
    assert codes(report) == ["RTL002"]


def test_inline_suppression_disables_all_rules(tmp_path):
    report = scan(tmp_path, "label.textAlignment = .left // rtl-lint:ignore\n")
    assert report.issues == []


def test_inline_suppression_can_target_one_rule(tmp_path):
    report = scan(
        tmp_path,
        "label.textAlignment = .left // rtl-lint:ignore RTL001\n"
        "label.leftAnchor.constraint(equalTo: view.leftAnchor)\n",
    )
    assert codes(report) == ["RTL003", "RTL003"]


def test_config_ignore_hides_rule(tmp_path):
    path = tmp_path / "View.swift"
    path.write_text("label.textAlignment = .left\n", encoding="utf-8")
    report = run([str(path)], Config(ignore=("RTL001",)))
    assert report.issues == []


def test_severity_can_be_overridden(tmp_path):
    report = scan(tmp_path, "label.textAlignment = .left\n")
    path = tmp_path / "View.swift"
    overridden = run([str(path)], Config(severity={"RTL001": "warning"}))
    assert overridden.issues[0].severity == "warning"
    assert report.issues[0].severity == "error"


def test_fix_rewrites_physical_values(tmp_path):
    path = tmp_path / "View.swift"
    path.write_text(
        "label.textAlignment = .right\nlabel.rightAnchor.constraint(equalTo: view.rightAnchor)\n",
        encoding="utf-8",
    )
    report = run([str(path)], Config(), fix=True)
    assert report.fixed == 3
    assert report.issues == []
    assert path.read_text(encoding="utf-8") == (
        "label.textAlignment = .trailing\n"
        "label.trailingAnchor.constraint(equalTo: view.trailingAnchor)\n"
    )


def test_fix_preserves_crlf(tmp_path):
    path = tmp_path / "View.swift"
    path.write_bytes(b"label.textAlignment = .left\r\nother.textAlignment = .left\r\n")
    report = run([str(path)], Config(), fix=True)
    assert report.fixed == 2
    assert (
        path.read_bytes() == b"label.textAlignment = .leading\r\nother.textAlignment = .leading\r\n"
    )


def test_fix_leaves_unfixable_issues(tmp_path):
    path = tmp_path / "View.swift"
    path.write_text("view.semanticContentAttribute = .forceLeftToRight\n", encoding="utf-8")
    report = run([str(path)], Config(), fix=True)
    assert report.fixed == 0
    assert codes(report) == ["RTL005"]


def test_skips_dependency_directories(tmp_path):
    pods = tmp_path / "Pods"
    pods.mkdir()
    (pods / "Noise.swift").write_text("label.textAlignment = .left\n", encoding="utf-8")
    app = tmp_path / "App"
    app.mkdir()
    (app / "Clean.swift").write_text("label.textAlignment = .leading\n", encoding="utf-8")
    report = run([str(tmp_path)], Config())
    assert report.files_scanned == 1
    assert report.issues == []


def test_ignores_binary_content(tmp_path):
    path = tmp_path / "Broken.swift"
    path.write_bytes(b"\x00\x01label.textAlignment = .left")
    report = run([str(path)], Config())
    assert report.issues == []


def test_exclude_globs(tmp_path):
    storyboard = tmp_path / "Main.storyboard"
    storyboard.write_text('<label textAlignment="right"/>\n', encoding="utf-8")
    report = run([str(tmp_path)], Config(exclude=("*.storyboard",)))
    assert report.issues == []


# --- CLI -------------------------------------------------------------------


def test_cli_text_output(tmp_path, capsys):
    path = tmp_path / "View.swift"
    path.write_text("label.textAlignment = .left\n", encoding="utf-8")
    assert main([str(path)]) == 1
    output = capsys.readouterr().out
    assert "RTL001" in output
    assert "1 issue(s)" in output


def test_cli_clean_exit_zero(tmp_path, capsys):
    path = tmp_path / "View.swift"
    path.write_text("label.textAlignment = .leading\n", encoding="utf-8")
    assert main([str(path)]) == 0
    assert "No RTL issues found" in capsys.readouterr().out


def test_cli_json_output(tmp_path, capsys):
    path = tmp_path / "View.swift"
    path.write_text("label.textAlignment = .left\n", encoding="utf-8")
    assert main(["--format", "json", str(path)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["issues"] == 1
    assert payload["issues"][0]["code"] == "RTL001"
    assert payload["issues"][0]["fixable"] is True


def test_cli_github_format(tmp_path, capsys):
    path = tmp_path / "View.swift"
    path.write_text("label.textAlignment = .left\n", encoding="utf-8")
    assert main(["--format", "github", str(path)]) == 1
    line = capsys.readouterr().out.strip()
    assert line.startswith("::error file=")
    assert "title=RTL001" in line


def test_cli_ignore_flag(tmp_path):
    path = tmp_path / "View.swift"
    path.write_text("label.textAlignment = .left\n", encoding="utf-8")
    assert main(["--ignore", "RTL001", str(path)]) == 0


def test_cli_list_rules(capsys):
    assert main(["--list-rules"]) == 0
    output = capsys.readouterr().out
    assert "RTL001" in output and "RTL009" in output


def test_cli_missing_path_exits_two(tmp_path):
    assert main([str(tmp_path / "nope")]) == 2


def test_cli_bad_config_exits_two(tmp_path):
    config = tmp_path / ".rtllint.json"
    config.write_text("{not json", encoding="utf-8")
    assert main(["--config", str(config), str(tmp_path)]) == 2


def test_cli_fix_exits_zero(tmp_path):
    path = tmp_path / "View.swift"
    path.write_text("label.textAlignment = .left\n", encoding="utf-8")
    assert main(["--fix", str(path)]) == 0
    assert ".leading" in path.read_text(encoding="utf-8")


def test_cli_quiet_hides_summary(tmp_path, capsys):
    path = tmp_path / "View.swift"
    path.write_text("label.textAlignment = .left\n", encoding="utf-8")
    assert main(["-q", str(path)]) == 1
    output = capsys.readouterr().out
    assert "RTL001" in output
    assert "issue(s) in" not in output


@pytest.mark.parametrize("name", ["Model.swift", "Main.storyboard", "Main.xib"])
def test_discover_supported_suffixes(tmp_path, name):
    from rtl_lint import discover

    (tmp_path / name).write_text("", encoding="utf-8")
    found = discover([str(tmp_path)])
    assert [path.name for path, _ in found] == [name]


def test_comments_are_ignored(tmp_path):
    report = scan(
        tmp_path,
        "// label.textAlignment = .left\n"
        "/// uses view.leftAnchor somewhere\n"
        "label.textAlignment = .leading\n",
    )
    assert report.issues == []


def test_string_literals_are_ignored(tmp_path):
    report = scan(tmp_path, 'let sample = "label.textAlignment = .left"\n')
    assert report.issues == []


def test_block_comments_are_ignored(tmp_path):
    report = scan(
        tmp_path,
        "/*\n  view.leftAnchor.constraint(equalTo: view.leftAnchor)\n*/\n",
    )
    assert report.issues == []


def test_multiline_strings_are_ignored(tmp_path):
    report = scan(
        tmp_path,
        'let sql = """\n  view.leftAnchor.constraint(equalTo: view.leftAnchor)\n"""\n',
    )
    assert report.issues == []


def test_raw_strings_are_ignored(tmp_path):
    report = scan(tmp_path, 'let sample = #"label.textAlignment = .left"#\n')
    assert report.issues == []


def test_code_before_an_inline_comment_is_still_reported(tmp_path):
    report = scan(tmp_path, "label.textAlignment = .left // temporary\n")
    assert [issue.code for issue in report.issues] == ["RTL001"]


def test_fix_never_rewrites_strings_or_comments(tmp_path):
    path = tmp_path / "View.swift"
    path.write_text(
        "// label.textAlignment = .left\n"
        'let sample = "label.textAlignment = .left"\n'
        "label.textAlignment = .left\n",
        encoding="utf-8",
    )
    report = run([str(path)], Config(), fix=True)
    assert report.fixed == 1
    assert path.read_text(encoding="utf-8") == (
        "// label.textAlignment = .left\n"
        'let sample = "label.textAlignment = .left"\n'
        "label.textAlignment = .leading\n"
    )


def test_storyboard_comments_are_ignored(tmp_path):
    report = scan(
        tmp_path,
        '<!-- <label textAlignment="right"/> -->\n',
        name="Main.storyboard",
    )
    assert report.issues == []


def test_config_is_found_from_a_subdirectory(tmp_path, monkeypatch):
    (tmp_path / ".rtllint.json").write_text('{"ignore": ["RTL001"]}', encoding="utf-8")
    nested = tmp_path / "App" / "Feature"
    nested.mkdir(parents=True)
    path = nested / "View.swift"
    path.write_text("label.textAlignment = .left\n", encoding="utf-8")

    monkeypatch.chdir(nested)
    report = run([str(path)], Config.load())
    assert report.issues == []
