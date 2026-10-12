"""Codex's own image generation stays on in Ducky, and its pictures go to the chat."""
import importlib.util
import os
import sys
import time
import types
from pathlib import Path


def _adapter():
    spec = importlib.util.spec_from_file_location("_pictures_adapter", Path(__file__).with_name("codex_adapter.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_image_generation_is_not_switched_off():
    # Oct 11 2026: switched off with Codex's shell and browser, so "make me a picture" in a
    # Codex chat could not work. It runs nothing and edits nothing.
    flags = _adapter().DUCKY_ONLY_FLAGS
    assert "features.image_generation=false" not in flags
    assert "features.shell_tool=false" in flags  # Codex's own shell stays off


def test_pictures_codex_saved_this_turn_go_to_the_chat(tmp_path, monkeypatch):
    kept = []
    fake = types.ModuleType("frontend.ui_web.generated_images")
    fake.note_image_file = lambda path, conv_id, gateway: kept.append((Path(path).name, conv_id, gateway)) or {"ok": True}
    monkeypatch.setitem(sys.modules, "frontend.ui_web.generated_images", fake)
    folder = tmp_path / "generated_images" / "thread-1"
    folder.mkdir(parents=True)
    old = folder / "exec-old.png"
    old.write_bytes(b"png")
    started = time.time()
    os.utime(old, (started - 60, started - 60))  # an earlier turn's picture
    (folder / "exec-new.png").write_bytes(b"png")
    (folder / "notes.txt").write_text("not a picture")

    keep = _adapter()._keep_codex_pictures
    assert keep(tmp_path, "thread-1", "chat-1", started) == 1
    assert kept == [("exec-new.png", "chat-1", "codex")]
    assert keep(tmp_path, "", "chat-1", started) == 0  # no thread yet: nothing to look at
    assert keep(tmp_path, "thread-2", "chat-1", started) == 0  # nothing generated
