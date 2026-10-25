/** The public showcase never contacts localhost or paid providers. */
export const CLOUD=process.env.NEXT_PUBLIC_CLOUD === 'true';
export const SHOWCASE = process.env.NEXT_PUBLIC_SHOWCASE === 'true';
export const API = process.env.NEXT_PUBLIC_API_BASE || (CLOUD?'/api':'http://127.0.0.1:8000');
const STORAGE='truthhunter-demo-v1';
const samples=[
 ['演示服务是否永久无限免费？','虚构服务条款','本地测试样本：基础功能在试用期内免费，试用结束后需要订阅。此内容为虚构数据。'],
 ['演示：青岚市今晚一定发生七级地震？','虚构地震通报','虚构演示通报：网络图片拍摄于三年前，不能证明青岚市今晚发生地震。青岚市及该消息均为测试设定。'],
 ['演示：星叶饮料零添加就更健康？','虚构营养标签','虚构演示标签：星叶饮料每百毫升含糖十二克。零添加的标签本身不能替代营养成分比较。品牌与数据均为测试设定。'],
 ['演示：火星照片里的形状证明存在建筑？','虚构图像解读','虚构演示材料：照片只呈现一块轮廓规则的岩石，没有附带测量记录或建筑证据。本段不是航天机构发布的结论。'],
];
function demos():any[]{try{const value=JSON.parse(localStorage.getItem(STORAGE)||'[]');return Array.isArray(value)?value.filter(x=>x.data_mode==='fixture'&&x.id?.startsWith('demo-')&&samples.some(s=>s[0]===x.message)):[]}catch{return []}}
async function publicCases(){const response=await fetch('/showcase/index.json');if(!response.ok)throw Error('公开案例暂时无法加载，请刷新后重试。');return response.json()}
export async function request(path:string,options?:RequestInit):Promise<any>{
 if(CLOUD){
  if(path==='/investigations'&&(!options||options.method!=='POST')){const own=await apiRequest(path,options);return [...own,...await publicCases()]}
  const id=path.match(/^\/investigations\/([a-f0-9]{32})$/)?.[1];
  if(id&&PUBLIC_IDS.has(id)){const response=await fetch('/showcase/'+id+'.json');if(!response.ok)throw Error('历史档案加载失败');return response.json()}
  const value=await apiRequest(path,options);
  if(path==='/investigations'&&options?.method==='POST')void runCloudTask(value.id).catch(()=>{});
  return value;
 }
 if(!SHOWCASE){const response=await fetch(API+path,options);if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(typeof data.detail==='string'?data.detail:`请求失败 (${response.status})`)}return response.json()}
 if(path==='/health')return {status:'showcase',configured:{yuanbao:false,llm:false},search_history:{attempts:0,succeeded:0},publication:true};
 if(path==='/investigations'&&options?.method==='POST'){
  const payload=JSON.parse(String(options.body||'{}'));
  if(payload.data_mode!=='fixture')throw Error('线上比赛版不执行真实搜索或模型调用。请体验虚构案例，或查看已验收公开报告。');
  const sample=samples.find(s=>s[0]===payload.message);if(!sample)throw Error('请选择页面中的固定演示案例。');
  const id='demo-'+crypto.randomUUID(),created_at=new Date().toISOString(),claim_id=id+'-claim',source_id=id+'-source',evidence_id=id+'-evidence';
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(sample[2]));
  const sha256=Array.from(new Uint8Array(digest)).map(b=>b.toString(16).padStart(2,'0')).join('');
  const detail={id,message:sample[0],mode:payload.mode||'quick',workflow:'investigation',data_mode:'fixture',status:'COMPLETED',created_at,records:[
   {id:claim_id,kind:'claim',text:sample[0],data_mode:'fixture'},
   {id:id+'-search',kind:'search_run',query:'虚构样本演示',status:'fixture',request_id:null,pages:[],data_mode:'fixture'},
   {id:source_id,kind:'source',title:sample[1],url:'https://fixture.invalid/terms',status:'fixture',data_mode:'fixture'},
   {id:evidence_id,kind:'evidence',claim_id,source_id,url:'https://fixture.invalid/terms',quote:sample[2],stance:'context',locator:{start:0,end:Array.from(sample[2]).length,unit:'unicode_codepoints'},sha256,data_mode:'fixture'},
   {id:id+'-report',kind:'report',revision:1,assessments:[{claim_id,verdict:'INSUFFICIENT',evidence_ids:[evidence_id],rationale:'虚构测试资料不能证明任何现实消息。'}],limitations:['全部为虚构测试资料；未调用元宝或模型，未访问真实网页。','此流程在当前浏览器生成并保存，不产生现实事实核验结论。']}
  ],events:[['PLANNING','演示：拆解虚构消息'],['SEARCHING','演示：读取测试资料，未调用元宝 API'],['BROWSING','演示：没有访问真实网页'],['EXTRACTING','演示：定位样本文本'],['VERIFYING','演示：保留证据不足结论'],['REPORTING','演示：生成测试报告'],['COMPLETED','演示完成；不是真实核验']].map(([status,message],i)=>({id:i+1,status,message,created_at,data_mode:'fixture'}))};
  try{localStorage.setItem(STORAGE,JSON.stringify([detail,...demos()].slice(0,30)))}catch{throw Error('浏览器存储不可用，演示未保存。请允许此网站使用本地存储后重试。')}
  return detail;
 }
 if(path==='/investigations')return [...demos().map(({records,events,...x})=>x),...await publicCases()];
 const match=path.match(/^\/investigations\/([^/]+)$/);
 if(match){const cached=demos().find(x=>x.id===match[1]);if(cached)return cached;const cases=await publicCases();if(!cases.some((x:any)=>x.id===match[1]))throw Error('找不到这项调查。');const r=await fetch('/showcase/'+match[1]+'.json');if(!r.ok)throw Error('案例档案加载失败。');return r.json()}
 throw Error('此功能需要本机调查服务，线上公开版仅提供演示与只读档案。');
}
export function screenshotUrl(id:string,name:string){return (SHOWCASE||(CLOUD&&PUBLIC_IDS.has(id)))?`/showcase/${encodeURIComponent(id)}/${encodeURIComponent(name)}`:`${API}/investigations/${id}/screenshots/${encodeURIComponent(name)}`}
export function reportUrl(id:string){return (SHOWCASE||(CLOUD&&PUBLIC_IDS.has(id)))?`/showcase/${encodeURIComponent(id)}/report.md`:`${API}/investigations/${id}/report.md`}
export async function reportText(detail:any){if(!SHOWCASE||detail.data_mode==='live'){const response=await fetch(reportUrl(detail.id));if(!response.ok)throw Error('报告加载失败');return response.text()}return `# 虚构演示报告\n\n${detail.message}\n\n> 虚构测试资料，未搜索、未访问网页、未进行现实核验。\n\n结论：证据不足\n\n${detail.records.find((r:any)=>r.kind==='evidence')?.quote||''}\n\n本报告只用于展示调查界面，不证明现实消息。\n`}
export async function downloadReport(detail:any){const blob=new Blob([await reportText(detail)],{type:'text/markdown;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`TruthHunter-${detail.id}.md`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}

const PUBLIC_IDS=new Set(['5b2229b18b064be394f630ed6999560a','e70e6f577a974a6082be1ab570e54389','7cf8c1e35d4b43308b57d1dfe79f888c','a58f7022b69a4a909f541f2725003971']);
async function apiRequest(path:string,options?:RequestInit){const response=await fetch(API+path,{...options,cache:'no-store'});const value=await response.json().catch(()=>({}));if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:`服务请求失败 (${response.status})`);return value}
export async function runCloudTask(id:string){const session=await apiRequest('/session');const response=await fetch('/truthhunter/rpc',{method:'POST',headers:{'Content-Type':'application/json','Makers-Conversation-Id':session.id,'X-TH-Token':session.token},body:JSON.stringify({path:'/investigations/'+id+'/run',method:'POST'})});const result=await response.json();if(!response.ok||result.status>=400)throw Error(result.body?.detail||'调查启动失败');return result}
export function subscribeInvestigation(id:string,onUpdate:(detail:any)=>void,onError:()=>void){
 let closed=false,timer:ReturnType<typeof setTimeout>;
 if(CLOUD){const poll=async()=>{if(closed)return;try{const detail=await request('/investigations/'+id);if(closed)return;onUpdate(detail);if(['COMPLETED','PARTIAL','FAILED','CANCELLED'].includes(detail.status)){closed=true;return}}catch{if(!closed)onError()}if(!closed)timer=setTimeout(poll,2200)};timer=setTimeout(poll,900);return {close(){closed=true;clearTimeout(timer)}}}
 const es=new EventSource(`${API}/investigations/${id}/events`);es.addEventListener('investigation',async()=>{try{onUpdate(await request('/investigations/'+id))}catch{onError()}});es.onerror=onError;return {close(){es.close()}};
}
