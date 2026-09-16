import React, {useEffect, useMemo, useState} from 'react';
import {
  Activity, ArrowRight, BarChart3, CheckCircle2, ChevronRight, Database,
  ExternalLink, Eye, FileCheck2, FlaskConical, Layers3, Play, Search,
  ShieldCheck, Sparkles, TriangleAlert
} from 'lucide-react';
import {buildEvidenceIndex, getSlice, highlightEvidence, leadingMetrics, percent} from './data-model.js';

const NAV = [
  ['insights', '总览与洞察', BarChart3],
  ['evidence', '证据追溯', Search],
  ['method', '方法与边界', Layers3],
  ['admin', '内部运行台', Activity],
];
const SENTIMENT = {negative: '负向', positive: '正向', neutral: '中性'};

async function loadData() {
  let health = null;
  try {
    const response = await fetch('/api/health', {cache: 'no-store'});
    if (response.ok) health = await response.json();
  } catch {}
  const path = health?.status === 'ok' ? '/api/snapshot' : '/snapshot.json';
  const response = await fetch(path, {cache: 'no-store'});
  if (!response.ok) throw new Error('snapshot');
  return {snapshot: await response.json(), health};
}

function Badge({children, tone = 'teal'}) { return <span className={`badge badge-${tone}`}>{children}</span>; }
function Empty({children}) { return <div className="empty"><TriangleAlert size={18}/><span>{children}</span></div>; }

function Header({snapshot, source}) {
  return <header className="topbar">
    <div>
      <div className="eyebrow">CONSUMER INSIGHT PIPELINE</div>
      <h1>消费者洞察工作台 <span>Demo 2.0</span></h1>
    </div>
    <div className="header-meta">
      <Badge>合成样本 · 流程演示</Badge>
      <Badge tone="blue">rules_demo / demo-v1</Badge>
      <span className="source-dot"><i className={source === 'dynamic' ? 'online' : ''}/>{source === 'dynamic' ? '本机服务已连接' : '只读快照'}</span>
      <span className="snapshot-id">{snapshot?.snapshot_id}</span>
    </div>
  </header>;
}

function Sidebar({page, setPage}) {
  return <aside className="sidebar" aria-label="主导航">
    <div className="brand"><div className="brand-mark">P</div><div><strong>Insight Lab</strong><small>产品作品演示</small></div></div>
    <nav>{NAV.map(([id, label, Icon], index) => <button key={id} className={page === id ? 'active' : ''} onClick={() => setPage(id)} data-testid={`nav-${id}`}>
      <span className="nav-index">0{index + 1}</span><Icon size={18}/><span>{label}</span><ChevronRight className="nav-arrow" size={16}/>
    </button>)}</nav>
    <div className="side-note"><ShieldCheck size={20}/><strong>演示数据隔离</strong><p>1000 条原创合成样本<br/>真实业务样本为 0</p></div>
  </aside>;
}

function Filters({snapshot, value, onChange}) {
  const groups = [['product', '产品', snapshot.filter_options.products], ['skin', '肤质', snapshot.filter_options.skins], ['scene', '场景', snapshot.filter_options.scenes]];
  return <div className="filters" aria-label="洞察筛选">{groups.map(([key, label, options]) => <label key={key}><span>{label}</span><select value={value[key]} onChange={event => onChange({...value, [key]: event.target.value})} data-testid={`filter-${key}`}>{options.map(option => <option key={option}>{option}</option>)}</select></label>)}<div className="filter-caption"><Database size={16}/>只读取后端预计算切片</div></div>;
}

function Stat({label, value, note, accent}) { return <article className={`stat ${accent ?? ''}`}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>; }

function MetricList({title, metrics, onEvidence, tone}) {
  const max = Math.max(1, ...metrics.map(item => item.mention_count));
  return <section className="panel metric-panel">
    <div className="panel-title"><div><span className={`title-dot ${tone}`}/><h3>{title}</h3></div><small>按不同评论编号计数</small></div>
    <div className="metric-list">{metrics.length ? metrics.map(metric => <button key={metric.decision_id} onClick={() => onEvidence(metric)} className="metric-row">
      <div className="metric-label"><strong>{metric.category}</strong><span>{metric.mention_count} 条 / n={metric.sample_size}</span></div>
      <div className="metric-track"><i style={{width: `${Math.max(4, metric.mention_count / max * 100)}%`}}/></div>
      <b>{percent(metric.mention_rate)}</b><Eye size={16}/>
    </button>) : <Empty>当前切片没有这一类观点。</Empty>}</div>
  </section>;
}

function InsightPage({snapshot, slice, filters, setFilters, openMetric}) {
  const negative = leadingMetrics(slice, 'negative');
  const positive = leadingMetrics(slice, 'positive');
  const opportunities = (slice?.opportunities ?? []).slice(0, 3);
  return <div data-testid="page-insights">
    <div className="page-heading"><div><span className="kicker">PUBLIC INSIGHT VIEW</span><h2>先看洞察，再核对证据</h2><p>本页只描述合成样本，用来证明流程能够产出可追溯结果。</p></div><div className="heading-proof"><CheckCircle2/><span>快照已通过 Schema 与证据校验</span></div></div>
    <Filters snapshot={snapshot} value={filters} onChange={setFilters}/>
    <div className="stats-grid">
      <Stat label="当前切片样本" value={slice?.summary.raw_count ?? 0} note="包含保留与过滤记录"/>
      <Stat label="进入洞察统计" value={slice?.summary.kept_count ?? 0} note="最终动作 = KEEP" accent="teal"/>
      <Stat label="观点特征" value={slice?.summary.feature_count ?? 0} note="一条评论可含多个观点" accent="blue"/>
      <Stat label="真实业务样本" value="0" note="全部为 pipeline_test" accent="amber"/>
    </div>
    <div className="two-col"><MetricList title="主要问题线索" metrics={negative} onEvidence={openMetric} tone="coral"/><MetricList title="主要正向反馈" metrics={positive} onEvidence={openMetric} tone="teal"/></div>
    <section className="panel opportunity-panel">
      <div className="panel-title"><div><span className="title-dot blue"/><h3>研究候选</h3></div><Badge tone="gray">不是业务结论</Badge></div>
      <div className="opportunity-grid">{opportunities.length ? opportunities.map(item => <article key={item.decision_id}><span>待真实数据验证</span><h4>{item.title}</h4><p>{item.fact}</p><div><strong>建议验证</strong>{item.validation_action}</div><button onClick={() => openMetric((slice.metrics ?? []).find(m => m.decision_id === item.decision_id))}>查看证据 <ArrowRight size={15}/></button></article>) : <Empty>当前切片没有满足证据门槛的研究候选。</Empty>}</div>
    </section>
  </div>;
}

function EvidenceText({text, evidence}) { return <p className="evidence-text">{highlightEvidence(text, evidence).map((part, i) => part.match ? <mark key={i}>{part.text}</mark> : <React.Fragment key={i}>{part.text}</React.Fragment>)}</p>; }

function EvidencePage({snapshot, selectedMetric, setSelectedMetric, index}) {
  const [query, setQuery] = useState('');
  const metrics = snapshot.slices['全部|全部|全部']?.metrics ?? [];
  const chosen = selectedMetric ?? metrics[0];
  const items = (chosen?.evidence_ids ?? []).map(id => index.get(id)).filter(Boolean).filter(item => !query || item.record.record_id.toLowerCase().includes(query.toLowerCase()) || item.record.review_text.includes(query));
  return <div data-testid="page-evidence">
    <div className="page-heading"><div><span className="kicker">TRACEABLE EVIDENCE</span><h2>从指标一路回到原始评论</h2><p>每个数字都绑定 feature_id、record_id 和原文片段。</p></div><Badge>证据原文未改写</Badge></div>
    <section className="evidence-layout">
      <aside className="topic-list"><h3>选择指标</h3>{metrics.slice().sort((a,b)=>b.mention_count-a.mention_count).slice(0,18).map(metric => <button key={metric.decision_id} className={chosen?.decision_id === metric.decision_id ? 'active' : ''} onClick={() => setSelectedMetric(metric)}><span>{metric.category} · {SENTIMENT[metric.sentiment]}</span><b>{metric.mention_count}</b></button>)}</aside>
      <div className="evidence-main">
        <div className="evidence-summary"><div><span>当前指标</span><h3>{chosen?.category} · {SENTIMENT[chosen?.sentiment]}</h3></div><div><strong>{chosen?.mention_count ?? 0}</strong><span>不同评论</span></div><div><strong>{percent(chosen?.mention_rate)}</strong><span>提及率 / n={chosen?.sample_size}</span></div><Badge tone={chosen?.support_status === 'SUPPORTED' ? 'teal' : 'amber'}>{chosen?.support_status}</Badge></div>
        <label className="searchbox"><Search size={17}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="按编号或原文搜索当前证据"/></label>
        <div className="evidence-cards">{items.length ? items.map(({record, feature}) => <article key={feature.feature_id} data-testid="evidence-card"><div className="record-head"><span>{record.record_id}</span><Badge tone="gray">{record.product_name}</Badge><Badge tone="blue">{record.skin} · {record.scene}</Badge></div><EvidenceText text={record.review_text} evidence={feature.evidence}/><div className="lineage"><span>观点：{feature.category} / {SENTIMENT[feature.sentiment]}</span><span>feature_id：{feature.feature_id}</span><span>{feature.audit_status}</span></div></article>) : <Empty>没有匹配的证据记录。</Empty>}</div>
      </div>
    </section>
  </div>;
}

function MethodPage({snapshot}) {
  const statuses = [
    ['Schema 结构校验', snapshot.qa.schema_valid, '字段、枚举、切片与关系完整'],
    ['证据原文校验', snapshot.qa.evidence_valid, '每条证据必须是评论原文子串'],
    ['数量守恒校验', snapshot.qa.counts_consistent, 'KEEP / FILTER / PENDING / ERROR 可解释'],
  ];
  return <div data-testid="page-method">
    <div className="page-heading"><div><span className="kicker">METHOD & LIMITS</span><h2>流程透明，能力边界也透明</h2><p>五层真正运行；未启用的能力不使用装饰性数字代替。</p></div><Badge tone="blue">run_id · {snapshot.run_id}</Badge></div>
    <div className="pipeline">{snapshot.stages.map((stage, index) => <React.Fragment key={stage.layer}><article><div><span>L{stage.layer}</span><CheckCircle2 size={18}/></div><h3>{stage.name}</h3><p>{stage.input_count.toLocaleString()} 输入 → {stage.output_count.toLocaleString()} 输出</p><small>{stage.duration_ms} ms · {stage.mode}</small></article>{index < 4 && <ArrowRight className="pipe-arrow"/>}</React.Fragment>)}</div>
    <div className="two-col quality-grid"><section className="panel"><div className="panel-title"><div><span className="title-dot teal"/><h3>已执行质量检查</h3></div></div>{statuses.map(([label, ok, note]) => <div className="check-row" key={label}><CheckCircle2/><div><strong>{label}</strong><span>{note}</span></div><Badge>{ok ? '通过' : '未通过'}</Badge></div>)}</section>
      <section className="panel"><div className="panel-title"><div><span className="title-dot coral"/><h3>明确未启用</h3></div></div>{[['AI 模型评测', '没有独立人工 Gold，不能显示 F1'], ['真实时间趋势', '样本没有真实发布时间'], ['自动聚类', '首版使用 13 类固定演示规则'], ['真实业务结论', 'business_count = 0']].map(([label,note]) => <div className="limit-row" key={label}><TriangleAlert/><div><strong>{label}</strong><span>{note}</span></div><Badge tone="gray">未启用</Badge></div>)}</section></div>
    <section className="scope-note"><FlaskConical/><div><h3>这版能证明什么？</h3><p>能证明从原始输入、清洗、观点、指标、证据到页面快照的工程闭环；不能证明对真实消费者评论的模型泛化能力，也不能直接支持珀莱雅业务决策。</p></div></section>
  </div>;
}

function AdminPage({snapshot, health, refresh}) {
  const enabled = health?.management_enabled === true;
  const [runs, setRuns] = useState([]);
  const [message, setMessage] = useState('');
  const [review, setReview] = useState({record_id: snapshot.records.find(r => r.final_action === 'KEEP')?.record_id ?? '', action:'KEEP', note:''});
  useEffect(() => { if (enabled) fetch('/api/runs', {cache:'no-store'}).then(r => r.ok ? r.json() : {runs:[]}).then(x => setRuns(x.runs ?? [])).catch(()=>{}); }, [enabled]);
  async function startRun() {
    setMessage('正在建立新运行…');
    try { const r = await fetch('/api/runs', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'}); const data=await r.json(); setRuns(old => [data, ...old.filter(x => x.run_id !== data.run_id)]); setMessage('任务已进入队列，可稍后刷新查看新快照。'); }
    catch { setMessage('本机运行服务暂时不可用。'); }
  }
  async function submitReview(event) {
    event.preventDefault();
    if (!review.note.trim()) { setMessage('请先填写复核理由。'); return; }
    try {
      const response = await fetch('/api/reviews', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(review)});
      if (!response.ok) throw new Error('review');
      setReview(old => ({...old, note:''}));
      setMessage('复核动作已追加保存；重新运行后进入新快照。');
    } catch { setMessage('复核暂未保存，请确认本机管理服务仍在运行。'); }
  }
  return <div data-testid="page-admin">
    <div className="page-heading"><div><span className="kicker">LOCAL OPERATIONS</span><h2>内部运行台</h2><p>用于证明流程可重跑、可审计；普通公开快照不开放写操作。</p></div><Badge tone={enabled?'teal':'gray'}>{enabled ? '本机管理已启用' : '只读模式'}</Badge></div>
    {!enabled ? <section className="locked"><ShieldCheck/><div><h3>当前是公开只读视图</h3><p>运行、审核与同步功能只在同源本机服务连接后出现。</p></div></section> : <>
      <div className="admin-actions"><section className="panel run-card"><div><Play/><span><strong>重新运行五层流程</strong><small>新建 run_id，保留旧运行，不覆盖历史。</small></span></div><button onClick={startRun} data-testid="start-run">开始新运行</button></section><section className="panel run-card"><div><FileCheck2/><span><strong>当前发布快照</strong><small>{snapshot.snapshot_id}</small></span></div><button className="secondary" onClick={refresh}>刷新状态</button></section></div>
      {message && <p className="action-message">{message}</p>}
      <div className="admin-grid"><section className="panel"><div className="panel-title"><div><span className="title-dot blue"/><h3>最近运行</h3></div><small>仅显示必要状态</small></div><div className="run-table"><div className="run-row head"><span>运行编号</span><span>模式</span><span>时间</span><span>状态</span></div>{runs.slice(0,8).map(run => <div className="run-row" key={run.run_id}><span>{run.run_id}</span><span>{run.mode}</span><span>{(run.generated_at || run.started_at || '').replace('T',' ').slice(0,19)}</span><span><Badge tone={run.status==='COMPLETED'?'teal':run.status==='FAILED'?'amber':'blue'}>{run.status}</Badge></span></div>)}</div></section>
      <section className="panel review-panel"><div className="panel-title"><div><span className="title-dot teal"/><h3>人工复核</h3></div><small>只追加，不覆盖旧记录</small></div><form onSubmit={submitReview}><label><span>记录编号</span><input value={review.record_id} onChange={e=>setReview({...review,record_id:e.target.value})}/></label><label><span>复核动作</span><select value={review.action} onChange={e=>setReview({...review,action:e.target.value})}><option value="KEEP">KEEP · 保留</option><option value="FILTER">FILTER · 过滤</option></select></label><label className="review-note"><span>复核理由</span><input value={review.note} onChange={e=>setReview({...review,note:e.target.value})} placeholder="说明证据与判断理由" maxLength={1000}/></label><button type="submit">追加复核动作</button><p>动作在下一次运行生成的新快照中生效。</p></form></section></div>
      <section className="admin-boundary"><ShieldCheck/><div><strong>Supabase 同步未执行</strong><span>本地五层映射 dry-run 已通过；连接、建表和公开发布需要指定项目授权。</span></div></section>
    </>}
  </div>;
}

export default function App() {
  const [state, setState] = useState({loading:true, snapshot:null, health:null, error:false});
  const [page, setPage] = useState('insights');
  const [filters, setFilters] = useState({product:'全部', skin:'全部', scene:'全部'});
  const [selectedMetric, setSelectedMetric] = useState(null);
  const refresh = () => { setState(old=>({...old,loading:true})); loadData().then(({snapshot,health}) => setState({loading:false,snapshot,health,error:false})).catch(()=>setState({loading:false,snapshot:null,health:null,error:true})); };
  useEffect(refresh, []);
  const index = useMemo(() => buildEvidenceIndex(state.snapshot?.records), [state.snapshot]);
  if (state.loading) return <div className="splash"><Sparkles/><h1>正在装载洞察快照</h1><p>验证数据身份与证据关系…</p></div>;
  if (state.error || !state.snapshot) return <div className="splash error"><TriangleAlert/><h1>暂时无法读取演示快照</h1><button onClick={refresh}>重新尝试</button></div>;
  const {snapshot, health} = state;
  const slice = getSlice(snapshot, filters.product, filters.skin, filters.scene);
  const openMetric = metric => { if (metric) { setSelectedMetric(metric); setPage('evidence'); window.scrollTo({top:0,behavior:'smooth'}); } };
  return <div className="app-shell"><Sidebar page={page} setPage={setPage}/><div className="workspace"><Header snapshot={snapshot} source={health ? 'dynamic':'static'}/><main>
    {page === 'insights' && <InsightPage snapshot={snapshot} slice={slice} filters={filters} setFilters={setFilters} openMetric={openMetric}/>}
    {page === 'evidence' && <EvidencePage snapshot={snapshot} selectedMetric={selectedMetric} setSelectedMetric={setSelectedMetric} index={index}/>}
    {page === 'method' && <MethodPage snapshot={snapshot}/>}
    {page === 'admin' && <AdminPage snapshot={snapshot} health={health} refresh={refresh}/>}
  </main><footer><span>Consumer Insight Demo 2.0</span><span>synthetic_demo · pipeline_test · business_count 0</span></footer></div></div>;
}
