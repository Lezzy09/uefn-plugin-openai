"""OpenAI Automations + Pipelines tiles. No BrainRot imports."""

from __future__ import annotations

import base64
import json
import mimetypes
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

NODES = ("openai.complete", "openai.image")


def _secret(name: str) -> str:
    from backend.agent.secrets import get_key

    return get_key(name) or ""


def _persist(raw: bytes, *, prompt: str, gateway: str, model: str) -> dict[str, Any]:
    from frontend.ui_web.generated_images import save_generated_image

    return save_generated_image(raw, prompt=prompt, gateway=gateway, model=model)


def _pair(ctx: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    cfg = ctx.get("config") if isinstance(ctx.get("config"), dict) else {}
    payload = ctx.get("payload") if isinstance(ctx.get("payload"), dict) else {}
    return cfg, payload


def handle_complete(ctx: dict[str, Any]) -> dict[str, Any]:
    cfg, payload = _pair(ctx)
    prompt = str(cfg.get("prompt") or payload.get("prompt") or payload.get("text") or "")
    model = str(cfg.get("model") or payload.get("model") or "")
    from backend.automations.llm_complete import complete_prompt

    return complete_prompt("openai", prompt, model)


def _images_http(body: dict[str, Any], key: str) -> dict[str, Any]:
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _edits_http(body: dict[str, Any], image: Path, key: str) -> dict[str, Any]:
    """/images/edits: the same ask, starting from a reference picture (multipart)."""
    boundary = uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8") for k, v in body.items()]
    mime = mimetypes.guess_type(image.name)[0] or "image/png"
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{image.name}"\r\n'
                 f"Content-Type: {mime}\r\n\r\n".encode("utf-8") + image.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/edits",
        data=b"".join(parts),
        headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _image_path(value: Any) -> str:
    """A picture's path from a path or a file ref ({path})."""
    raw = value.get("path") if isinstance(value, dict) else value
    return str(raw or "").strip()


def handle_image(ctx: dict[str, Any]) -> dict[str, Any]:
    cfg, payload = _pair(ctx)
    prompt = str(cfg.get("prompt") or payload.get("prompt") or "").strip()
    if not prompt:
        return {"ok": False, "error": "prompt required"}
    model = str(cfg.get("model") or "gpt-image-1")
    size = str(cfg.get("size") or "1024x1024")
    quality = str(cfg.get("quality") or "")
    key = _secret("openai")
    if not key:
        return {"ok": False, "error": "OpenAI key required"}
    body: dict[str, Any] = {"model": model, "prompt": prompt, "n": 1, "size": size}
    if quality:
        body["quality"] = quality
    # A reference picture (Edit Image: the same character from the side) makes it an edit.
    image = _image_path(cfg.get("image") or payload.get("image"))
    if image and not Path(image).is_file():
        return {"ok": False, "error": f"reference picture not found: {image}"}
    try:
        data = _edits_http(body, Path(image), key) if image else _images_http(body, key)
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"images API {exc.code}"}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    item = (data.get("data") or [{}])[0]
    raw = b""
    if item.get("b64_json"):
        raw = base64.b64decode(item["b64_json"])
    elif item.get("url"):
        raw = urllib.request.urlopen(item["url"], timeout=60).read()
    if not raw:
        return {"ok": False, "error": "no image bytes"}
    saved = _persist(raw, prompt=prompt, gateway="openai", model=model)
    path = str(saved.get("path") or "")
    return {
        "ok": True,
        "files": [{"path": path, "name": saved.get("name") or "image.png"}],
        "path": path,
        "prompt": prompt,
    }


def register_nodes(api: Any) -> None:
    if not hasattr(api, "register_pipeline_node"):
        return
    api.register_pipeline_node("openai.complete", handle_complete)
    api.register_pipeline_node("openai.image", handle_image)
