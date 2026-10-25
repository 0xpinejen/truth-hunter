"""Package only built public files and explicit server modules. Never copy the checkout or .env."""
import json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/edgeone-release'
OUT.mkdir(parents=True,exist_ok=True)
# Remove only this generated directory's old contents to avoid publishing obsolete assets.
for p in OUT.iterdir():
    if p.is_dir():shutil.rmtree(p)
    else:p.unlink()
shutil.copytree(ROOT/'apps/web/out',OUT,dirs_exist_ok=True)
shutil.copytree(ROOT/'agents',OUT/'agents',dirs_exist_ok=True,ignore=shutil.ignore_patterns('_truthhunter','_browser_source.txt','__pycache__','*.pyc'))
shutil.copytree(ROOT/'cloud-functions',OUT/'cloud-functions',dirs_exist_ok=True)
shutil.copytree(ROOT/'apps/api/truthhunter',OUT/'agents/_truthhunter',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
# Keep the heavy Playwright driver inside the platform sandbox, not the 128 MB Agent bundle.
browser=(ROOT/'apps/api/truthhunter/browser.py').read_text()
helper=browser.replace('from .providers import ProviderError',"class ProviderError(Exception):\n    def __init__(self,code):self.code=code;super().__init__(code)").replace('from .store import now',"from datetime import datetime,timezone\ndef now():return datetime.now(timezone.utc).isoformat()")
helper+="""
import base64,json
from urllib.parse import urlsplit,parse_qs,urlencode
async def capture_main():
    agent=BrowserAgent('/tmp/truthhunter-capture')
    async def connect(p):
        token=parse_qs(urlsplit(os.environ['TH_CDP']).query)['access_token'][0]
        # The same authenticated local CDP endpoint used by the platform SDK.
        return await p.chromium.connect_over_cdp('http://127.0.0.1:9000/cdp?'+urlencode({'access_token':token}),headers={'X-Access-Token':token},timeout=20000)
    agent.browser_connector=connect
    try:
        result=await agent.capture(os.environ['TH_CAPTURE_URL'],os.environ['TH_SOURCE_ID'])
        result['_image']=base64.b64encode((agent.artifact_dir/result['screenshot']).read_bytes()).decode()
        print(json.dumps(result,ensure_ascii=False))
    except Exception as error:
        message=str(error)
        token=parse_qs(urlsplit(os.environ.get('TH_CDP','')).query).get('access_token',[''])[0]
        if token:message=message.replace(token,'[redacted]')
        print(json.dumps({'error':error.code if isinstance(error,ProviderError) else 'CLOUD_CAPTURE_'+type(error).__name__.upper(),'diagnostic':message[:800]}))
asyncio.run(capture_main())
"""
(OUT/'agents/_browser_source.txt').write_text(helper)
start=browser.index('    async def capture(self,url,source_id):')
(OUT/'agents/_truthhunter/browser.py').write_text(browser[:start]+'    async def capture(self,url,source_id):\n        raise ProviderError("CLOUD_BROWSER_NOT_INITIALIZED")\n')
# Also prepare conventional root sources for EdgeOne Git builds.
shutil.copytree(OUT/'agents/_truthhunter',ROOT/'agents/_truthhunter',dirs_exist_ok=True)
shutil.copy2(OUT/'agents/_browser_source.txt',ROOT/'agents/_browser_source.txt')
config={'agents':{'framework':'openai-agents-sdk','dir':'agents','timeout':300,'sandbox':{'timeout':600}},'cloudFunctions':{'nodejs':{'maxDuration':120}}}
(OUT/'edgeone.json').write_text(json.dumps(config,indent=2)+'\n')
(OUT/'package.json').write_text(json.dumps({'name':'truthhunter-cloud','version':'0.3.0','private':True,'type':'module'})+'\n')
print('Prepared explicit cloud package:',OUT)
