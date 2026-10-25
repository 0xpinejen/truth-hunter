import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
process.env.NEXT_PUBLIC_SHOWCASE='true';
const storage=new Map();
globalThis.localStorage={getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)};
const fetched=[];
globalThis.fetch=async input=>{const path=String(input);fetched.push(path);assert.match(path,/^\/showcase\/[a-z0-9/.-]+$/);const bytes=await readFile(new URL('../public'+path,import.meta.url));return new Response(bytes)};
const client=await import('../app/data-client.ts');

test('public mode only reads the four selected cases and explicitly disables live capabilities',async()=>{
 const health=await client.request('/health');assert.equal(health.configured.yuanbao,false);assert.equal(health.configured.llm,false);
 const items=await client.request('/investigations');assert.equal(items.length,4);assert.ok(items.every(x=>x.readonly&&x.data_mode==='live'));
 const detail=await client.request('/investigations/'+items[3].id);
 assert.equal(detail.records.find(x=>x.kind==='report').assessments[0].independent_support_groups,2);
 assert.ok(client.screenshotUrl(detail.id,'image.png').startsWith('/showcase/'));
 assert.ok(client.reportUrl(detail.id).startsWith('/showcase/'));
});
test('live tasks, image extraction, review writes, and arbitrary demo messages cannot trigger provider requests',async()=>{
 const initial=fetched.length;
 await assert.rejects(client.request('/investigations',{method:'POST',body:JSON.stringify({message:'任意现实消息',data_mode:'live'})}),/不执行真实搜索/);
 await assert.rejects(client.request('/investigations',{method:'POST',body:JSON.stringify({message:'任意现实消息',data_mode:'fixture'})}),/固定演示/);
 await assert.rejects(client.request('/extract-image',{method:'POST'}));
 await assert.rejects(client.request('/investigations/example/review',{method:'POST'}));
 assert.equal(fetched.length,initial);
});
test('a fixed fixture persists with exact Unicode quote and honest insufficient verdict; export stays marked fictional',async()=>{
 const task=await client.request('/investigations',{method:'POST',body:JSON.stringify({message:'演示：青岚市今晚一定发生七级地震？',data_mode:'fixture'})});
 assert.equal(task.data_mode,'fixture');assert.equal(task.status,'COMPLETED');
 assert.equal(task.records.find(x=>x.kind==='report').assessments[0].verdict,'INSUFFICIENT');
 assert.ok(task.events.every(x=>x.data_mode==='fixture'));
 const restored=await client.request('/investigations/'+task.id);assert.equal(restored.id,task.id);
 const evidence=restored.records.find(x=>x.kind==='evidence');assert.equal(evidence.locator.end,Array.from(evidence.quote).length);
 const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(evidence.quote));assert.equal(evidence.sha256,Buffer.from(hash).toString('hex'));
 assert.match(await client.reportText(task),/虚构测试资料，未搜索/);
 assert.equal((await client.request('/investigations')).filter(x=>x.data_mode==='live').length,4);
});
test('blocked browser storage produces an explicit failure instead of false saved state',async()=>{
 const setter=localStorage.setItem;localStorage.setItem=()=>{throw Error('QuotaExceeded')};
 try{await assert.rejects(client.request('/investigations',{method:'POST',body:JSON.stringify({message:'演示服务是否永久无限免费？',data_mode:'fixture'})}),/演示未保存/)}finally{localStorage.setItem=setter}
});
