"""Browser acceptance checks using installed Edge; run with system Python."""
import json
import csv
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).parent
OUT=ROOT/'outputs'


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        context=browser.new_context(viewport={'width':1536,'height':1024},device_scale_factor=1,accept_downloads=True)
        page=context.new_page()
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:18521',wait_until='networkidle')
        page.get_by_text('产品痛点与机会卡',exact=True).wait_for(timeout=90000)
        page.get_by_text('1,000',exact=True).wait_for()
        page.get_by_text('刺激与耐受 / 闷痘负担 · C03',exact=True).first.wait_for()
        page.wait_for_timeout(1800)
        page.screenshot(path=str(OUT/'dashboard.png'),full_page=True)
        page.screenshot(path=str(OUT/'demo_01.png'))
        page.get_by_text('原始评论证据',exact=True).scroll_into_view_if_needed()
        page.wait_for_timeout(1200)
        page.screenshot(path=str(OUT/'demo_02.png'))
        with page.expect_download() as download:
            page.get_by_role('button',name='导出洞察报告（Markdown）').click()
        download.value.save_as(str(OUT/'合成数据案例报告.md'))
        assert 'SYN' in (OUT/'合成数据案例报告.md').read_text(encoding='utf-8')
        page.get_by_role('tab',name='原始评论',exact=True).click()
        page.get_by_label('搜索原文 / 证据编号').fill('SYN0001')
        page.get_by_label('搜索原文 / 证据编号').press('Enter')
        page.get_by_text('显示 1 条，导出遵循当前搜索与筛选。',exact=True).wait_for()
        page.wait_for_timeout(1200)
        page.screenshot(path=str(OUT/'demo_03.png'))
        with page.expect_download() as dl:
            page.get_by_role('button',name='导出结构化评论 CSV').click()
        dl.value.save_as(str(OUT/'qa_export.csv'))
        assert 'SYN0001' in (OUT/'qa_export.csv').read_text(encoding='utf-8-sig')
        page.get_by_role('tab',name='评测',exact=True).click()
        page.get_by_text('人工标注验证',exact=True).wait_for()
        page.wait_for_timeout(1200)
        page.screenshot(path=str(OUT/'demo_04.png'))
        with page.expect_download() as dl:
            page.get_by_role('button',name='下载 100 条待标注样本').click()
        dl.value.save_as(str(OUT/'待人工标注100条.csv'))
        page.get_by_label('品牌筛选',exact=True).click()
        page.get_by_role('option',name='竞品示例',exact=True).click()
        expected=sum(r['brand']=='竞品示例' for r in csv.DictReader((ROOT/'data/synthetic_reviews.csv').open(encoding='utf-8-sig')))
        page.get_by_text(str(expected),exact=True).wait_for()
        page.get_by_label('品牌筛选',exact=True).click()
        page.get_by_role('option',name='全部品牌',exact=True).click()
        page.get_by_text('1,000',exact=True).wait_for()
        # A real CSV upload must change the backend result, never just the filename.
        fixture='id,text,brand,product,date\nU1,刺激得停用,测试品牌,测试产品,2026-08-01\nU2,明显刺激啊,测试品牌,测试产品,2026-08-02\nU3,真的刺激泛红,测试品牌,测试产品,2026-08-03\n'
        page.locator('input[type=file]').first.set_input_files({'name':'acceptance.csv','mimeType':'text/csv','buffer':fixture.encode('utf-8')})
        page.get_by_text('已读取 3 条有效评论。点击左侧「开始分析」生成本批结果。',exact=True).wait_for()
        page.get_by_role('button',name='开始分析',exact=True).click()
        page.get_by_text('产品痛点与机会卡',exact=True).wait_for(timeout=90000)
        page.get_by_role('tab',name='原始评论',exact=True).click()
        page.get_by_label('搜索原文 / 证据编号').fill('U1')
        page.get_by_label('搜索原文 / 证据编号').press('Enter')
        page.get_by_text('显示 1 条，导出遵循当前搜索与筛选。',exact=True).wait_for()
        assert page.get_by_label('分析模式',exact=True).count()
        mobile=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=1)
        mobile.goto('http://127.0.0.1:18521',wait_until='networkidle')
        mobile.get_by_text('产品痛点与机会卡',exact=True).wait_for(timeout=90000)
        mobile.wait_for_timeout(1500)
        mobile.screenshot(path=str(OUT/'mobile.png'),full_page=True)
        assert mobile.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
        assert not errors,errors
        (OUT/'browser_checks.json').write_text(json.dumps({'desktop':'1536x1024','mobile':'390x844','page_errors':errors,'checks':['1000 sample rows','original evidence in downloaded report','search one evidence ID','CSV export','annotation export','brand filter updates count','uploaded CSV reaches backend and changes rows','mobile no document overflow'],'browser':'Installed Microsoft Edge via Playwright; built-in browser unavailable'},ensure_ascii=False,indent=2),encoding='utf-8')
        browser.close()

if __name__=='__main__':run()
