import pytest

from SigProfilerExtractor.web import native_dialog

# Titles that would break out of a string literal if they were ever written
# into AppleScript or PowerShell source.
HOSTILE_TITLES = [
    'Pick "x") & (do shell script "touch /tmp/pwned") & ("',
    "Pick $(Start-Process calc)",
    'Pick"; Remove-Item -Recurse C:\\ ; "',
    "Pick `whoami` ' \" \\",
]


class _FakeCompleted:
    def __init__(self, stdout):
        self.stdout = stdout


@pytest.fixture
def capture(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append({"args": args, "env": kwargs.get("env")})
        return _FakeCompleted("/chosen/path\n")

    monkeypatch.setattr(native_dialog.subprocess, "run", fake_run)
    return calls


def test_choose_rejects_unknown_kind():
    with pytest.raises(native_dialog.DialogError):
        native_dialog.choose("city")


@pytest.mark.parametrize("kind", ["folder", "file"])
def test_macos_passes_the_title_as_an_argument_not_script(monkeypatch, capture, kind):
    monkeypatch.setattr(native_dialog.sys, "platform", "darwin")

    assert native_dialog.choose(kind, title="Pick input") == "/chosen/path"

    args = capture[0]["args"]
    assert args[0] == "osascript"
    assert args[-1] == "Pick input"
    script = " ".join(args[1:-1])
    assert f"choose {kind}" in script
    assert "Pick input" not in script


@pytest.mark.parametrize("title", HOSTILE_TITLES)
def test_macos_script_text_never_changes_with_the_title(monkeypatch, capture, title):
    monkeypatch.setattr(native_dialog.sys, "platform", "darwin")

    native_dialog.choose("folder", title="plain")
    native_dialog.choose("folder", title=title)

    plain, hostile = capture[0]["args"], capture[1]["args"]
    assert plain[:-1] == hostile[:-1]
    assert hostile[-1] == title


@pytest.mark.parametrize("title", HOSTILE_TITLES)
def test_windows_passes_the_title_through_the_environment(monkeypatch, capture, title):
    monkeypatch.setattr(native_dialog.sys, "platform", "win32")

    native_dialog.choose("folder", title=title)

    call = capture[0]
    assert call["args"][0] == "powershell"
    assert title not in " ".join(call["args"])
    assert "$env:SPE_DIALOG_TITLE" in call["args"][-1]
    assert call["env"]["SPE_DIALOG_TITLE"] == title


def test_windows_file_dialog_uses_open_file_dialog(monkeypatch, capture):
    monkeypatch.setattr(native_dialog.sys, "platform", "win32")

    native_dialog.choose("file", title="Pick a BED file")

    assert "OpenFileDialog" in capture[0]["args"][-1]


def test_cancelled_dialog_returns_none(monkeypatch):
    monkeypatch.setattr(native_dialog.sys, "platform", "darwin")
    monkeypatch.setattr(native_dialog.subprocess, "run", lambda args, **kwargs: _FakeCompleted(""))

    assert native_dialog.choose("folder") is None


def test_subprocess_failure_raises_dialog_error(monkeypatch):
    monkeypatch.setattr(native_dialog.sys, "platform", "darwin")

    def fake_run(args, **kwargs):
        raise OSError("osascript not found")

    monkeypatch.setattr(native_dialog.subprocess, "run", fake_run)

    with pytest.raises(native_dialog.DialogError):
        native_dialog.choose("folder")


def test_linux_prefers_zenity_and_passes_arguments_without_a_shell(monkeypatch, capture):
    monkeypatch.setattr(native_dialog.sys, "platform", "linux")
    monkeypatch.setattr(native_dialog.shutil, "which", lambda name: "/usr/bin/zenity" if name == "zenity" else None)

    native_dialog.choose("folder", title=HOSTILE_TITLES[0])

    args = capture[0]["args"]
    assert args[0] == "zenity"
    assert "--directory" in args
    assert f"--title={HOSTILE_TITLES[0]}" in args


def test_linux_falls_back_to_kdialog_when_zenity_absent(monkeypatch, capture):
    monkeypatch.setattr(native_dialog.sys, "platform", "linux")
    monkeypatch.setattr(native_dialog.shutil, "which", lambda name: "/usr/bin/kdialog" if name == "kdialog" else None)

    native_dialog.choose("file", title="Pick")

    args = capture[0]["args"]
    assert args[0] == "kdialog"
    assert "--getopenfilename" in args
