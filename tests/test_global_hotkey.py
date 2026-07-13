from app.main_window import MainAppWindow
from app.utils.global_hotkey import MOD_ALT, MOD_CONTROL, parse_shortcut


def test_parse_shortcut_accepts_modified_key():
    modifiers, key = parse_shortcut("Ctrl+Alt+K")
    assert modifiers == MOD_CONTROL | MOD_ALT
    assert key == ord("K")


def test_parse_shortcut_rejects_unmodified_or_unknown_key():
    assert parse_shortcut("U") is None
    assert parse_shortcut("Ctrl+PageDown") is None


class _FakeHotkey:
    def __init__(self):
        self.calls = []

    def register(self, shortcut):
        self.calls.append(shortcut)
        return shortcut == "Ctrl+U"


def test_conflicting_shortcut_restores_previous_registration():
    host = type("Host", (), {})()
    host.global_hotkey = _FakeHotkey()
    host._applied_shortcut = "Ctrl+U"
    host.hotkey_registered = True

    assert MainAppWindow.try_register_shortcut(host, "Ctrl+Alt+K") is False
    assert host.global_hotkey.calls == ["Ctrl+Alt+K", "Ctrl+U"]
    assert host.hotkey_registered is True
    assert host._applied_shortcut == "Ctrl+U"
