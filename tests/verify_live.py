"""Read live MVP data and prove rejected writes without altering review state."""
import json
from datetime import datetime, timezone
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    with httpx.Client(base_url="http://127.0.0.1:18523", timeout=15) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        assert health.json()["service"] == "consumer-insight-demo-2.0"
        response = client.get("/api/snapshot")
        response.raise_for_status()
        snapshot = response.json()
        assert snapshot["summary"]["raw_count"] == 1000
        assert snapshot["summary"]["business_count"] == 0
        assert len(snapshot["stages"]) == 5 and len(snapshot["slices"]) == 140
        assert client.post("/api/runs").status_code == 403
        assert client.post("/api/reviews", json={"record_id": "SYN-20260915-0061", "action": "FILTER", "note": "must be rejected"}, headers={"Origin": "https://external.invalid"}).status_code == 403
        assert client.get("/runtime/latest.json").status_code in (403, 404, 503)
        assert client.get("/backend/server.py").status_code in (403, 404, 503)
    report = {"verified_at": datetime.now(timezone.utc).isoformat(), "service": health.json()["service"],
              "snapshot_id": snapshot["snapshot_id"], "summary": snapshot["summary"],
              "checks": ["live health identity", "live 1000-row snapshot", "five completed stages", "140 precomputed slices", "missing Origin write denied", "foreign Origin review denied", "private runtime/source not served"],
              "cloud_connected": False, "browser_verified": False}
    (ROOT / "runtime" / "live_api_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
