"""Build the store ZIP from the current extension source: python scripts/package_extension.py."""

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def package_extension():
    root = Path(__file__).resolve().parents[1]
    source = root / "extension"
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    output = root / "talentmatch-extension.zip"
    # Explicit inventory excludes local artwork, screenshots, and temporary files.
    files = ("manifest.json", "popup.html", "popup.js", "theme.js", "style.css")
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name in files:
            archive.write(source / name, name)
    print(f"Packaged TalentMatch AI {manifest['version']}: {output}")
    return output


if __name__ == "__main__":
    package_extension()
