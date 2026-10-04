from PySide6.QtGui import QAction

from deeplabeling.ui.settings_ui import (
    LAST_SOURCE,
    RECENT,
    RECENT_MAX,
    SHOW_LABELS,
    Saver,
    bind_toggle,
    global_settings,
    remember_source,
)


def test_global_settings_live_in_the_state_folder(state_dir):
    file, _ = global_settings()
    assert file.path == state_dir / "settings.json"


def test_remembering_a_source_puts_it_first_once():
    _, settings = global_settings()
    remember_source(settings, "/a.yaml", None)
    remember_source(settings, "/b", "/b_labels")
    remember_source(settings, "/a.yaml", None)
    assert settings.get(LAST_SOURCE) == {"source": "/a.yaml", "labels": None}
    assert settings.get(RECENT) == [{"source": "/a.yaml", "labels": None},
                                    {"source": "/b", "labels": "/b_labels"}]


def test_the_recent_list_is_capped():
    _, settings = global_settings()
    for i in range(RECENT_MAX + 3):
        remember_source(settings, f"/{i}.yaml", None)
    assert len(settings.get(RECENT)) == RECENT_MAX


def test_the_saver_waits_then_saves_once(qtbot):
    saved = []
    saver = Saver(lambda: saved.append(1), delay_ms=20)
    saver.schedule()
    saver.schedule()
    assert saved == [] and saver.pending
    qtbot.waitUntil(lambda: saved == [1], timeout=2000)
    saver.schedule()
    saver.flush()
    assert saved == [1, 1] and not saver.pending


def test_a_toggle_is_seeded_from_the_setting_and_writes_back(qtbot):
    file, settings = global_settings()
    settings.set(SHOW_LABELS, False)
    action, seen = QAction(), []
    bind_toggle(action, settings, SHOW_LABELS, seen.append)
    assert not action.isChecked()
    action.setChecked(True)
    assert settings.get(SHOW_LABELS) is True and seen == [True] and file.dirty
