import {combinations,datasets} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {table} from '../components/common/table.js';
import {esc,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';

const canEdit=()=>session.user.role!=='viewer';

function datasetPicker(list,selected=[]){
 return '<div class="batch-checks">'+list.map(d=>'<label class="batch-check"><input type="checkbox" name="dataset" value="'+d.id+'" '+(selected.includes(d.id)?'checked':'')+'><span><strong>'+esc(d.name)+'</strong><small>'+d.rows+' 条 · '+esc(d.observation_date||'未标注日期')+' · SHA256 '+esc(d.checksum.slice(0,12))+'…</small></span></label>').join('')+'</div>';
}

function combinationCard(c){
 const v=c.current_version;
 return '<button class="batch-item combination-item" data-combination="'+c.id+'"><strong>'+esc(c.name)+'</strong><span>'+(v?'v'+v.version_no+' · '+v.sample_count+' 条样本 · '+v.dataset_ids.length+' 个批次':'尚无已发布版本')+'</span><small>'+(v?'样本指纹 '+esc(v.sample_checksum.slice(0,18))+'…':'冲突未解决，不能用于计算')+'</small></button>';
}

function summaryPanel(c){
 if(!c)return '<p class="empty">选择左侧组合查看按日期的样本构成与冲突。</p>';
 const current=c.current_version,latest=c.latest_version;
 const meta=(latest?.dataset_meta||current?.dataset_meta||[]);
 return '<div class="section-title"><h2>'+esc(c.name)+'</h2><span>'+(c.published?'当前版本已发布':'最新版本未发布')+'</span></div>'+
   '<div class="metrics compact-metrics">'+[[latest?.version_no!=null?'最新版本':'—','v'+(latest?.version_no??'—')],['样本数',latest?.sample_count??0],['冲突键',latest?.conflict_count??0],['已解决',latest?.resolved_count??0],['观测日数',latest?.stats?.dates?.length??0]].map(([k,v])=>'<div><span>'+k+'</span><strong>'+esc(v)+'</strong></div>').join('')+'</div>'+
   '<div class="two-columns tight"><div><h3>参与批次</h3>'+(meta.length?'<ul class="plain">'+meta.map(d=>'<li><strong>'+esc(d.name)+'</strong><span>'+esc(d.observation_date||'未标注日期')+' · '+d.rows+' 条 · '+esc(d.checksum.slice(0,14))+'…</span></li>').join('')+'</ul>':'<p class="empty">尚未选择批次。</p>')+'</div><div><h3>日期与样本</h3>'+((latest?.stats?.per_date||[]).length?'<ul class="plain">'+latest.stats.per_date.map(p=>'<li><strong>'+esc(p.date)+'</strong><span>'+p.rows+' 条 · 来源批次 '+p.dataset_ids.map(i=>'#'+i).join('、')+'</span></li>').join('')+'</ul>':'<p class="empty">尚无样本。</p>')+'</div></div>'+
   (latest?.stats?.collapsed_rows?'<p class="hint">同站同日同时段重复观测已合并 '+latest.stats.collapsed_rows+' 条，仅计一次。</p>':'')+
   (latest?.stale_resolutions?.length?'<p class="warning">有 '+latest.stale_resolutions.length+' 个旧来源选择因冲突内容变化已失效，未套用到新的冲突上。请在本页重新选择来源后保存新版本。</p>':'')+
   '<p class="hint">样本指纹 '+esc(latest?.sample_checksum||'—')+'。计算任务会锁定提交时的完整样本；此后修改组合不会影响排队中的研究。</p>';
}

function conflictPanel(c){
 const latest=c?.latest_version;if(!latest)return '';
 if(!latest.conflicts.length)return '<section class="panel"><div class="section-title"><h2>数值冲突</h2><span>无</span></div><p class="empty">组合内没有同站同日同时段的不同数值，可直接用于计算。</p></section>';
 const conflicts=latest.conflicts;
 const stale=new Set((latest.stale_resolutions||[]).map(x=>x.key));
 const byDate={};conflicts.forEach(x=>{(byDate[x.observation_date]??=[]).push(x);});
 return '<section class="panel"><div class="section-title"><h2>数值冲突</h2><span>'+conflicts.length+' 个键 · 点击行定位</span></div>'+
  '<p class="hint">同一站点、日期、时段的观测在多个批次中数值不同。必须指定采用哪个来源批次，组合才可发布并计算。来源核对见每行的对照。</p>'+
  '<div class="conflict-index"><span>定位：</span>'+Object.entries(byDate).sort().map(([day,items])=>'<button class="small" data-jump="conflict-day-'+esc(day)+'">'+esc(day)+' · '+items.length+'</button>').join('')+'</div>'+
  '<p class="hint">在每对样本中选择采用来源，然后点击左侧“保存新版本”使该版本发布。未发布的组合不能被计算任务使用。</p>'+
  '<div class="conflict-list">'+Object.entries(byDate).sort().map(([day,items])=>'<article class="conflict-day" id="conflict-day-'+esc(day)+'"><header><strong>'+esc(day)+'</strong><span>'+items.length+' 个冲突</span></header>'+items.map(x=>
    '<details class="conflict'+(stale.has(x.key)?' stale':'')+'" id="conflict-'+esc(x.key.replace(/[^\w一-龥-]/g,'_'))+'" '+(stale.has(x.key)?'open':'')+'><summary><span>'+esc(x.station)+' · 时段 '+esc(x.period)+'</span><span>'+(stale.has(x.key)?'旧来源选择已失效，请重新选择':'')+' · '+x.pairs.length+' 组对照 · 需选择来源</span></summary>'+
     '<div class="conflict-body"><div class="pair-list">'+x.pairs.map(p=>'<div class="pair"><div><small>来源 A</small><strong>'+esc(p.left.dataset_name)+'</strong><span>commute '+esc(p.left.commute)+' · arrivals '+esc(p.left.arrivals)+' · demand '+esc(p.left.demand)+'</span><code>'+esc(p.left.dataset_checksum.slice(0,16))+'…</code></div><div><small>来源 B</small><strong>'+esc(p.right.dataset_name)+'</strong><span>commute '+esc(p.right.commute)+' · arrivals '+esc(p.right.arrivals)+' · demand '+esc(p.right.demand)+'</span><code>'+esc(p.right.dataset_checksum.slice(0,16))+'…</code></div><em>差异字段：'+esc(p.differences.join('、'))+'</em></div>').join('')+'</div>'+
     '<label>采用来源<select data-resolution="'+esc(x.key)+'" data-signature="'+esc(x.signature)+'">'+x.candidates.map(d=>'<option value="'+d.dataset_id+'">'+esc(d.dataset_name)+' · '+esc(d.dataset_checksum.slice(0,12))+'…</option>').join('')+'</select></label></div></details>').join('')+'</article>').join('')+'</div>'+
  '<div class="section-title"><h2>已确认的来源</h2><span>'+(latest.resolutions?Object.keys(latest.resolutions).length:0)+' 项</span></div>'+
  (Object.keys(latest.resolutions||{}).length?'<div class="table-wrap small-table">'+table([{key:'key',label:'冲突键'},{key:'dataset',label:'采用来源'},{key:'signature',label:'冲突指纹'}],Object.entries(latest.resolutions).map(([k,v])=>({key:k,dataset:'#'+v.dataset_id,signature:String(v.signature||'').slice(0,12)+'…'})))+'</div>':'<p class="empty">尚未确认任何来源。</p>')+
  '</section>';
}

export async function combinationPage(id){
 const [list,datasetList]=await Promise.all([combinations.list(),datasets.list()]);
 workspace.combinations=list;workspace.datasets=datasetList;
 const selected=id?await combinations.get(id):(list[0]?await combinations.get(list[0].id):null);
 if(selected)workspace.combinationFormState=null;
 const m=workspace.meta;
 return heading('02B / COMBINATION','按日期组合批次','把分散在多批的观测按观测日期合成同一研究样本：缺口不跨日配对，同站同日同时段只计一次，数值冲突必须选择来源。','<a class="button" href="#/datasets">接入新批次 ↗</a>')+
  '<div class="dataset-grid"><section class="panel"><div class="section-title"><h2>研究组合</h2><span>'+list.length+' 个</span></div><div class="batch-list combination-list">'+(list.map(combinationCard).join('')||'<p class="empty">还没有组合。先在右侧选择批次并保存。</p>')+'</div>'+
  '<div class="section-title"><h2>'+(selected?'修改组合':'新建组合')+'</h2></div>'+
  '<form id="combination-form" data-id="'+(selected?selected.id:'')+'"><label>组合名称<input name="name" required minlength="2" value="'+esc(selected?.name||'整周观察组合')+'" '+(selected?'readonly':'')+'></label>'+
  '<p class="hint">选择批次（按观测日期合并，同站同日同时段重复只保留一份）：</p>'+datasetPicker(datasetList,selected?.latest_version?.dataset_ids||selected?.current_version?.dataset_ids||[])+
  '<button type="submit" class="primary" '+(canEdit()?'':'disabled')+'>'+(selected?'保存新版本':'创建组合')+'</button><p class="hint">保存会立即解析样本并编号为新版本；有冲突的版本不会发布，也不会被计算使用。</p></form></section>'+
  '<section class="panel"><div id="combination-summary">'+summaryPanel(selected)+'</div>'+
  (selected?'<div id="combination-conflicts">'+conflictPanel(selected)+'</div>':'')+'</section></div>';
}

function resolutionMap(){
 const state={};
 document.querySelectorAll('[data-resolution]').forEach(select=>{state[select.dataset.resolution]={dataset_id:Number(select.value),signature:select.dataset.signature};});
 return state;
}


export function bindCombinations(refresh){
 document.querySelectorAll('[data-combination]').forEach(b=>b.onclick=()=>{location.hash='#/combinations/'+b.dataset.combination;});
 document.querySelectorAll('[data-jump]').forEach(b=>b.onclick=()=>{const target=document.getElementById(b.dataset.jump);if(!target)return;target.scrollIntoView({behavior:'smooth',block:'start'});const first=target.querySelector('details');if(first)first.open=true;notify('已定位到 '+b.dataset.jump.replace('conflict-day-','')+' 的冲突，请核对每对样本来源');});
 const form=document.querySelector('#combination-form');
 if(!form)return;
 submit(form,async f=>{
  const id=form.dataset.id;
  const ids=[...form.querySelectorAll('input[name=dataset]:checked')].map(x=>Number(x.value));
  if(!ids.length)throw new Error('请至少选择一个数据批次');
  const current=id?await combinations.get(id):null;
  // Only choices that still match the current conflict signature are sent.
  // A stale choice is deliberately NOT re-applied; the conflict below must be
  // reviewed and picked again for the new candidate set.
  const resolutions={...(current?.latest_version?.resolutions||{}),...resolutionMap()};
  if(id){const r=await combinations.revise(id,{dataset_ids:ids,resolutions});const v=r.latest_version;notify(r.published?'新版本 v'+v.version_no+' 已发布，可用于计算':'新版本 v'+v.version_no+' 仍有 '+v.conflict_count+' 个冲突未解决，组合暂不可用于计算');}
  else{const r=await combinations.create({name:f.get('name'),dataset_ids:ids,resolutions});const v=r.latest_version;notify(r.published?'组合已创建并发布 v1，可用于计算':'组合已创建，但仍有 '+v.conflict_count+' 个冲突未解决，暂不可用于计算');}
  await refresh();
 });
}
