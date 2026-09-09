from pathlib import Path
import hashlib
import os

import pandas as pd
import plotly.express as px
import streamlit as st

from core import read_csv,normalize,analyze,opportunities,report_markdown,evaluate

ROOT=Path(__file__).parent
st.set_page_config(page_title='消费者洞察 · Consumer Signal Radar',page_icon='◎',layout='wide')
st.markdown('''<style>
.block-container{padding-top:2rem;max-width:1500px;padding-bottom:3rem}
h1{font-size:2.1rem!important;letter-spacing:-.04em}h2{font-size:1.25rem!important}h3{font-size:1.2rem!important}
div[data-testid="stMetric"]{border:1px solid #dce2e8;border-radius:7px;padding:14px 20px}
div[data-testid="stMetricValue"]{color:#008d95;font-weight:650}
[data-testid="stSidebar"]{border-right:1px solid #dce2e8}
[data-testid="stCaptionContainer"]{line-height:1.6}
button[data-baseweb="tab"]{font-size:16px;padding:0 22px}
</style>''',unsafe_allow_html=True)

with st.sidebar:
    st.title('消费者洞察')
    st.caption('Consumer Signal Radar · v0.1')
    uploaded=st.file_uploader('数据上传（CSV）',type=['csv'],help='最多 5000 条、10 MB。上传数据仅在本次会话内分析。')
    st.download_button('下载导入模板',(ROOT/'data/import_template.csv').read_bytes(),'import_template.csv','text/csv')
    st.divider()
    mode_label=st.selectbox('分析模式',['离线规则演示','大模型 + Embedding'])
    mode='offline' if mode_label=='离线规则演示' else 'llm'
    k=st.slider('聚类数量',2,10,8)
    if mode=='llm':
        configured=all(os.environ.get(x) for x in ['RADAR_API_KEY','RADAR_BASE_URL','RADAR_MODEL','RADAR_EMBEDDING_MODEL'])
        st.caption('本机模型配置：'+('已检测到，尚需请求验证' if configured else '未齐备，参见 README'))
        consent=st.checkbox('我同意把本批评论发送到本机配置的模型服务（可能计费）')
    else:
        consent=True
    run=st.button('开始分析',type='primary',width='stretch',disabled=not consent)
    st.caption('离线模式不向外部发送评论。大模型模式仅在点击分析后调用。')

st.title('消费者洞察雷达')
st.caption('从评论到可追溯的产品机会')
raw=uploaded.getvalue() if uploaded else (ROOT/'data/synthetic_reviews.csv').read_bytes()
signature=hashlib.sha256(raw+f'{mode}:{k}'.encode()).hexdigest()
try:
    source,quality=normalize(read_csv(raw))
except Exception as exc:
    st.error(str(exc));st.stop()
if uploaded is None:
    st.warning('合成数据 · 仅演示流程，不代表真实消费者反馈。')
else:
    st.info('用户导入样本 · 来源与代表性尚未验证，结论仅针对本批评论。')

if run or ('result' not in st.session_state and mode=='offline' and uploaded is None):
    try:
        with st.spinner('正在抽取反馈并聚类…'):
            progress=st.progress(0) if mode=='llm' else None
            data,method=analyze(source,mode,k,progress.progress if progress else None)
            st.session_state.result=(signature,data,method)
            if progress:progress.empty()
    except Exception as exc:
        st.error(str(exc));st.stop()
if 'result' not in st.session_state or st.session_state.result[0]!=signature:
    st.info(f'已读取 {len(source)} 条有效评论。点击左侧「开始分析」生成本批结果。')
    st.dataframe(source[['id','text','brand','product']].head(10),hide_index=True,width='stretch')
    st.stop()
_,all_data,method=st.session_state.result
with st.sidebar:
    st.divider()
    brand=st.selectbox('品牌筛选',['全部品牌']+sorted(all_data.brand.unique()))
    df=all_data if brand=='全部品牌' else all_data[all_data.brand.eq(brand)]
    product=st.selectbox('产品筛选',['全部产品']+sorted(df['product'].unique()))
    if product!='全部产品':df=df[df['product'].eq(product)]
    dates=df.parsed_date.dropna()
    if len(dates):
        interval=st.date_input('时间范围',(dates.min().date(),dates.max().date()),min_value=dates.min().date(),max_value=dates.max().date())
        include_missing=st.checkbox('保留无日期评论',value=True)
        if len(interval)==2:
            mask=df.parsed_date.between(pd.Timestamp(interval[0]),pd.Timestamp(interval[1])+pd.Timedelta(days=1)-pd.Timedelta(microseconds=1))
            df=df[mask | (df.parsed_date.isna() if include_missing else False)]
    st.caption(f'输入 {quality["input"]} 条 · 移除空白/完全重复 {quality["removed"]} 条 · 无效日期 {quality["invalid_dates"]} 条')
if df.empty:
    st.info('当前筛选没有评论，请调整品牌、产品或日期。');st.stop()
cards=opportunities(df)
cols=st.columns(4)
cols[0].metric('评论数',f'{len(df):,}')
cols[1].metric('话题数',df.cluster.nunique())
cols[2].metric('负面 / 混合反馈',f'{df.is_negative.mean():.0%}')
cols[3].metric('机会卡证据覆盖','100%' if cards else '—',help='仅表示所有已生成卡片至少有 3 条不同负面原文，不表示结论正确率。')
st.caption(f'当前方法：{method} · 抽取结果待人工复核 · 品牌归属仅使用导入字段')
radar,comments,assessment=st.tabs(['机会雷达','原始评论','评测'])
with radar:
    left,right=st.columns([1.05,1])
    with left:
        with st.container(border=True):
            st.subheader('痛点排行')
            ranking=df.groupby('cluster_name').agg(负面占比=('is_negative','mean'),提及量=('id','count')).reset_index()
            ranking=ranking.sort_values('负面占比')
            fig=px.bar(ranking,x='负面占比',y='cluster_name',orientation='h',hover_data=['提及量'],color_discrete_sequence=['#008d95'])
            fig.update_layout(height=300,margin=dict(l=0,r=15,t=10,b=0),xaxis_title='负面 / 混合反馈占比',yaxis_title=None,paper_bgcolor='white',plot_bgcolor='white',font=dict(color='#122239'))
            fig.update_xaxes(tickformat='.0%',range=[0,1],gridcolor='#edf0f3')
            st.plotly_chart(fig,width='stretch')
    with right:
        with st.container(border=True):
            st.subheader('反馈趋势')
            dated=df.dropna(subset=['parsed_date']).copy()
            if dated.parsed_date.nunique()>=2:
                dated['日期']=dated.parsed_date.dt.date
                trend=dated.groupby('日期').agg(负面占比=('is_negative','mean'),评论数=('id','count')).reset_index()
                fig=px.line(trend,x='日期',y='负面占比',markers=True,hover_data=['评论数'],color_discrete_sequence=['#008d95'])
                fig.update_layout(height=300,margin=dict(l=0,r=15,t=10,b=0),yaxis_title=None,xaxis_title=None,paper_bgcolor='white',plot_bgcolor='white')
                fig.update_yaxes(tickformat='.0%',range=[0,1],gridcolor='#edf0f3')
                st.plotly_chart(fig,width='stretch')
            else:st.info('需要至少两个有效日期才能展示趋势，不补造时间。')
    st.subheader('产品痛点与机会卡')
    st.caption('默认按基础优先级排序；未满足程度暂用负面占比代理，不能等同市场规模或需求强度。')
    if not cards:st.info('当前主题不足 3 条不同负面原文，暂不生成机会卡。')
    else:
        order=st.radio('排序依据',['基础优先级','趋势机会分'],horizontal=True)
        if order=='趋势机会分':cards=sorted(cards,key=lambda c:c['score'] if c['score'] is not None else -1,reverse=True)
        selection=st.selectbox('选择机会',[c['topic'] for c in cards])
        c=next(c for c in cards if c['topic']==selection)
        with st.container(border=True):
            summary,detail=st.columns([1,3])
            with summary:
                st.subheader(c['topic'])
                st.metric('基础优先级',f'{c["priority"]:.2f}')
                st.caption(f'提及 {c["count"]} 条 · 负面 {c["negative_rate"]:.0%}')
                st.caption('趋势机会分：'+(f'{c["score"]:.2f}' if c['score'] is not None else '不可计算'))
                st.caption('主题份额增长：'+(f'{c["growth"]:+.0%}' if c['growth'] is not None else '日期不足或前期零基数'))
            with detail:
                st.markdown('**建议研究假设**')
                st.write(c['hypothesis'])
                st.markdown('**原始评论证据**')
                for e in c['evidence']:
                    st.text(e['text'])
                    st.caption(f'{e["id"]} · {e["brand"]} / {e["product"]} · {e["platform"]} · {e["date"] or "无日期"}')
                    if e['source_url'].startswith(('https://','http://')):st.link_button('打开原始来源',e['source_url'])
        names=st.text_input('人工修订当前话题名称',value=c['topic'],key='name_'+signature+str(selection))
        if st.button('应用话题名称'):
            if names.strip() and names.strip() not in set(all_data.cluster_name)-{selection}:
                updated=all_data.copy();updated.loc[updated.cluster_name.eq(selection),'cluster_name']=names.strip()
                st.session_state.result=(signature,updated,method);st.rerun()
            else:st.error('名称不能为空或与其他主题重复。')
    with st.expander('评分方法与边界'):
        st.write('基础优先级 = 100 × 主题评论占比 × 负面评论占比 × 平均严重度/3。严重度是抽取标签，不是医疗判断。')
        st.write('趋势机会分 = 基础优先级 × 增长倍数（上限 3）。比较最后两个等长 7 日窗口中主题份额；不足 14 日、前期零基数或无日期时不计算。日期跨度不保证采样连续，趋势仅代表导入样本。')
        st.write('离线抽取只支持有限词表和局部否定，不识别所有反讽、多义及隐性诉求；字符聚类会受重复文本影响。每条评论只分一个簇，混合反馈可能遗漏次要主题。')
    st.download_button('导出洞察报告（Markdown）',report_markdown(df,cards,method),'consumer_insights.md','text/markdown',type='primary')
with comments:
    query=st.text_input('搜索原文 / 证据编号')
    shown=df[df.text.str.contains(query,regex=False)|df.id.str.contains(query,regex=False)] if query else df
    fields=['id','text','brand','product','date','platform','cluster_name','feedback_type','dimension','scene','ingredients','sentiment','severity','need','source_url']
    st.dataframe(shown[fields],hide_index=True,width='stretch')
    st.caption(f'显示 {len(shown)} 条，导出遵循当前搜索与筛选。')
    safe=shown[fields].copy().astype(str)
    safe=safe.map(lambda v:"'"+v if v.startswith(('=','+','-','@','\t','\r')) else v)
    st.download_button('导出结构化评论 CSV',safe.to_csv(index=False).encode('utf-8-sig'),'structured_reviews.csv','text/csv')
with assessment:
    st.subheader('人工标注验证')
    st.info('尚无独立人工标注集，未证明 F1 ≥ 0.8。合成数据和工程测试不能替代真实效果评测。')
    st.write('下载随机抽取的最多 100 条原文，由人工填写四个标签后上传。模板不预填模型答案，以减少标注偏差。')
    annotation=all_data[['id','text']].sample(min(100,len(all_data)),random_state=42).copy()
    for f in ['feedback_type','dimension','sentiment','severity']:annotation[f]=''
    st.download_button('下载 100 条待标注样本',annotation.to_csv(index=False).encode('utf-8-sig'),'annotation_template.csv','text/csv')
    st.caption('feedback_type：优点/痛点/优缺点并存/未知；dimension：肤感/功效/包装/价格/未知；sentiment：正面/负面/混合/中性；severity：0无、1轻微、2明显、3强烈（如停用/退货）。')
    gold_file=st.file_uploader('上传已完成的人工标注 CSV',type=['csv'],key='gold')
    if gold_file:
        try:
            scores,n=evaluate(all_data,read_csv(gold_file.getvalue()))
            st.dataframe(pd.DataFrame([{'字段':k,'Macro F1':v} for k,v in scores.items()]),hide_index=True)
            st.caption(f'匹配 {n} 条 · Macro F1 为各类别 F1 的平均值 · 只评四个离散字段，不代表场景/成分/诉求抽取全项验收。')
            st.warning('需确认标注独立性与真实数据来源；少于100条不满足原定样本数量。')
        except Exception as exc:st.error(str(exc))
