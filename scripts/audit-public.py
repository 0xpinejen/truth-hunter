"""Compare every deployed static asset against the approved local build."""
import argparse, concurrent.futures, hashlib, json, urllib.request
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('url');args=parser.parse_args()
assert args.url.startswith('https://')
root=Path(__file__).resolve().parents[1]/'apps/web/out'
files=[p for p in root.rglob('*') if p.is_file()]
def verify(path):
 relative=path.relative_to(root).as_posix()
 url=args.url.rstrip('/')+'/'+relative
 with urllib.request.urlopen(url,timeout=25) as response:
  assert response.status==200,url
  body=response.read()
 assert hashlib.sha256(body).digest()==hashlib.sha256(path.read_bytes()).digest(),relative
 return relative
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
 verified=list(pool.map(verify,files))
print(json.dumps({'url':args.url,'verified_files':len(verified),'status':'all_bytes_match'},ensure_ascii=False))
