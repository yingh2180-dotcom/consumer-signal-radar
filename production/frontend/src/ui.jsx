import React from 'react';
import {Inbox,LoaderCircle} from 'lucide-react';
export function Empty({title='这里还没有内容',children}){return <div className="empty"><Inbox size={36}/><h3>{title}</h3>{children&&<p>{children}</p>}</div>}
export function Notice({children,type='info'}){return <div className={'notice '+type} role={type==='error'?'alert':'status'}>{children}</div>}
export function Busy(){return <div className="empty"><LoaderCircle className="spin"/>正在读取…</div>}
export function Field({label,children}){return <label className="field"><span>{label}</span>{children}</label>}
export function Table({columns,rows}){return <div className="table-scroll"><table><thead><tr>{columns.map(c=><th key={c.key}>{c.label}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={r.id||i}>{columns.map(c=><td key={c.key}>{c.render?c.render(r):(r[c.key]??'—')}</td>)}</tr>)}</tbody></table>{!rows.length&&<Empty title="暂无记录"/>}</div>}
