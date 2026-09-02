from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

from scripts.compile_knowledge_packs import (
    compile_packs,
    find_contradictions,
    validate_links,
)

ROOT = Path(__file__).parents[2]


def test_compile_generates_pack_for_every_profile_and_manifest_hashes() -> None:
    output = ROOT / "knowledge" / "generated-test"
    result = compile_packs(ROOT, output)
    profiles = sorted(p.name for p in (ROOT / "profiles").iterdir() if p.is_dir())
    assert sorted(result["profiles"]) == profiles
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["version"] == "1.0.0"
    assert len(manifest["packs"]) == 7
    for pack in manifest["packs"]:
        assert len(pack["sha256"]) == 64
        pack_path = output / pack["path"]
        assert pack_path.is_file()
        assert not pack_path.read_text().endswith("\n\n")


def test_links_and_contradictions_are_rejected() -> None:
    assert validate_links("See [system](architecture/system.md)", ROOT) == []
    assert validate_links("[missing](missing.md)", ROOT)
    assert find_contradictions(["fact: timezone=deployment-configured", "fact: timezone=UTC"])


def test_compiler_fails_on_contradictory_sources(tmp_path: Path) -> None:
    source = tmp_path / "knowledge" / "shared"
    source.mkdir(parents=True)
    (tmp_path / "profiles" / "default").mkdir(parents=True)
    (tmp_path / "profiles" / "default" / "SOUL.md").write_text("# Default\n")
    (source / "one.md").write_text("fact: timezone=UTC\n")
    (source / "two.md").write_text("fact: timezone=America/New_York\n")
    with pytest.raises(ValueError, match="contradiction"):
        compile_packs(tmp_path, tmp_path / "out")
