"""Marketplace SKILL.md description contract.

Every shipped skill description must be <=250 chars (ZCode truncates at 250)
with a self-contained first sentence (trigger phrase) — per GC-DIST SPEC §1.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted((ROOT / "skills").glob("*/SKILL.md"))
MAX_LEN = 250


def test_every_skill_present():
    names = {p.parent.name for p in SKILLS}
    assert {"kinocut", "kinocut-repurpose", "mcp-video"} <= names


def test_description_length_contract():
    violators = []
    for p in SKILLS:
        text = p.read_text(encoding="utf-8")
        m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
        assert m, f"{p}: no description frontmatter"
        desc = m.group(1).strip()
        if len(desc) > MAX_LEN:
            violators.append(f"{p.parent.name}: {len(desc)} chars")
    assert not violators, f"SKILL.md descriptions over {MAX_LEN} chars: {violators}"


def test_first_sentence_self_contained():
    # First sentence must contain a verb and end before 80 chars — the trigger
    # phrase must survive every known truncation point (57-char Claude/ZCode
    # preview windows included).
    for p in SKILLS:
        text = p.read_text(encoding="utf-8")
        m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
        desc = m.group(1).strip()
        first = desc.split(". ")[0] + "."
        assert len(first) <= 80, f"{p.parent.name}: first sentence {len(first)} chars > 80"
        assert re.search(r"\b(inspect|edit|plan|render|use|turn|guarded|translate|validate|package)\b", first, re.I) or "Use" in first, \
            f"{p.parent.name}: first sentence lacks a trigger verb"
