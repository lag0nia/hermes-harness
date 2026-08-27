"""Compile canonical documentation into deterministic, hashed read-only packs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path

DEFAULT_PROFILES = (
    "default",
    "browser-operator",
    "researcher",
    "architect-planner",
    "engineer",
    "coder",
    "documentator",
    "travel-planner",
)
LINK_RE = re.compile(r"\[[^]]+\]\(([^)#]+)(?:#[^)]+)?\)")
FACT_RE = re.compile(r"^fact:\s*([^=\s]+)\s*=\s*(.+?)\s*$", re.MULTILINE)


def validate_links(text: str, root: Path) -> list[str]:
    errors = []
    for target in LINK_RE.findall(text):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        resolved = (root / target).resolve()
        if not resolved.is_file() or root.resolve() not in resolved.parents:
            errors.append(f"broken link: {target}")
    return errors


def find_contradictions(texts: Iterable[str]) -> list[str]:
    seen: dict[str, str] = {}
    errors = []
    for text in texts:
        for key, value in FACT_RE.findall(text):
            if key in seen and seen[key] != value:
                errors.append(f"contradiction: {key}={seen[key]} vs {value}")
            seen[key] = value
    return errors


def _sources(root: Path) -> list[Path]:
    paths = list((root / "knowledge" / "shared").glob("*.md"))
    paths += list((root / "architecture").glob("*.md"))
    paths += list((root / "runbooks").glob("*.md"))
    return sorted(p for p in paths if p.is_file())


def compile_packs(root: Path, output: Path) -> dict[str, object]:
    sources = _sources(root)
    texts = [p.read_text(encoding="utf-8") for p in sources]
    contradictions = find_contradictions(texts)
    if contradictions:
        raise ValueError("; ".join(contradictions))
    all_errors = [error for text in texts for error in validate_links(text, root)]
    if all_errors:
        raise ValueError("; ".join(all_errors))

    output.mkdir(parents=True, exist_ok=True)
    profiles_root = root / "profiles"
    profiles = (
        tuple(sorted(p.name for p in profiles_root.iterdir() if p.is_dir()))
        if profiles_root.is_dir()
        else DEFAULT_PROFILES
    )
    shared = "\n\n".join(
        f"<!-- source: {p.relative_to(root)} -->\n{t}" for p, t in zip(sources, texts, strict=True)
    )
    entries = []
    for profile in profiles:
        soul = root / "profiles" / profile / "SOUL.md"
        if not soul.is_file():
            raise ValueError(f"missing profile soul: {profile}")
        content = (
            f"# Knowledge pack: {profile}\n\n{shared}\n\n"
            f"<!-- source: {soul.relative_to(root)} -->\n"
            f"{soul.read_text(encoding='utf-8')}\n"
        ).rstrip() + "\n"
        filename = f"{profile}.md"
        (output / filename).write_text(content, encoding="utf-8")
        entries.append(
            {
                "profile": profile,
                "path": filename,
                "sha256": hashlib.sha256(content.encode()).hexdigest(),
            }
        )
    manifest = {
        "version": "1.0.0",
        "source_count": len(sources),
        "packs": entries,
        "profiles": list(profiles),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    output = args.output or args.root / "knowledge" / "generated"
    compile_packs(args.root, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
