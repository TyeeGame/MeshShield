// Optional Node check: a stalled backend must not freeze healthy badges forever.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('dashboard/app.js', 'utf8');
const elements = Object.fromEntries(['gateway','notice','train','auto','sim-mode'].map(k=>[k,{}]));
const badges = [{textContent:'HEALTHY',dataset:{state:'HEALTHY'}}];
let stall=true, renders=0;
const context = vm.createContext({
  AbortController,
  $: id=>elements[id],
  document:{querySelectorAll:selector=>selector==='.status'?badges:[]},
  setTimeout:fn=>{queueMicrotask(fn);return 1;}, clearTimeout:()=>{},
  render:()=>{renders++;},
  fetch:(_,options)=>stall ? new Promise((resolve,reject)=>{
    options.signal.addEventListener('abort',()=>reject(Object.assign(new Error('timeout'),{name:'AbortError'})));
  }) : Promise.resolve({ok:true,json:async()=>({})})
});
vm.runInContext(source.slice(source.indexOf('let fetching=false;'),source.indexOf("$('train').onclick")),context);
(async()=>{
  await context.refresh();
  assert.equal(badges[0].textContent,'OFFLINE');
  assert.equal(elements.train.disabled,true);
  stall=false;
  await context.refresh();
  assert.equal(renders,1,'a timeout must release the polling lock');
  console.log('Dashboard stalled-request and retry checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
