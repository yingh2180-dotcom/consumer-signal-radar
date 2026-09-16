"""Independent end-to-end checks against saved source and generated snapshots."""
import csv
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SavedPipelineAcceptance(unittest.TestCase):
    def setUp(self):
        artifact = ROOT / "frontend" / "public" / "snapshot.json"
        self.assertTrue(artifact.is_file(), "Five-layer pipeline must produce a real snapshot first")
        self.snapshot = json.loads(artifact.read_text(encoding="utf-8"))
        with (ROOT / "data" / "synthetic_reviews.csv").open(encoding="utf-8-sig", newline="") as source:
            self.raw = {row["record_id"]: row for row in csv.DictReader(source)}

    def test_raw_identity_and_text_survive_all_layers(self):
        records = self.snapshot["records"]
        self.assertEqual(len(records), 1000)
        self.assertEqual({r["record_id"] for r in records}, set(self.raw))
        for record in records:
            original = self.raw[record["record_id"]]
            for field in ("review_text", "record_id", "dataset_role", "source_platform", "source_type", "sampling_stratum", "target_product_id"):
                self.assertEqual(record[field], original[field], (record["record_id"], field))

    def test_partition_is_exhaustive_without_silent_deletion(self):
        summary = self.snapshot["summary"]
        self.assertEqual(summary["raw_count"], 1000)
        self.assertEqual(sum(summary[key] for key in ("kept_count", "filtered_count", "pending_count", "error_count")), 1000)
        actions = {action: sum(r["final_action"] == action for r in self.snapshot["records"]) for action in ("KEEP", "FILTER", "PENDING", "ERROR")}
        for action, key in (("KEEP", "kept_count"), ("FILTER", "filtered_count"), ("PENDING", "pending_count"), ("ERROR", "error_count")):
            self.assertEqual(actions[action], summary[key])

    def test_slice_metrics_are_independently_reproducible(self):
        lookup = {r["record_id"]: r for r in self.snapshot["records"]}
        feature_lookup = {f["feature_id"]: f for r in lookup.values() for f in r["features"]}
        keys = list(self.snapshot["slices"])
        self.assertEqual(len(keys), 140)
        for key in keys[::13] + ["全部|全部|全部"]:
            sliced = self.snapshot["slices"][key]
            eligible = [lookup[rid] for rid in sliced["record_ids"] if lookup[rid]["final_action"] == "KEEP"]
            for metric in sliced["metrics"]:
                base = [r for r in eligible if metric["product"] in ("全部", r["product_name"])]
                mentioned = {r["record_id"] for r in base if any(f["category"] == metric["category"] and f["sentiment"] == metric["sentiment"] for f in r["features"])}
                self.assertEqual(metric["sample_size"], len(base), (key, metric["decision_id"]))
                self.assertEqual(metric["mention_count"], len(mentioned))
                if base:
                    self.assertAlmostEqual(metric["mention_rate"], len(mentioned) / len(base), places=6)
                evidence_records = [feature_lookup[fid]["record_id"] for fid in metric["evidence_ids"]]
                self.assertEqual(len(evidence_records), len(set(evidence_records)))
                self.assertTrue(set(evidence_records) <= mentioned)

    def test_features_have_actual_evidence_and_test_only_context(self):
        self.assertEqual(self.snapshot["context"], "demo")
        self.assertEqual(self.snapshot["mode"], "rules_demo")
        self.assertEqual(self.snapshot["summary"]["business_count"], 0)
        seen = set()
        for record in self.snapshot["records"]:
            self.assertEqual(record["dataset_role"], "pipeline_test")
            for feature in record["features"]:
                self.assertNotIn(feature["feature_id"], seen)
                seen.add(feature["feature_id"])
                self.assertEqual(feature["record_id"], record["record_id"])
                self.assertTrue(feature["evidence"])
                self.assertIn(feature["evidence"], record["clean_text"])
        self.assertGreater(len(seen), 0)
        self.assertEqual(self.snapshot["qa"]["model_evaluation_status"], "NOT_EVALUATED")
        self.assertEqual(self.snapshot["qa"]["trend_status"], "NO_REAL_TIMESTAMPS")
        self.assertEqual(self.snapshot["qa"]["clustering_status"], "NOT_ENABLED")


if __name__ == "__main__":
    unittest.main()
