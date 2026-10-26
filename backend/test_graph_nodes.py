from __future__ import annotations

import json
from pathlib import Path


def test_plugin_declares_nodes():
    data = json.loads((Path(__file__).resolve().parent.parent / "plugin.json").read_text(encoding="utf-8"))
    ids = {n["id"] for n in data["contributes"]["automations"]["nodes"]}
    assert ids == {"openai.complete", "openai.image"}
    model = next(f for n in data["contributes"]["automations"]["nodes"] if n["id"] == "openai.complete" for f in n["config_fields"] if f["id"] == "model")
    assert model["type"] == "model"


def _load():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "openai_graph_test", Path(__file__).with_name("graph_nodes.py")
    )
    graph_nodes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(graph_nodes)
    return graph_nodes


def test_image_node_takes_a_reference_picture(tmp_path, monkeypatch):
    data = json.loads((Path(__file__).resolve().parent.parent / "plugin.json").read_text(encoding="utf-8"))
    node = next(n for n in data["contributes"]["automations"]["nodes"] if n["id"] == "openai.image")
    assert node["accepts_image"] is True  # core lists it on Edit Image
    assert any(f["id"] == "image" for f in node["config_fields"])

    graph_nodes = _load()
    png = b"\x89PNG\r\n\x1a\n"
    reply = {"data": [{"b64_json": __import__("base64").b64encode(png).decode()}]}
    calls = []
    monkeypatch.setattr(graph_nodes, "_images_http", lambda body, key: calls.append(("generate", body, None)) or reply)
    monkeypatch.setattr(graph_nodes, "_edits_http", lambda body, image, key: calls.append(("edit", body, image)) or reply)
    monkeypatch.setattr(graph_nodes, "_secret", lambda *_a, **_k: "sk-test")
    monkeypatch.setattr(graph_nodes, "_persist", lambda raw, **kw: {"path": str(tmp_path / "out.png")})
    front = tmp_path / "front.png"
    front.write_bytes(png)

    assert graph_nodes.handle_image({"config": {"prompt": "side view", "image": str(front)}})["ok"] is True
    assert calls[-1] == ("edit", {"model": "gpt-image-1", "prompt": "side view", "n": 1, "size": "1024x1024"}, front)
    assert graph_nodes.handle_image({"config": {"prompt": "side view"}, "payload": {"image": {"path": str(front)}}})["ok"] is True
    assert calls[-1][0] == "edit"
    assert graph_nodes.handle_image({"config": {"prompt": "a duck"}})["ok"] is True
    assert calls[-1] == ("generate", {"model": "gpt-image-1", "prompt": "a duck", "n": 1, "size": "1024x1024"}, None)
    missing = graph_nodes.handle_image({"config": {"prompt": "x", "image": str(tmp_path / "nope.png")}})
    assert missing["ok"] is False and "not found" in missing["error"]
    assert len(calls) == 3


def test_edits_http_sends_the_picture_as_multipart(tmp_path, monkeypatch):
    graph_nodes = _load()
    front = tmp_path / "front.png"
    front.write_bytes(b"\x89PNGdata")
    sent = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"data": []}'

    def _open(req, timeout=0):
        sent["url"], sent["data"], sent["ct"] = req.full_url, req.data, req.get_header("Content-type")
        return _Resp()

    monkeypatch.setattr(graph_nodes.urllib.request, "urlopen", _open)
    graph_nodes._edits_http({"model": "gpt-image-1", "prompt": "side view"}, front, "sk")
    assert sent["url"].endswith("/v1/images/edits")
    assert sent["ct"].startswith("multipart/form-data; boundary=")
    assert b'name="image"; filename="front.png"' in sent["data"] and b"\x89PNGdata" in sent["data"]
    assert b'name="prompt"\r\n\r\nside view' in sent["data"]


def test_image_writes_png(tmp_path, monkeypatch):
    graph_nodes = _load()

    png = b"\x89PNG\r\n\x1a\n"
    monkeypatch.setattr(graph_nodes, "_images_http", lambda body, key: {"data": [{"b64_json": __import__("base64").b64encode(png).decode()}]})
    monkeypatch.setattr(graph_nodes, "_secret", lambda *_a, **_k: "sk-test")

    saved = {}

    def _save(raw, **kw):
        dest = tmp_path / "out.png"
        dest.write_bytes(raw)
        saved["raw"] = raw
        return {"ok": True, "path": str(dest), "name": "out.png"}

    monkeypatch.setattr(graph_nodes, "_persist", _save)
    out = graph_nodes.handle_image({"config": {"prompt": "a duck"}, "payload": {}})
    assert out["ok"] is True
    assert Path(out["path"]).is_file()
    assert saved["raw"].startswith(b"\x89PNG")
    assert "brainrot" not in Path(graph_nodes.__file__).read_text(encoding="utf-8")
