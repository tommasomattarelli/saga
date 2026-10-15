#!/usr/bin/env python3
"""Cross-stack reader/writer audit for untyped dict keys.

Static analysers are blind here: `state["foo"]` is a string, not a symbol, and the
writer is frequently in another language than the reader. So sweep py + ts/tsx +
yaml together and classify every occurrence as READ or WRITE.

    python3 scripts/key_audit.py world_state_key another_key

Heuristic — it reports candidates, not verdicts. Short common names collide with
unrelated code (`background` hits CSS), so verify each hit before believing it.
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAYERS = {
    "py": [ROOT / "backend/app", ROOT / "backend/alembic"],
    "ts": [ROOT / "frontend/src"],
    "yaml": [ROOT / "templates", ROOT / "backend/app"],
}
SUFFIX = {"py": {".py"}, "ts": {".ts", ".tsx"}, "yaml": {".yaml", ".yml"}}


def patterns(k: str) -> dict[str, list[tuple[str, re.Pattern]]]:
    e = re.escape(k)
    return {
        "py": [
            ("W", re.compile(rf'\[["\']{e}["\']\]\s*=')),
            ("W", re.compile(rf'setdefault\(\s*["\']{e}["\']')),
            ("W", re.compile(rf'pop\(\s*["\']{e}["\']')),
            ("W", re.compile(rf'["\']{e}["\']\s*:')),
            ("W", re.compile(rf'\b{e}\s*=\s*[^=]')),
            ("R", re.compile(rf'get\(\s*["\']{e}["\']')),
            ("R", re.compile(rf'\[["\']{e}["\']\](?!\s*=[^=])')),
            ("R", re.compile(rf'\{{{e}\}}')),
        ],
        "ts": [
            ("W", re.compile(rf'["\']?{e}["\']?\s*:\s*[^:]')),
            ("W", re.compile(rf'\.{e}\s*=\s*[^=]')),
            ("R", re.compile(rf'[?.]\.?{e}\b(?!\s*[:=][^=])')),
            ("R", re.compile(rf'\[["\']{e}["\']\]')),
        ],
        "yaml": [("W", re.compile(rf"^\s*{e}\s*:"))],
    }


def scan(keys: list[str]) -> dict:
    hits: dict = defaultdict(lambda: defaultdict(list))
    for layer, roots in LAYERS.items():
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.suffix not in SUFFIX[layer] or "__pycache__" in str(path):
                    continue
                try:
                    lines = path.read_text().splitlines()
                except UnicodeDecodeError:
                    continue
                for key in keys:
                    for kind, rx in patterns(key)[layer]:
                        for n, line in enumerate(lines, 1):
                            if rx.search(line):
                                rel = path.relative_to(ROOT)
                                hits[key][kind].append(f"{rel}:{n}")
    return hits


def is_test(loc: str) -> bool:
    return "__tests__" in loc or "/test_" in loc or "/tests/" in loc or ".test." in loc


def verdict(w: int, r: int) -> str:
    if w and r:
        return "live"
    if r and not w:
        return "ORPHAN READ"
    if w and not r:
        return "ORPHAN WRITE"
    return "FULLY DEAD"


if __name__ == "__main__":
    keys = sys.argv[1:]
    hits = scan(keys)
    for key in keys:
        w = sorted(set(hits[key]["W"]))
        r = sorted(set(hits[key]["R"]))
        # A key only a test writes is dead in production: the test builds the state
        # by hand and then validates the reader against itself.
        pw = [x for x in w if not is_test(x)]
        pr = [x for x in r if not is_test(x)]
        flag = "  <<< TEST-ONLY WRITER" if w and not pw else ""
        print(f"\n=== {key}  [{verdict(len(pw), len(pr))}]  prod W={len(pw)} R={len(pr)}"
              f"  (test W={len(w) - len(pw)} R={len(r) - len(pr)}){flag}")
        print(f"  W: {', '.join(pw[:6]) or '—'}")
        print(f"  R: {', '.join(pr[:6]) or '—'}")
