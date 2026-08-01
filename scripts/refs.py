"""Single source of truth for turning a reference-image path into safe bytes.

Every reference is uploaded to the Gemini API, so a stray path must fail loudly
instead of quietly shipping a local file to a third party. The recipes import
this instead of each carrying their own copy, and the tests in tests/test_refs.py
exercise it. This module is pure: no SDK, no network, so CI can run it for free.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

ALLOWED_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
MAX_REF_BYTES = 20 * 1024 * 1024  # every reference is uploaded to the API — cap it
REFS_ROOT = (Path.home() / "generations" / "refs").resolve()


def _within(p: Path, root: Path) -> bool:
    return p == root or root in p.parents


def resolve_reference(ref_path, allowed_roots: Optional[Iterable] = None):
    """Resolve one reference path to ``(bytes, mime_type)`` or raise ``ValueError``.

    Containment holds for EVERY path, absolute or relative — there is no branch that
    skips the check. A relative path resolves under ``REFS_ROOT``; an absolute path is
    accepted only when it lands inside one of ``allowed_roots``. ``.resolve()`` follows
    symlinks, so a link pointing out of the roots resolves outside and is rejected.

    allowed_roots: directories a reference may live under, on top of ``REFS_ROOT``.
    Pass the resolved roots of the linked sets the user registered (from ``sets.json``)
    so an absolute path is honored only when it belongs to a folder they set up — never
    an arbitrary absolute path pulled from task text.
    """
    roots = [REFS_ROOT]
    for r in allowed_roots or []:
        roots.append(Path(r).expanduser().resolve())

    raw = Path(ref_path)
    base = raw if raw.is_absolute() else (REFS_ROOT / raw)
    p = base.resolve()

    if not any(_within(p, root) for root in roots):
        raise ValueError(
            f"reference is outside the refs library and every registered set: {ref_path}"
        )
    mime = ALLOWED_TYPES.get(p.suffix.lower())
    if mime is None:
        raise ValueError(f"reference is not an allowed image type (png/jpg/webp): {ref_path}")
    if not p.is_file():
        raise ValueError(f"reference is not a file: {ref_path}")
    if p.stat().st_size > MAX_REF_BYTES:
        raise ValueError(f"reference exceeds {MAX_REF_BYTES} bytes: {ref_path}")

    return p.read_bytes(), mime
