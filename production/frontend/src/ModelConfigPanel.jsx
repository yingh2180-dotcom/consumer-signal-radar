import {useEffect,useRef,useState} from 'react';
import {Cpu,ExternalLink,Minus,RefreshCw,X} from 'lucide-react';

export function getModelConfigStatus(settings){
  if(!settings)return {label:'状态未知',tone:'unknown'};
  if(!settings.configured)return {label:'待配置',tone:'pending'};
  if(settings.paid_enabled)return {label:'已启用',tone:'enabled'};
  return {label:'已配置',tone:'configured'};
}

export function ModelConfigLauncher({settings,onOpen,launcherRef}){
  const status=getModelConfigStatus(settings);
  return <button ref={launcherRef} className="model-config-launcher" aria-label={'模型配置，'+status.label} onClick={onOpen}>
    <Cpu size={17}/><span className="model-config-launcher-text">模型配置</span>
    <span className={'model-status-dot '+status.tone} aria-hidden="true"/>
    <span className="model-config-launcher-text">{status.label}</span>
  </button>;
}

function ValueRow({label,value}){
  return <div className="model-config-value"><span>{label}</span><strong>{value||'未配置'}</strong></div>;
}

export default function ModelConfigPanel({settings,view,setView,onRefresh,onSave,refreshing,launcherRef}){
  const panelRef=useRef(null);
  const closeButtonRef=useRef(null);
  const[apiKey,setApiKey]=useState('');
  const[baseUrl,setBaseUrl]=useState('https://dashscope.aliyuncs.com/compatible-mode/v1');
  const[model,setModel]=useState('qwen3.5-plus');
  const[embeddingModel,setEmbeddingModel]=useState('text-embedding-v4');
  const[paidEnabled,setPaidEnabled]=useState(false);
  const[saveMessage,setSaveMessage]=useState(null);
  useEffect(()=>{if(!settings)return;setBaseUrl(settings.base_url||'https://dashscope.aliyuncs.com/compatible-mode/v1');setModel(settings.model||'qwen3.5-plus');setEmbeddingModel(settings.embedding_model||'text-embedding-v4');setPaidEnabled(Boolean(settings.paid_enabled))},[settings]);
  useEffect(()=>{if(view!=='open'){setApiKey('');setSaveMessage(null)}},[view]);
  const leave=next=>{setView(next);requestAnimationFrame(()=>launcherRef?.current?.focus())};
  useEffect(()=>{
    if(view!=='open')return undefined;
    const background=[document.querySelector('.sidebar'),document.querySelector('.main')].filter(Boolean);
    background.forEach(element=>element.setAttribute('inert',''));
    const focusable=()=>[...panelRef.current.querySelectorAll('button,a[href],input,select')].filter(element=>!element.disabled);
    closeButtonRef.current?.focus();
    const handleKey=event=>{
      if(event.key==='Escape'){leave('closed');return}
      if(event.key!=='Tab')return;
      const items=focusable();if(!items.length)return;
      const first=items[0],last=items[items.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
    };
    window.addEventListener('keydown',handleKey);
    return()=>{window.removeEventListener('keydown',handleKey);background.forEach(element=>element.removeAttribute('inert'))};
  },[view]);

  const status=getModelConfigStatus(settings);
  if(view==='closed')return null;
  if(view==='minimized')return <button className="model-config-mini" onClick={()=>{setView('open');onRefresh()}}>
    <Cpu size={17}/><span>模型配置</span><span className={'model-status-dot '+status.tone} aria-hidden="true"/>
  </button>;

  const configuredText=!settings?'等待本机服务返回状态':settings.configured?'已检测到完整配置':'尚未完成配置';
  const paidText=!settings?'状态未知':settings.paid_enabled?(settings.configured?'已开启，真实模型可在分析页授权后使用':'已开启，但配置不完整，仍不可调用'):'未开启，当前仅可使用离线流程';
  return <div className="model-config-layer">
    <button className="model-config-backdrop" aria-label="关闭模型配置面板" onClick={()=>leave('closed')}/>
    <aside ref={panelRef} className="model-config-panel" role="dialog" aria-modal="true" aria-labelledby="model-config-title">
      <header className="model-config-header">
        <div><span className="model-config-kicker"><Cpu size={16}/>本机服务设置</span><h2 id="model-config-title">模型 API 配置</h2></div>
        <div className="model-config-header-actions">
          <button className="model-config-icon-button" onClick={()=>leave('minimized')} aria-label="缩小模型配置面板"><Minus size={18}/></button>
          <button ref={closeButtonRef} className="model-config-icon-button" onClick={()=>leave('closed')} aria-label="关闭模型配置面板"><X size={18}/></button>
        </div>
      </header>

      <div className="model-config-content">
        <section className="model-config-status-card">
          <div><span className={'model-status-dot '+status.tone} aria-hidden="true"/><strong>{status.label}</strong></div>
          <p>{!settings?'无法读取设置，请检查本机服务是否正在运行。':status.tone==='enabled'?'配置已检测，真实模型仍需完成项目质量验收。':status.tone==='configured'?'配置已检测，但计费调用尚未开启。':'请在本机服务端完成模型和密钥配置。'}</p>
        </section>

        <form className="model-config-section model-config-form" onSubmit={async event=>{event.preventDefault();setSaveMessage(null);try{await onSave({api_key:apiKey,base_url:baseUrl.trim(),model:model.trim(),embedding_model:embeddingModel.trim(),paid_enabled:paidEnabled});setApiKey('');setSaveMessage({type:'success',text:'配置已安全保存。API Key 输入框已清空。'})}catch(error){setSaveMessage({type:'error',text:error.message})}}}>
          <h3>填写并保存配置</h3>
          <label><span>API Key</span><input type="password" autoComplete="new-password" value={apiKey} onChange={event=>setApiKey(event.target.value)} placeholder={settings?.key_configured?'留空可保留已保存的 Key':'请输入百炼 API Key'} aria-describedby="api-key-help" required={!settings?.key_configured}/></label>
          <small id="api-key-help">密钥只提交给这台电脑上的后端，并保存到本项目的本机环境文件。接口不会返回或显示密钥。</small>
          <label><span>服务地址</span><input type="url" value={baseUrl} onChange={event=>setBaseUrl(event.target.value)} required/></label>
          <label><span>文本模型</span><input value={model} onChange={event=>setModel(event.target.value)} required/></label>
          <label><span>向量模型</span><input value={embeddingModel} onChange={event=>setEmbeddingModel(event.target.value)} required/></label>
          <label className="model-config-paid"><input type="checkbox" checked={paidEnabled} onChange={event=>setPaidEnabled(event.target.checked)}/><span><strong>允许真实模型计费调用</strong><small>开启后，分析任务可调用百炼模型，并受项目 20 元预算上限约束。</small></span></label>
          {saveMessage&&<p className={'model-config-save-message '+saveMessage.type} role="status">{saveMessage.text}</p>}
          <button className="primary model-config-save" disabled={refreshing}>{refreshing?'正在保存…':'保存模型配置'}</button>
        </form>

        <section className="model-config-section">
          <div className="model-config-section-heading"><h3>当前状态</h3><button onClick={onRefresh} disabled={refreshing}><RefreshCw className={refreshing?'spin':''} size={15}/>{refreshing?'刷新中':'刷新状态'}</button></div>
          <div className="model-config-values">
            <ValueRow label="文本模型" value={settings?.model}/>
            <ValueRow label="向量模型" value={settings?.embedding_model}/>
            <ValueRow label="API 配置" value={configuredText}/>
            <ValueRow label="计费调用" value={paidText}/>
            <ValueRow label="单次导入上限" value={settings?.max_rows ? `${settings.max_rows.toLocaleString()} 条` : '状态未知'}/>
          </div>
          <p className="model-config-budget">预算说明：真实模型调用以本机 20 元预算为上限，请在分析前确认数据发送范围和模型价格。</p>
        </section>

        <section className="model-config-section">
          <h3>模型清单</h3>
          <div className="model-config-models">
            <div><strong>文本模型 <span>必需</span></strong><b>qwen3.5-plus</b><p>评论结构化抽取与口语语义理解。</p></div>
            <div><strong>向量模型 <span>必需</span></strong><b>text-embedding-v4</b><p>评论向量化与探索性聚类。</p></div>
            <div><strong>重排模型 <span className="optional">当前不需要</span></strong><b>qwen3-rerank</b><p>未来用于语义检索结果二次排序。</p></div>
          </div>
          <p className="model-config-note">qwen-turbo 可作为后续低成本备选；当前预算校验尚未配置其价格，切换前需先更新后端计费白名单并重新进行金标评测。</p>
        </section>

        <section className="model-config-section model-config-setup">
          <h3>获取与配置</h3>
          <ol><li>在阿里云百炼控制台创建 API Key，并确认所选地域。</li><li>在上方表单填写 Key 和模型信息，然后保存。</li><li>状态会立即刷新，无需手工编辑配置文件。</li></ol>
          <div className="model-config-links">
            <a href="https://help.aliyun.com/zh/model-studio/get-api-key" target="_blank" rel="noreferrer">查看 API Key 官方说明<ExternalLink size={15}/></a>
            <a href="https://help.aliyun.com/zh/model-studio/model-pricing" target="_blank" rel="noreferrer">查看百炼模型与价格<ExternalLink size={15}/></a>
          </div>
          <p className="model-config-security">为保护密钥，页面仅允许写入；保存后不会读取、回显或记录 API Key。</p>
        </section>
      </div>
    </aside>
  </div>;
}
