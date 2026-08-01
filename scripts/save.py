"""Write a generated media file and its JSON sidecar together, never overwriting.

Shared by the recipes and documented in SKILL.md, so "the file and its sidecar are
one atomic step" holds everywhere — image and video alike, not just where someone
remembered to inline it. Pure: no SDK, no network, so the tests run for free.
"""
from __future__ import annotations

import json
from pathlib import Path


def save_generation(media_bytes, ext, base_name, out_dir, sidecar):
    """Write media + sidecar with the same basename; add a numeric suffix rather than
    clobber an existing pair (two generations in the same second never overwrite an
    audit record). Returns the media path."""
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    stem, n = base_name, 1
    while (out / f"{stem}{ext}").exists() or (out / f"{stem}.json").exists():
        stem = f"{base_name}_{n}"
        n += 1
    (out / f"{stem}{ext}").write_bytes(media_bytes)
    (out / f"{stem}.json").write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    return out / f"{stem}{ext}"
