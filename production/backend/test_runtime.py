import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from backend import engine
import maintenance
import launch


class RuntimeSafetyTests(unittest.TestCase):
    def test_stale_heartbeat_process_is_not_treated_as_alive(self):
        with patch("launch.os.kill", side_effect=ProcessLookupError):
            self.assertFalse(launch.process_alive(999999))
        with patch("launch.os.kill", return_value=None):
            self.assertTrue(launch.process_alive(os.getpid()))

    def test_backup_restore_excludes_budget_ledger(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            live.mkdir()
            with closing(sqlite3.connect(live / "radar.sqlite3")) as connection:
                connection.execute("CREATE TABLE sample(value TEXT)")
                connection.execute("INSERT INTO sample VALUES('current')")
                connection.commit()
            with closing(sqlite3.connect(live / "budget.sqlite3")) as connection:
                connection.execute("CREATE TABLE reservations(amount REAL)")
                connection.execute("INSERT INTO reservations VALUES(12.5)")
                connection.commit()

            backup_dir = root / "backup"
            self.assertEqual(maintenance.backup(live, backup_dir), ["radar.sqlite3"])
            manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["budget_ledger_included"])
            self.assertFalse((backup_dir / "budget.sqlite3").exists())

            restored = root / "restored"
            self.assertEqual(maintenance.restore(backup_dir, restored), ["radar.sqlite3"])
            self.assertTrue((restored / "radar.sqlite3").is_file())
            self.assertFalse((restored / "budget.sqlite3").exists())

    def test_restore_rejects_legacy_backup_containing_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backup_dir = root / "legacy"
            backup_dir.mkdir()
            (backup_dir / "manifest.json").write_text(
                json.dumps({"databases": ["budget.sqlite3"]}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "预算账本"):
                maintenance.restore(backup_dir, root / "restored")

    def test_budget_path_does_not_follow_restored_data_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = root / "permanent" / "budget.sqlite3"
            first_data = root / "data-a"
            restored_data = root / "data-restored"
            environment = {
                "RADAR_DATA_DIR": str(first_data),
                "RADAR_BUDGET_DB_PATH": str(ledger),
                "RADAR_BUDGET_CNY": "0.01",
            }
            payload = {"model": "text-embedding-v4", "input": ["x" * 9000]}
            with patch.dict(os.environ, environment, clear=False):
                engine._reserve_budget("/embeddings", payload)
                os.environ["RADAR_DATA_DIR"] = str(restored_data)
                with self.assertRaisesRegex(ValueError, "预算"):
                    engine._reserve_budget("/embeddings", payload)
            self.assertTrue(ledger.is_file())
            self.assertFalse((restored_data / "budget.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
