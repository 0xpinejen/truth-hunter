import {createHmac,randomUUID,timingSafeEqual} from 'node:crypto';
const sign=(value,key)=>createHmac('sha256',key).update(value).digest('hex');
function equal(a,b){const x=Buffer.from(a),y=Buffer.from(b);return x.length===y.length&&timingSafeEqual(x,y)}
export async function onRequest(context){
 const request=context.request,env=context.env||process.env,key=env.TH_SESSION_SECRET;
 if(!key)return Response.json({detail:'云端会话尚未配置'},{status:503});
 const url=new URL(request.url),publicOrigin=env.TH_PUBLIC_ORIGIN||url.origin,path=url.pathname.slice(4)+url.search;
 const cookie=(request.headers.get('cookie')||'').split(';').map(x=>x.trim()).find(x=>x.startsWith('th_session='))?.slice(11)||'';
 let [id,signature]=cookie.split('.');
 if(!/^[a-f0-9]{32}$/.test(id||'')||!equal(signature||'',sign(id,key)))id=randomUUID().replaceAll('-','');
 const expires=Math.floor(Date.now()/1000)+3600,token=expires+'.'+sign(id+'.'+expires,key);
 const headers={'Cache-Control':'no-store','Set-Cookie':`th_session=${id}.${sign(id,key)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000`};
 if(path==='/session')return Response.json({id,token,expires},{headers});
 if(!/^\/(health|extract-image|investigations)(\/|$|\?)/.test(path))return Response.json({detail:'接口不存在'},{status:404,headers});
 if(request.method==='POST'&&request.headers.get('origin')&&request.headers.get('origin')!==publicOrigin)return Response.json({detail:'请求来源不匹配'},{status:403,headers});
 let body;try{if(request.method!=='GET')body=await request.json()}catch{return Response.json({detail:'请求格式不正确'},{status:422,headers})}
 try{
  const response=await fetch(publicOrigin+'/truthhunter/rpc',{method:'POST',headers:{'Content-Type':'application/json','Makers-Conversation-Id':id,'X-TH-Token':token},body:JSON.stringify({path,method:request.method,body})});
  const result=await response.json();
  if(!response.ok)return Response.json({detail:result.code||`云端接口暂不可用 (${response.status})`},{status:response.status,headers});
  if(result.binary)return new Response(Buffer.from(result.binary,'base64'),{status:result.status||200,headers:{...headers,'Content-Type':result.content_type||'application/octet-stream'}});
  return Response.json(result.body??result,{status:result.status||200,headers});
 }catch{return Response.json({detail:'云端连接失败，请稍后重试'},{status:502,headers})}
}
