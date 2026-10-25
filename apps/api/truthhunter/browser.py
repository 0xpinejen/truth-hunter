import asyncio
import hashlib
import ipaddress
import os
import socket
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, urljoin
import httpx
from .providers import ProviderError
from .store import now

async def public_addresses(host):
    """Resolve only public addresses; optional fixed HTTPS DNS avoids local fake-IP DNS."""
    try:
        if os.getenv('BROWSER_DNS_MODE','system') == 'doh':
            async with httpx.AsyncClient(timeout=8,trust_env=False,follow_redirects=False) as client:
                response=await client.get('https://cloudflare-dns.com/dns-query',params={'name':host,'type':'A'},headers={'Accept':'application/dns-json'})
                response.raise_for_status()
                data=response.json()
                if data.get('Status')!=0: raise ValueError()
                addresses=[a['data'] for a in data.get('Answer',[]) if a.get('type') in (1,28)]
        else:
            records=await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host,443,type=socket.SOCK_STREAM),timeout=5)
            addresses=list(dict.fromkeys(x[4][0] for x in records))
        if not addresses or any(not ipaddress.ip_address(x).is_global for x in addresses):raise ValueError()
        return addresses
    except (ValueError,OSError,TimeoutError,httpx.HTTPError,KeyError,TypeError):
        raise ProviderError('BROWSER_DNS_BLOCKED') from None

async def validate_public_url(url, allowed_domains, resolver=None):
    try:
        parts=urlsplit(url)
        host=(parts.hostname or '').lower().rstrip('.')
        if parts.scheme!='https' or parts.username or parts.password or parts.port not in (None,443):raise ValueError()
        if not host or not ('*' in allowed_domains or any(host==x or host.endswith('.'+x) for x in allowed_domains)):raise ValueError()
        addresses=await (resolver or public_addresses)(host)
        if not addresses or any(not ipaddress.ip_address(x).is_global for x in addresses):raise ValueError()
    except (ValueError,OSError,TimeoutError,ProviderError):
        raise ProviderError('BROWSER_TARGET_BLOCKED') from None
    return host

async def fetch_pinned(client,url,host,address,accept='*/*'):
    parts=urlsplit(url)
    if (parts.hostname or '').lower().rstrip('.')!=host or not ipaddress.ip_address(address).is_global:
        raise ProviderError('BROWSER_TARGET_BLOCKED')
    authority=f'[{address}]' if ':' in address else address
    pinned=urlunsplit(('https',authority,parts.path or '/',parts.query,''))
    async with client.stream('GET',pinned,headers={'Host':host,'User-Agent':'TruthHunter/0.2 (read-only evidence capture)','Accept':accept},extensions={'sni_hostname':host}) as response:
        chunks=[];size=0
        async for chunk in response.aiter_bytes():
            size+=len(chunk)
            if size>4*1024*1024:raise ProviderError('BROWSER_RESPONSE_TOO_LARGE')
            chunks.append(chunk)
        headers={k:v for k,v in response.headers.items() if k.lower() not in {'content-encoding','content-length','transfer-encoding','set-cookie','connection'}}
        return response.status_code,headers,b''.join(chunks)

async def fetch_guarded(client,target,allowed_domains,resolver,network,accept='*/*'):
    for hop in range(6):
        host=await validate_public_url(target,allowed_domains,resolver)
        address=(await resolver(host))[0]
        status,headers,body=await fetch_pinned(client,target,host,address,accept)
        network.append({'url':target,'public_ip':address,'status':status,'bytes':len(body),'tls_hostname':host,'redirect_to':headers.get('location') if 300<=status<400 else None})
        if status in {301,302,303,307,308}:
            if not headers.get('location'):raise ProviderError('BROWSER_INVALID_REDIRECT')
            target=urljoin(target,headers['location'])
            continue
        return target,status,headers,body
    raise ProviderError('BROWSER_TOO_MANY_REDIRECTS')

class ResourceParser(HTMLParser):
    def __init__(self):super().__init__();self.urls=[];self.in_style=False
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='link' and 'stylesheet' in attrs.get('rel','') and attrs.get('href'):self.urls.append(attrs['href'])
        if tag=='img' and attrs.get('src'):self.urls.append(attrs['src'])
        if tag=='style':self.in_style=True
    def handle_endtag(self,tag):
        if tag=='style':self.in_style=False
    def handle_data(self,data):
        if self.in_style:self.urls.extend(css_resources(data))

def css_resources(text):
    return re.findall(r'url\(\s*[\'"]?([^\)\'"\s]+)',text)+re.findall(r'@import\s+[\'"]([^\'"]+)',text)

class BrowserAgent:
    def __init__(self,artifact_dir,browser_connector=None):
        self.artifact_dir=Path(artifact_dir)
        self.browser_connector=browser_connector
        self.allowed={x.strip().lower() for x in os.getenv('BROWSER_ALLOWED_DOMAINS','').split(',') if x.strip()}
        if os.getenv('BROWSER_ALLOW_PUBLIC_WEB')=='true':self.allowed.add('*')

    async def capture(self,url,source_id):
        cache={};network=[];resources={};visited=set();asset_bytes=0
        async def resolve(host):
            if host not in cache:cache[host]=await public_addresses(host)
            return cache[host]
        await validate_public_url(url,self.allowed,resolve)
        from playwright.async_api import async_playwright
        self.artifact_dir.mkdir(parents=True,exist_ok=True)
        async with httpx.AsyncClient(timeout=12,trust_env=False,follow_redirects=False) as client:
            async with asyncio.timeout(25):
                final_url,status,headers,document=await fetch_guarded(client,url,self.allowed,resolve,network,'text/html,application/xhtml+xml')
            if status!=200:raise ProviderError('BROWSER_HTTP_ERROR')
            final_url=str(httpx.URL(final_url))
            resources[final_url]=(status,headers,document)
            parser=ResourceParser();parser.feed(document.decode('utf-8',errors='replace'))
            queue=[urljoin(final_url,u) for u in parser.urls]
            semaphore=asyncio.Semaphore(4)
            async def asset(target):
                nonlocal asset_bytes
                try:
                    async with semaphore,asyncio.timeout(6):
                        actual,status,h,body=await fetch_guarded(client,target,self.allowed,resolve,network)
                    if status!=200 or asset_bytes+len(body)>12*1024*1024:return []
                    asset_bytes+=len(body)
                    resources[str(httpx.URL(target))]=(status,h,body)
                    resources[str(httpx.URL(actual))]=(status,h,body)
                    return [urljoin(actual,u) for u in css_resources(body.decode('utf-8',errors='replace'))] if 'text/css' in h.get('content-type','') else []
                except Exception as error:
                    network.append({'url':target,'error':error.code if isinstance(error,ProviderError) else 'BROWSER_ASSET_UNAVAILABLE'})
                    return []
            # Fetch a bounded static resource bundle before rendering. The browser
            # receives cached bytes only; no async external request runs inside a route.
            bundle_limited=False
            try:
                async with asyncio.timeout(12):
                    for depth in range(3):
                        batch=[]
                        for target in queue:
                            if target not in visited and target.startswith('https://') and len(visited)<40:
                                visited.add(target);batch.append(target)
                        if not batch:break
                        queue=[u for result in await asyncio.gather(*(asset(u) for u in batch)) for u in result]
            except TimeoutError:
                bundle_limited=True
        async with async_playwright() as p:
            browser=await self.browser_connector(p) if self.browser_connector else await p.chromium.launch();context=None
            try:
                context=await browser.new_context(offline=True,java_script_enabled=False,service_workers='block',accept_downloads=False,viewport={'width':1440,'height':960})
                async def route_request(route):
                    try:
                        request=route.request
                        item=resources.get(str(httpx.URL(request.url)))
                        if request.method!='GET' or request.resource_type in {'script','media','websocket'} or item is None:
                            await route.abort();return
                        if request.is_navigation_request() and request.url!=final_url:
                            await route.abort();return
                        code,h,body=item
                        await route.fulfill(status=code,headers=h,body=body)
                    except Exception:pass  # Context shutdown may race a final cached resource.
                await context.route('**/*',route_request)
                page=await context.new_page()
                try:response=await page.goto(final_url,wait_until='load',timeout=15000)
                except Exception:raise ProviderError('BROWSER_NAVIGATION_FAILED') from None
                if not response or response.status!=200 or page.url!=final_url:raise ProviderError('BROWSER_HTTP_ERROR')
                body=await page.locator('body').inner_text(timeout=5000)
                if len(body.strip())<40:raise ProviderError('BROWSER_EMPTY_PAGE')
                text=body[:80000]
                links=await page.locator('a[href]').evaluate_all('(nodes)=>nodes.slice(0,300).map(a=>({url:a.href,text:(a.innerText||a.textContent||"").trim().slice(0,300)}))')
                shot=f'{source_id}.png'
                await page.screenshot(path=str(self.artifact_dir/shot),full_page=False,timeout=5000)
                (self.artifact_dir/f'{source_id}.txt').write_text(text,encoding='utf-8')
                return {'final_url':final_url,'title':await page.title(),'text':text,'captured_at':now(),'sha256':hashlib.sha256(text.encode()).hexdigest(),'screenshot':shot,'truncated':len(body)>80000,'links':links,'network':network,'transport':'public_ip_pinned_tls_v2','browser_offline':True,'resource_bundle_limited':bundle_limited,'cached_resources':len(resources),'dns_mode':os.getenv('BROWSER_DNS_MODE','system')}
            finally:
                if context is not None:await context.unroute_all(behavior='ignoreErrors')
                await browser.close()
