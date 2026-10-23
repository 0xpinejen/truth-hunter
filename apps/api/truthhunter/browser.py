import asyncio
import hashlib
import ipaddress
import os
import socket
from pathlib import Path
from urllib.parse import urlsplit
from .providers import ProviderError
from .store import now

async def validate_public_url(url, allowed_domains, resolver=None):
    try:
        parts = urlsplit(url)
        host = (parts.hostname or '').lower().rstrip('.')
        if parts.scheme != 'https' or parts.username or parts.password or parts.port not in (None,443):
            raise ValueError()
        if not host or not any(host==x or host.endswith('.'+x) for x in allowed_domains):
            raise ValueError()
        if resolver:
            addresses = await resolver(host)
        else:
            records = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host,443,type=socket.SOCK_STREAM), timeout=5)
            addresses = [x[4][0] for x in records]
        if not addresses or any(not ipaddress.ip_address(x).is_global for x in addresses):
            raise ValueError()
    except (ValueError, OSError, asyncio.TimeoutError):
        raise ProviderError('BROWSER_TARGET_BLOCKED')
    return host

class BrowserAgent:
    def __init__(self, artifact_dir):
        self.artifact_dir = Path(artifact_dir)
        self.allowed = {x.strip().lower() for x in os.getenv('BROWSER_ALLOWED_DOMAINS','').split(',') if x.strip()}

    async def capture(self, url, source_id):
        await validate_public_url(url,self.allowed)
        from playwright.async_api import async_playwright
        self.artifact_dir.mkdir(parents=True,exist_ok=True)
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                context = await browser.new_context(java_script_enabled=False, service_workers='block', accept_downloads=False, viewport={'width':1440,'height':960})
                async def route_request(route):
                    try:
                        if route.request.method != 'GET': raise ProviderError('BROWSER_METHOD_BLOCKED')
                        await validate_public_url(route.request.url,self.allowed)
                        await route.continue_()
                    except Exception: await route.abort()
                await context.route('**/*',route_request)
                page = await context.new_page()
                response = await page.goto(url,wait_until='domcontentloaded',timeout=20000)
                if not response or response.status >= 400: raise ProviderError('BROWSER_HTTP_ERROR')
                await validate_public_url(page.url,self.allowed)
                body = await page.locator('body').inner_text(timeout=5000)
                if len(body.strip()) < 40: raise ProviderError('BROWSER_EMPTY_PAGE')
                text = body[:80000]
                shot = f'{source_id}.png'
                await page.screenshot(path=str(self.artifact_dir/shot),full_page=False,timeout=5000)
                (self.artifact_dir/f'{source_id}.txt').write_text(text,encoding='utf-8')
                return {'final_url':page.url,'title':await page.title(),'text':text,'captured_at':now(),'sha256':hashlib.sha256(text.encode()).hexdigest(),'screenshot':shot,'truncated':len(body)>80000}
            finally: await browser.close()
