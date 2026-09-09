import base64
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).parent/'outputs'
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page()
    page.set_content('<video muted></video>')
    url='data:video/webm;base64,'+base64.b64encode((root/'操作演示.webm').read_bytes()).decode()
    page.locator('video').evaluate('(v,s)=>v.src=s',url)
    page.wait_for_function('document.querySelector("video").readyState>=2')
    page.locator('video').evaluate('(v)=>v.play()')
    page.wait_for_timeout(800)
    result=page.locator('video').evaluate('(v)=>({width:v.videoWidth,height:v.videoHeight,time:v.currentTime,error:v.error})')
    assert result['width']==1536 and result['height']==1112 and result['time']>0 and result['error'] is None
    (root/'video_check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(result)
    browser.close()
