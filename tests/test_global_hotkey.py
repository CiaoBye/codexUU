from app.utils.global_hotkey import MOD_ALT, MOD_CONTROL, parse_shortcut


def test_parse_shortcut_accepts_modified_key():
    modifiers, key = parse_shortcut("Ctrl+Alt+K")
    assert modifiers == MOD_CONTROL | MOD_ALT
    assert key == ord("K")


def test_parse_shortcut_rejects_unmodified_or_unknown_key():
    assert parse_shortcut("U") is None
    assert parse_shortcut("Ctrl+PageDown") is None
