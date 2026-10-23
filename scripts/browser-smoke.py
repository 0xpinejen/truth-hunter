"""Real read-only browser smoke check. This is not a fact-checking investigation."""
import asyncio
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/api'))
from truthhunter.browser import BrowserAgent

async def main():
    result=await BrowserAgent(os.getenv('ARTIFACT_DIR','./artifacts')).capture(
        'https://cloud.tencent.com/document/product/1806/130615','browser-smoke')
    output={k:v for k,v in result.items() if k!='text'}
    output['captured_characters']=len(result['text'])
    output['purpose']='Browser smoke check only; not evidence for a factual claim.'
    Path('artifacts/browser-smoke.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(output,ensure_ascii=False,indent=2))

if __name__=='__main__': asyncio.run(main())
