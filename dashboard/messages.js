'use strict';
const el=id=>document.getElementById(id);
let sending=false, readerKey='', polling=false, addressInitialized=false;
async function copyCode(inputId, label) {
  const input=el(inputId);
  if(!input.value){el('copy-status').textContent='Wait for the codes to load.';return;}
  try {
    await navigator.clipboard.writeText(input.value);
    el('copy-status').textContent=`${label} copied. Paste it with Ctrl+V or Command+V.`;
  } catch {
    input.focus();input.select();
    el('copy-status').textContent=`Automatic copying is unavailable. ${label} selected: press Ctrl+C or Command+C.`;
  }
}
el('copy-sender').addEventListener('click',()=>copyCode('sender-code','Sender code'));
el('copy-reader').addEventListener('click',()=>copyCode('reader-code','Inbox code'));
el('lan-form').addEventListener('submit',async event=>{
  event.preventDefault();el('save-address').disabled=true;
  try {
    await api('/api/messages/lan-address',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({address:el('lan-address').value.trim()})});
    el('lan-status').textContent='Address updated. Give your partner the new page address below. Codes and inbox are unchanged.';
    await refresh();
  } catch(error){el('lan-status').textContent=error.message;}
  finally{el('save-address').disabled=false;}
});
async function api(url, options={}) {
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),7000);
  try {
    const response=await fetch(url,{...options,signal:controller.signal});
    const data=await response.json();
    if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:'Request rejected');
    return data;
  } finally {clearTimeout(timer);}
}
el('message').addEventListener('input',()=>{
  el('bytes').textContent=`${new TextEncoder().encode(el('message').value).length} / 160 UTF-8 bytes`;
});
el('send-form').addEventListener('submit',async event=>{
  event.preventDefault();if(sending)return;
  sending=true;el('send').disabled=true;el('result').dataset.status='pending';
  el('result').textContent='Waiting for the gateway’s decision…';
  try {
    const data=await api('/api/messages/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:el('message').value,key:el('sender-key').value.trim()})});
    el('result').dataset.status=data.status;
    const source=data.source==='SIMULATION'?'Software simulator':'Argon';
    el('result').textContent=data.status==='delivered'?`${source} allowed this message. Added to the partner inbox.`:data.status==='blocked'?`${source} blocked this message: ${data.reason.replaceAll('_',' ')}.${data.quarantine_ms?' Quarantine remaining: '+Math.ceil(data.quarantine_ms/1000)+' seconds.':''}`:data.reason;
  } catch(error){el('result').textContent=`Delivery not confirmed: ${error.message}. Check the inbox before sending again.`;}
  finally{sending=false;await refresh();}
});
el('inbox-form').addEventListener('submit',event=>{event.preventDefault();readerKey=el('inbox-key').value.trim();el('inbox').replaceChildren();refresh();});
function rows(target,items,render){const nodes=items.map(item=>{const li=document.createElement('li');render(li,item);return li;});target.replaceChildren(...nodes);}
async function refresh(){
  if(polling)return;polling=true;
  try {
    const state=await api('/api/messages/status');
    el('connection').textContent=state.ready?'GATEWAY READY':'GATEWAY NOT READY';
    el('send').disabled=sending||!state.ready;
    el('mode').textContent=state.mode==='HARDWARE'?'ARGON HARDWARE · REAL MESSAGE RELAY':'FULL SOFTWARE SIMULATION · NO HARDWARE ENFORCEMENT';
    if(!state.ready)el('connection').textContent=state.supported?'Waiting for gateway readiness':'Connect and flash message-capable firmware';
    if(location.hostname==='localhost'||location.hostname==='127.0.0.1'){
      const operator=await api('/api/messages/operator');
      el('operator').hidden=false;el('audit-panel').hidden=false;
      if(!addressInitialized){el('lan-address').value=operator.lan_host||'';addressInitialized=true;}
      el('share').textContent=operator.share_url||'Local preview only. Restart with --lan-host to share.';
      // Do not disrupt selection or manual copying during the one-second poll.
      if(el('sender-code').value!==operator.sender_key)el('sender-code').value=operator.sender_key;
      if(el('reader-code').value!==operator.reader_key)el('reader-code').value=operator.reader_key;
      rows(el('audit'),operator.audit,(li,item)=>{
        li.textContent=`${new Date(item.time*1000).toLocaleTimeString()} · slot ${item.slot} · ${item.status} · ${item.reason.replaceAll('_',' ')}`;
      });
    }
    if(readerKey){
      const inbox=await api('/api/messages/inbox',{headers:{Authorization:`Bearer ${readerKey}`}});
      el('inbox-status').textContent=inbox.ready?'Inbox open · most recent 50 approved messages':'Gateway offline · showing previously approved messages';
      rows(el('inbox'),inbox.items,(li,item)=>{const stamp=document.createElement('small');stamp.textContent=`${new Date(item.time*1000).toLocaleTimeString()} · ${item.source==='HARDWARE'?'Argon approved':'Simulator approved'}`;li.append(stamp,document.createTextNode(item.text));});
    }
  } catch(error){el('connection').textContent='OFFLINE / REQUEST FAILED';el('send').disabled=true;el('inbox-status').textContent=error.message;}
  finally{polling=false;}
}
refresh();setInterval(refresh,1000);
