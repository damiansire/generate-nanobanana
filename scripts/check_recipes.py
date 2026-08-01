#!/usr/bin/env python3
"""Integrity checks for the recipe files — the cheapest gate a Markdown skill can have.

None of these need an API key or a paid call. They cover the failure classes that
have actually bitten this repo:

1. compile      — every ```python block in models/*.md and SKILL.md parses.
2. call-shape   — every `Part.from_text(...)` uses the keyword arg `text=` (the exact
                  bug that once broke all image recipes; py_compile alone missed it).
3. paths        — every recipe path named in SKILL.md's routing table exists.
4. model-ids    — every backticked model id anywhere in the repo is one the recipe
                  tables declare (catches drift in BOTH directions, and unknown ids).
5. cost         — the per-second video price is stated identically in the SKILL.md
                  cost table and the video recipe (the declared "they must agree").
6. sidecar      — every examples/*.json validates against the sidecar contract.

Exit 0 if all pass, 1 otherwise. Run: python scripts/check_recipes.py
"""
from __future__ import annotations

import ast
import json
import os
import py_compile
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Free names the snippets reference; stubbed so compilation reflects syntax, not context.
STUB = (
    "prompt = 'x'\nreference_images = []\nimage_path = None\noutput_path = 'o'\n"
    "seed = 0\nset_roots = []\nimage_bytes = b''\next = '.png'\nbase_name = 'n'\n"
    "out_dir = '.'\nsidecar = {}\nmedia_bytes = b''\nduration_seconds = 4\n"
    "created_iso = ''\napproval = {'quoted_cost': '$0'}\n"
)
MD_WITH_PY = None  # lazily computed list of (path, blocks)


def _python_blocks():
    global MD_WITH_PY
    if MD_WITH_PY is None:
        MD_WITH_PY = []
        for md in sorted((ROOT / "models").glob("*.md")) + [ROOT / "SKILL.md"]:
            blocks = re.findall(r"```python\n(.*?)```", md.read_text(encoding="utf-8"), re.S)
            MD_WITH_PY.append((md, blocks))
    return MD_WITH_PY


def compile_blocks() -> list:
    errors = []
    for md, blocks in _python_blocks():
        for i, block in enumerate(blocks):
            tmp = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8")
            try:
                tmp.write(STUB + block)
                tmp.close()
                py_compile.compile(tmp.name, doraise=True)
            except py_compile.PyCompileError as e:
                errors.append(f"{md.name}[block {i}] does not compile: {e.msg}")
            finally:
                os.unlink(tmp.name)
                pyc = Path(tmp.name + "c")
                if pyc.exists():
                    os.unlink(pyc)  # py_compile can drop a sibling .pyc
    return errors


def check_call_shapes() -> list:
    """Part.from_text must be called with the keyword arg `text=`, never positionally.

    This is the bug class that shipped once and broke every image recipe; syntax
    compiled fine, so only an AST check catches it.
    """
    errors = []
    for md, blocks in _python_blocks():
        for i, block in enumerate(blocks):
            try:
                tree = ast.parse(STUB + block)
            except SyntaxError:
                continue  # compile_blocks already reports it
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "from_text"
                ):
                    if node.args or not any(kw.arg == "text" for kw in node.keywords):
                        errors.append(
                            f"{md.name}[block {i}]: Part.from_text must use the keyword arg text="
                        )
    return errors


def check_recipe_paths() -> list:
    errors = []
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    for rel in re.findall(r"`(models/[\w.-]+\.md)`", skill):
        if not (ROOT / rel).is_file():
            errors.append(f"routing table points at missing recipe: {rel}")
    return errors


def _canonical_model_ids() -> set:
    ids = set()
    for md in (ROOT / "models").glob("*.md"):
        text = md.read_text(encoding="utf-8")
        for m in re.findall(r"\|\s*Model ID\s*\|\s*`([^`]+)`\s*\|", text):
            ids.add(m)
    return ids


def check_model_ids() -> list:
    """Every backticked model id in the repo must be one the recipe tables declare.

    Anchoring on the declared set and requiring exact membership catches drift in
    both directions (a stale `-preview` left behind, OR a recipe not updated) and
    any unknown id — unlike a one-directional 'is this a suffix-variant' heuristic.
    """
    errors = []
    canonical = _canonical_model_ids()
    files = list(ROOT.glob("*.md")) + list((ROOT / "models").glob("*.md"))
    # A backticked token that looks like a Gemini media model id (hyphens included).
    token = re.compile(r"`(gemini-[\w.-]*(?:image|flash)[\w.-]*)`")
    for path in files:
        for m in set(token.findall(path.read_text(encoding="utf-8"))):
            if m not in canonical:
                errors.append(
                    f"{path.name}: model id `{m}` is not one the recipe tables declare "
                    f"({', '.join(sorted(canonical))})"
                )
    return errors


def check_cost_invariant() -> list:
    """The per-second video price must match between the SKILL.md table and the recipe."""
    errors = []
    price = re.compile(r"\$0\.10 per second")
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    recipe = (ROOT / "models" / "gemini-omni-flash.md").read_text(encoding="utf-8")
    if not price.search(skill):
        errors.append("SKILL.md cost table is missing the '$0.10 per second' video price")
    if not price.search(recipe):
        errors.append("gemini-omni-flash.md is missing the '$0.10 per second' video price")
    return errors


def check_sidecars() -> list:
    """Every examples/*.json must satisfy the sidecar contract."""
    errors = []
    examples = ROOT / "examples"
    if not examples.is_dir():
        return errors
    for jf in examples.glob("*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"examples/{jf.name}: invalid JSON ({e})")
            continue
        for key in ("model", "prompt", "params"):
            if key not in data:
                errors.append(f"examples/{jf.name}: sidecar is missing required key '{key}'")
        if "approved_by_user" in data:
            errors.append(
                f"examples/{jf.name}: uses the retired 'approved_by_user' flag; "
                "use an 'approval' block with quoted_cost/quoted_at/approved_text"
            )
        if "approval" in data:
            for key in ("quoted_cost", "quoted_at", "approved_text"):
                if key not in data["approval"]:
                    errors.append(f"examples/{jf.name}: approval block missing '{key}'")
    return errors


CHECKS = [
    compile_blocks,
    check_call_shapes,
    check_recipe_paths,
    check_model_ids,
    check_cost_invariant,
    check_sidecars,
]


def main() -> int:
    all_errors = []
    for check in CHECKS:
        all_errors.extend(check())
    if all_errors:
        print("FAIL:")
        for e in all_errors:
            print(f"  - {e}")
        return 1
    print("OK: snippets compile & call the SDK correctly, paths resolve, "
          "model ids and video price are consistent, sidecars valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
