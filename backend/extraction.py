"""Transparent phrase rules for the original synthetic corpus, not AI inference."""
import hashlib

# These phrases are independently authored demo input vocabulary; no label file is read.
RULES = {
    '包装': ('瓶盖扣得很稳，放在包里没有漏出来', '按压泵反复按了几次还是不出料'),
    '成分': ('成分说明写得清楚，方便核对自己的避雷项', '看了成分表仍不确定是否适合自己的情况'),
    '尺寸': ('这次的小规格很方便出差携带', '收到后觉得容量比想象中小'),
    '服务': ('客服耐心解释了使用顺序', '询问使用方法后一直没收到回复'),
    '功效': ('用了一段时间，干燥紧绷的感觉有所缓解', '连续用了几周，暂时没感觉到明显变化'),
    '价格': ('这次活动价格在我的预算内', '买完才看到更低的活动价格，有点犹豫'),
    '气味': ('气味很淡，涂完过一会儿就闻不到了', '香味对我来说偏浓，晚上用有点介意'),
    '使用体验': ('推开很顺，后续上妆也比较服帖', '涂完有些黏，叠加防晒时出现了搓泥'),
    '物流': ('配送很快，外箱收到时完整', '路上等了好几天，外箱还有些压痕'),
    '新鲜度': ('标注的日期清楚，剩余使用时间充足', '到手后发现剩余使用时间比预想短'),
    '真伪': ('包装上的核验步骤容易找到', '不知道怎样核验来源，准备先问客服'),
    '整体': ('总体使用感受符合我的预期', '整体体验没有达到预期，暂时不打算继续买'),
    '其他': ('希望以后能提供更详细的用量说明', '说明书的字有点小，阅读不太方便'),
}


def extract(record_id, raw_text):
    features = []
    for category, phrases in RULES.items():
        for polarity, phrase in zip(('positive', 'negative'), phrases):
            if phrase not in raw_text:
                continue
            sentiment = 'neutral' if category == '其他' and polarity == 'positive' else polarity
            fid = hashlib.sha256(f'{record_id}|{category}|{sentiment}|{phrase}'.encode()).hexdigest()[:20]
            features.append({'feature_id': f'F-{fid}', 'record_id': record_id,
                             'category': category, 'sentiment': sentiment, 'evidence': phrase,
                             'audit_status': 'RULE_VALIDATED'})
    return features


def context(text):
    skin = next((label for phrase, label in [('我是干皮', '干皮'), ('我是油皮', '油皮'), ('我是混合皮', '混合皮')] if phrase in text), '未说明')
    scene = next((label for phrase, label in [('早上用的时候', '早间'), ('晚上护肤时', '晚间'), ('出差这几天', '出差'), ('日常使用中', '日常'), ('刚开始尝试时', '初次尝试')] if phrase in text), '未说明')
    return skin, scene
