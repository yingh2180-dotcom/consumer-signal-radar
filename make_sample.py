"""Deterministic synthetic fixtures, never represented as public consumer data."""
import csv
import random
from datetime import date,timedelta
from pathlib import Path

ROOT=Path(__file__).parent


def generate():
    rng=random.Random(42)
    texts=[
        '上脸烫但不是过敏，晚上用完有些泛红，希望更温和一点。',
        '化妆前叠涂防晒会搓泥，想要更容易搭配底妆。',
        '油皮用了以后闷痘，鼻翼长了闭口，已经停用。',
        '换季脸还是干燥紧绷，希望保湿更持久。',
        '吸收慢，摸起来黏黏的，希望肤感更清爽。',
        '泵头按不出，瓶口还漏液，希望改善包装。',
        '价格高，活动后又涨价，日常买不划算。',
        '用了三周没变化，细纹改善不明显，希望说明见效周期。',
        '早上用吸收快，肤感清爽，化妆前也好用。',
        '敏感肌用着温和，不刺激，没有泛红。',
        '某国货早C晚A太刺激，已经停用，想要低刺激的选择。',
        '保湿好但是叠涂搓泥，希望解决搭配问题。',
    ]
    products=[('珀莱雅','红宝石面霜'),('珀莱雅','双抗精华'),('珀莱雅','源力精华'),('竞品示例','修护精华')]
    rows=[]
    for i in range(1000):
        idx=rng.randrange(len(texts))
        brand,product=products[i%len(products)] if idx!=10 else ('未指明','未指明')
        # Vary context in a visibly synthetic way; never fabricate author identities or source URLs.
        text=f'{texts[idx]}（合成场景 {i+1:04d}：使用第{1+i%28}天，单次{1+i%3}泵。）'
        rows.append({'id':f'SYN{i+1:04d}','text':text,'brand':brand,'product':product,'platform':['模拟天猫','模拟小红书','模拟京东','模拟抖音'][i%4],'date':str(date(2026,8,1)+timedelta(days=i%28)),'source_url':'','data_kind':'合成演示数据'})
    root=ROOT/'data'
    root.mkdir(exist_ok=True)
    with (root/'synthetic_reviews.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    with (root/'import_template.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader()
        writer.writerow({'id':'EXAMPLE001','text':'请替换为获准使用的真实评论','brand':'未指明','product':'未指明','date':'','platform':'未提供','source_url':'','data_kind':'模板示例，非真实评论'})

if __name__=='__main__':
    generate()
