"""Refresh release file counts before creating the delivery ZIP."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "RELEASE_MANIFEST.json"
def included_files():
    """Return the source files GitHub will carry, including new unstaged files."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    for relative_text in result.stdout.splitlines():
        path = ROOT / relative_text
        if path.is_file():
            yield path


def main():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    data["generated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for _ in range(5):
        files = list(included_files())
        data["file_count"] = len(files)
        data["bytes"] = sum(path.stat().st_size for path in files)
        rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        if MANIFEST.read_text(encoding="utf-8") == rendered:
            break
        MANIFEST.write_text(rendered, encoding="utf-8")
    files = list(included_files())
    data["file_count"] = len(files)
    data["bytes"] = sum(path.stat().st_size for path in files)
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Manifest: {data['file_count']} files, {data['bytes']} bytes")


if __name__ == "__main__":
    main()
