'use strict';
const $ = id => document.getElementById(id);
const nodeCards = new Map();
function text(tag, value, className) {
  const el = document.createElement(tag); el.textContent = value;
  if (className) el.className = className;
  return el;
}
function metric(label, value) {
  const el = text('div', '', 'metric'); el.append(text('small', label), text('strong', value)); return el;
}
async function post(path, body = {}) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data;
}
async function act(path, body) {
  try { await post(path, body); $('notice').textContent = ''; await refresh(); }
  catch (error) { $('notice').textContent = error.message; }
}
function card(n, online) {
  let c=nodeCards.get(n.node);
  if(!c){
    const root=text('article','','node');
    const header=text('div','','node-header');
    const name=text('div','');
    name.append(text('span',n.node===1?'WIRE · 0x21 · NORMAL SOURCE':'WIRE1 · 0x22 · BUTTON SOURCE','eyebrow'),text('h2',`Xenon ${n.node}`));
    const badge=text('span','','status');header.append(name,badge);
    const metrics=text('div','','metrics');metrics.append(metric('RECEIVED',0),metric('ALLOWED',0),metric('BLOCKED',0));
    const rates=text('div','','rates');
    const observed=text('span',''),learned=text('span','');rates.append(observed,learned);
    const canvas=document.createElement('canvas');canvas.width=520;canvas.height=100;canvas.className='graph';canvas.setAttribute('aria-label','Recent observed application-message rate');canvas.setAttribute('role','img');
    const fresh=text('div','','freshness'),diagnostics=text('div','','freshness');
    const controls=text('div','','actions');const buttons=[];
    for(const [op,label] of [['quarantine','Quarantine 15s'],['release','Release']]){
      const button=text('button',label,'secondary');
      button.onclick=()=>act('/api/command',{node:n.node,op,duration_ms:op==='quarantine'?15000:0});
      controls.append(button);buttons.push(button);
    }
    const pending=text('span','','muted');controls.append(pending);
    const alert=text('p','');alert.hidden=true;
    root.append(header,metrics,rates,canvas,fresh,diagnostics,controls,alert);
    c={root,badge,metrics,observed,learned,canvas,fresh,diagnostics,buttons,pending,alert};nodeCards.set(n.node,c);
    $('nodes').append(root);
  }
  c.badge.textContent=n.state;c.badge.dataset.state=n.state;
  ['received','allowed','blocked'].forEach((key,i)=>{c.metrics.querySelectorAll('strong')[i].textContent=n.totals[key];});
  c.observed.textContent=`Observed ${n.rate.toFixed(2)} msg/s`;
  c.learned.textContent=n.baseline?`Learned ${n.baseline.mean.toFixed(2)} · limit ${n.baseline.threshold.toFixed(2)}`:'Baseline not trained';
  const age=x=>x===null?'never':`${(x/1000).toFixed(1)}s ago`;
  c.fresh.textContent=`Bus response: ${age(n.seen_age_ms)} · Message: ${age(n.message_age_ms)} · Quarantine: ${(n.quarantine_ms/1000).toFixed(1)}s`;
  const interval=n.interval;
  c.diagnostics.textContent=`Last interval · transport ${interval.transport??0} · empty ${interval.empty??0} · queue overflow ${interval.queue_overflow??0}`;
  c.buttons.forEach(b=>{b.disabled=!online||!!n.pending;});
  c.pending.textContent=n.pending?`${n.pending.wire.op}: awaiting acknowledgment`:'';
  c.alert.hidden=!n.alert;c.alert.textContent=n.alert?n.alert.reason:'';
  const ctx=c.canvas.getContext('2d'),history=n.history,max=Math.max(5,...history);
  ctx.clearRect(0,0,520,100);ctx.strokeStyle='#24404d';ctx.beginPath();ctx.moveTo(0,85);ctx.lineTo(520,85);ctx.stroke();
  ctx.strokeStyle='#5be0b3';ctx.lineWidth=2;ctx.beginPath();history.forEach((v,i)=>{const x=i/Math.max(1,history.length-1)*520,y=85-v/max*70;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.stroke();
}

function render(s) {
  $('mode').textContent=s.mode;
  $('gateway').textContent=s.gateway_online?`Gateway connected · session ${s.session}`:'Gateway OFFLINE · waiting for fresh summary';
  s.nodes.forEach(n=>card(n,s.gateway_online));
  $('simulation').hidden=s.mode!=='SIMULATION';
  if(s.simulation_mode && document.activeElement!==$('sim-mode')) $('sim-mode').value=s.simulation_mode;
  $('auto').checked=s.auto_containment;
  const d=s.detector;
  $('training').textContent=d.training?`Clean windows: node 1 ${d.windows['1']}/12 · node 2 ${d.windows['2']}/12`:(Object.keys(d.baselines).length?'Baseline frozen · detection active':'No baseline learned');
  $('threshold').textContent=`${d.z} standard deviations above learned rate · σ floor ${d.sigma_floor} msg/s · two complete windows · rejected intervals ${d.rejected_intervals['1']} / ${d.rejected_intervals['2']}`;
  $('finish').disabled=!d.training;$('train').disabled=d.training||!s.gateway_online;
  $('diagnostics').textContent=`Bad serial lines ${s.malformed_lines} · gateway log drops ${s.log_drops}`;
  const rows=s.incidents.map(i=>{const tr=document.createElement('tr');tr.append(text('td',new Date(i.time*1000).toLocaleTimeString()),text('td',i.node?`Xenon ${i.node}`:'Gateway'),text('td',i.reason));return tr;});
  $('incidents').replaceChildren(...rows);
  $('commands').replaceChildren(...s.commands.slice(0,5).map(c=>text('div',`#${c.wire.id} · Xenon ${c.wire.node} · ${c.wire.op} · ${c.status}${c.error?' · '+c.error:''}`)));
}
let fetching=false;
async function refresh(){
  if(fetching)return;fetching=true;
  try{const r=await fetch('/api/state');if(!r.ok)throw new Error('Backend unavailable');render(await r.json());}
  catch(e){$('gateway').textContent='Backend OFFLINE';$('notice').textContent=e.message;document.querySelectorAll('#nodes button').forEach(b=>b.disabled=true);document.querySelectorAll('.status').forEach(b=>{b.textContent='OFFLINE';b.dataset.state='OFFLINE';});}
  finally{fetching=false;}
}
$('train').onclick=()=>act('/api/training/start');
$('finish').onclick=()=>act('/api/training/finish');
$('auto').onchange=()=>act('/api/auto',{enabled:$('auto').checked});
$('sim-mode').onchange=()=>act('/api/simulation/mode',{mode:$('sim-mode').value});
refresh();setInterval(refresh,500);
