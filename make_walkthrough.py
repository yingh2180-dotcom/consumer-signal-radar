"""Create a clearly labelled video walkthrough from verified UI screenshots."""
import base64
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).parent/'outputs'
captions=['1 / 4  查看样本统计、话题排行和趋势','2 / 4  核对机会假设及原始评论证据','3 / 4  按证据编号搜索原文并导出','4 / 4  下载独立人工标注模板，尚未证明 F1 达标']
frames=[{'image':'data:image/png;base64,'+base64.b64encode((ROOT/f'demo_{i:02d}.png').read_bytes()).decode(),'caption':captions[i-1]} for i in range(1,5)]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page()
    page.set_content('<canvas id="c" width="1536" height="1112"></canvas>')
    result=page.evaluate('''async (frames) => {
      const canvas=document.querySelector('canvas'),ctx=canvas.getContext('2d');
      const stream=canvas.captureStream(10),chunks=[];
      const recorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp8',videoBitsPerSecond:2500000});
      recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
      const done=new Promise(resolve=>recorder.onstop=async()=>{
        const blob=new Blob(chunks,{type:'video/webm'}),reader=new FileReader();
        reader.onload=()=>resolve(reader.result.split(',')[1]);reader.readAsDataURL(blob);
      });
      recorder.start();
      for(const f of frames){
        const img=new Image();img.src=f.image;await img.decode();
        ctx.fillStyle='#ffffff';ctx.fillRect(0,0,1536,1112);ctx.drawImage(img,0,0,1536,1024);
        ctx.fillStyle='#122239';ctx.fillRect(0,1024,1536,88);
        ctx.fillStyle='#ffffff';ctx.font='24px sans-serif';ctx.fillText(f.caption,32,1062);
        ctx.font='16px sans-serif';ctx.fillText('真实界面操作截图演示 · 非连续录屏 · 合成样本，不代表真实消费者反馈',32,1093);
        await new Promise(r=>setTimeout(r,4500));
      }
      recorder.stop();return await done;
    }''',frames)
    (ROOT/'操作演示.webm').write_bytes(base64.b64decode(result))
    browser.close()
