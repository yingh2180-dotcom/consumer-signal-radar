"""Create the reviewable 2.0 delivery ZIP without local dependency caches."""
from pathlib import Path
import os
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT.parent / f"{ROOT.name}.zip"
EXCLUDED_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", "work", "runtime", "dist"}
EXCLUDED_FILES = {"launcher.json", "server.log"}


def main():
    if TARGET.exists():
        raise SystemExit(f"Refusing to overwrite existing archive: {TARGET}")
    count = 0
    with zipfile.ZipFile(TARGET, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for current, dirs, files in os.walk(ROOT, followlinks=False):
            dirs[:] = sorted(name for name in dirs if name not in EXCLUDED_DIRS)
            for name in sorted(files):
                path = Path(current) / name
                if name in EXCLUDED_FILES or path.suffix == ".pyc":
                    continue
                archive.write(path, Path(ROOT.name) / path.relative_to(ROOT))
                count += 1
    print(f"Created {TARGET.name}: {count} files, {TARGET.stat().st_size} bytes")


if __name__ == "__main__":
    main()
