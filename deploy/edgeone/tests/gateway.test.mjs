import {test} from 'node:test';
import assert from 'node:assert/strict';
import {onRequest} from '../../../cloud-functions/api/[[default]].js';
const env={TH_SESSION_SECRET:'only-a-unit-test-key'};
const context=(path,init={})=>({env,request:new Request('https://truthhunter.test/api'+path,init)});
test('opaque signed browser session, HttpOnly cookie, and no provider credentials in bootstrap',async()=>{
 const response=await onRequest(context('/session'));const value=await response.json();
 assert.match(value.id,/^[a-f0-9]{32}$/);assert.match(value.token,/^[0-9]+\.[a-f0-9]{64}$/);
 assert.match(response.headers.get('set-cookie'),/HttpOnly; Secure; SameSite=Lax/);
 assert.equal(Object.keys(value).sort().join(','),'expires,id,token');
 const cookie=response.headers.get('set-cookie').split(';')[0];
 const continued=await (await onRequest(context('/session',{headers:{cookie}}))).json();assert.equal(continued.id,value.id);
 const forged=await (await onRequest(context('/session',{headers:{cookie:'th_session='+value.id+'.forged'}}))).json();assert.notEqual(forged.id,value.id);
});
test('gateway refuses cross-site writes and unknown endpoints before any provider call',async()=>{
 assert.equal((await onRequest(context('/investigations',{method:'POST',headers:{origin:'https://evil.test','content-type':'application/json'},body:'{}'}))).status,403);
 assert.equal((await onRequest(context('/other'))).status,404);
});
test('gateway injects its signed identity and forwards only the requested API path',async()=>{
 let call;
 globalThis.fetch=async(url,init)=>{call={url,init};return Response.json({status:200,body:{configured:{yuanbao:true,llm:true}}})};
 const response=await onRequest(context('/health'));assert.equal(response.status,200);
 assert.equal(call.url,'https://truthhunter.test/truthhunter/rpc');assert.match(call.init.headers['Makers-Conversation-Id'],/^[a-f0-9]{32}$/);
 assert.equal(JSON.parse(call.init.body).path,'/health');assert.ok(call.init.headers['X-TH-Token']);
});
