"""Create verified SQLite backups and restore them only into a new directory.

The paid-model budget ledger is deliberately excluded. It is an append-only
local spending guard and must not be rolled back with business data.
"""
import argparse
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
BUDGET_DB_NAME = "budget.sqlite3"


def _validate_new_destination(destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("目标目录已存在，请指定一个全新的空路径。")
    destination.mkdir(parents=True)
    return destination


def _copy_sqlite(source, destination):
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(destination)) as dst:
        src.backup(dst)
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError(f"数据库备份完整性检查失败：{source.name}")


def backup(source, destination):
    source = Path(source).resolve()
    destination = _validate_new_destination(destination)
    files = []
    for path in sorted(source.glob("*.sqlite*")):
        if path.suffix not in (".sqlite", ".sqlite3") or path.name == BUDGET_DB_NAME:
            continue
        _copy_sqlite(path, destination / path.name)
        files.append(path.name)
    if not files:
        raise ValueError("源目录没有可备份的业务数据库，未生成有效备份。")
    manifest = {
        "format": 2,
        "created_at": datetime.now().isoformat(),
        "databases": files,
        "secrets_included": False,
        "budget_ledger_included": False,
        "restore_note": "预算账本不会随业务数据恢复或回滚。",
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return files


def restore(source, destination):
    source = Path(source).resolve()
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("备份目录缺少 manifest.json。")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = manifest.get("databases")
    if not isinstance(names, list) or not names:
        raise ValueError("备份清单中没有数据库。")
    if BUDGET_DB_NAME in names or manifest.get("budget_ledger_included") is True:
        raise ValueError("该备份包含预算账本，拒绝恢复以防累计预算回滚。")

    destination = _validate_new_destination(destination)
    restored = []
    for name in names:
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError("备份清单包含非法路径。")
        path = (source / name).resolve()
        if path.parent != source or not path.is_file() or path.suffix not in (".sqlite", ".sqlite3"):
            raise ValueError(f"备份数据库无效：{name}")
        _copy_sqlite(path, destination / name)
        restored.append(name)
    (destination / "restore-manifest.json").write_text(
        json.dumps({"restored_at": datetime.now().isoformat(), "databases": restored,
                    "budget_ledger_restored": False}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return restored


if __name__ == "__main__":
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("--source", default=os.environ.get("RADAR_DATA_DIR", str(ROOT / "runtime")))
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    print((backup if args.action == "backup" else restore)(args.source, args.destination))
