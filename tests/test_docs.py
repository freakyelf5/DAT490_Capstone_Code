"""Every rule document is reachable from the README, links work, the dictionary is current."""

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\]\(([^)#\s]+)(#[^)\s]*)?\)")


def anchors(path):
    """GitHub-style anchors of a Markdown file's headings."""
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            text = line.lstrip("#").strip().lower()
            out.add("#" + re.sub(r"[^a-z0-9 _-]", "", text).replace(" ", "-"))
    return out


def links(path):
    for target, anchor in LINK.findall(path.read_text(encoding="utf-8")):
        if not target.startswith("http"):
            yield (path.parent / unquote(target)).resolve(), anchor


def test_every_rule_is_linked_from_readme():
    linked = {target for target, _ in links(ROOT / "README.md")}
    for doc in (ROOT / "rules").glob("*.md"):
        assert doc.resolve() in linked, f"{doc.name} is not linked from README.md"


def test_relative_links_resolve():
    for doc in ROOT.rglob("*.md"):
        for target, anchor in links(doc):
            assert target.exists(), f"{doc.relative_to(ROOT)}: broken link to {target}"
            if anchor and target.suffix == ".md":
                assert anchor in anchors(target), f"{doc.relative_to(ROOT)}: no {anchor}"


def test_published_dictionary_matches_definitions(tmp_path):
    script = ROOT / "pipeline" / "05_dictionary.py"
    subprocess.run([sys.executable, script, "--out", tmp_path], check=True)
    for name in ("data_dictionary.md", "data_dictionary.csv"):
        published = (ROOT / "dictionary" / name).read_text(encoding="utf-8")
        assert published == (tmp_path / name).read_text(encoding="utf-8"), (
            f"dictionary/{name} is out of date: run python pipeline/05_dictionary.py"
        )
