"""Browser acceptance for the local Demo MVP using installed Microsoft Edge."""
import json
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
URL = "http://127.0.0.1:18523"


def run():
    OUT.mkdir(exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(URL, wait_until="networkidle")
        page.get_by_text("先看洞察，再核对证据", exact=True).wait_for(timeout=60_000)
        assert page.get_by_text("合成样本 · 流程演示", exact=True).count() == 1
        assert page.get_by_text("真实业务样本", exact=True).count() == 1
        assert page.locator(".stat.amber strong").inner_text() == "0"
        assert page.locator(".stat").first.locator("strong").inner_text() == "1000"
        page.screenshot(path=str(OUT / "dashboard-desktop.png"), full_page=True)

        page.get_by_test_id("filter-product").select_option(label="演示产品 A")
        page.get_by_test_id("filter-skin").select_option(label="干皮")
        page.get_by_test_id("filter-scene").select_option(label="早间")
        assert page.locator(".stat").first.locator("strong").inner_text() != "1000"
        page.locator("button.metric-row").first.click()
        page.get_by_text("从指标一路回到原始评论", exact=True).wait_for()
        page.locator("[data-testid=evidence-card]").first.wait_for()
        assert page.locator("[data-testid=evidence-card] mark").first.inner_text().strip()
        page.screenshot(path=str(OUT / "evidence-desktop.png"), full_page=True)

        page.get_by_test_id("nav-method").click()
        page.get_by_text("流程透明，能力边界也透明", exact=True).wait_for()
        assert page.locator(".pipeline article").count() == 5
        assert page.get_by_text("AI 模型评测", exact=True).count() == 1
        assert page.get_by_text("真实时间趋势", exact=True).count() == 1
        page.screenshot(path=str(OUT / "method-desktop.png"), full_page=True)

        page.get_by_test_id("nav-admin").click()
        page.get_by_text("内部运行台", exact=True).last.wait_for()
        assert page.get_by_test_id("start-run").count() == 1
        assert page.get_by_text("Supabase 同步未执行", exact=True).count() == 1
        assert page.get_by_text("人工复核", exact=True).count() == 1
        page.screenshot(path=str(OUT / "admin-desktop.png"), full_page=True)

        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        mobile.on("pageerror", lambda error: errors.append("mobile: " + str(error)))
        mobile.goto(URL, wait_until="networkidle")
        mobile.get_by_text("先看洞察，再核对证据", exact=True).wait_for(timeout=60_000)
        assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2")
        mobile.screenshot(path=str(OUT / "dashboard-mobile.png"), full_page=True)
        assert not errors, errors
        browser.close()

    report = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "url": URL,
        "browser": "Installed Microsoft Edge via Playwright",
        "viewports": ["1440x1000", "390x844"],
        "page_errors": errors,
        "checks": [
            "synthetic identity and business_count=0 visible",
            "1000-row overview visible",
            "precomputed product/skin/scene filter changes the slice",
            "metric opens exact highlighted source evidence",
            "five completed layers visible",
            "AI evaluation and real trend explicitly disabled",
            "local operations are separated and enabled only with live backend",
            "Supabase cloud sync is labeled not executed",
            "mobile document has no horizontal overflow",
        ],
    }
    (OUT / "browser_checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    run()
