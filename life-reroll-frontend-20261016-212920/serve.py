"""Serve prebuilt UI + shared public assets. Python 3.11+; no Node required."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from http.client import HTTPConnection, HTTPSConnection, HTTPException
from pathlib import Path
from urllib.parse import unquote, urlsplit
import argparse
import json
import os
import re

ROOT=Path(__file__).resolve().parent

class Handler(SimpleHTTPRequestHandler):
    def send_response(self,code,message=None):
        self._response_code=code
        super().send_response(code,message)
    def send_head(self):
        self._static_compressed=False
        path=Path(self.translate_path(self.path))
        if not path.is_file():return super().send_head()
        original=path;encoded=False
        # Compression happens once at build time, never on a request thread.
        accepts={}
        for entry in self.headers.get('Accept-Encoding','').split(','):
            name,*options=entry.strip().split(';');quality=1.0
            for option in options:
                if option.strip().startswith('q='):
                    try:quality=float(option.strip()[2:])
                    except ValueError:quality=0
            accepts[name.lower()]=quality
        compressed=Path(str(path)+'.gz')
        if accepts.get('gzip',accepts.get('*',0))>0 and compressed.is_file() and compressed.stat().st_mtime_ns>=path.stat().st_mtime_ns:
            path=compressed;encoded=True
        try:
            stream=path.open('rb');stat=os.fstat(stream.fileno())
        except OSError:self.send_error(404);return None
        tag=f'"{stat.st_mtime_ns:x}-{stat.st_size:x}-{int(encoded)}"'
        self._static_compressed=encoded
        if tag in [v.strip().removeprefix('W/') for v in self.headers.get('If-None-Match','').split(',')] or self.headers.get('If-None-Match')=='*':
            self.send_response(304);self.send_header('ETag',tag);self.end_headers();stream.close();return None
        self.send_response(200)
        self.send_header('Content-Type',self.guess_type(str(original)))
        self.send_header('Content-Length',str(stat.st_size))
        self.send_header('Last-Modified',self.date_time_string(original.stat().st_mtime))
        self.send_header('ETag',tag);self.end_headers();return stream

    def proxy_api(self):
        upstream=getattr(self.server,'api_proxy','')
        if not upstream:
            self.api_error('API_NOT_CONFIGURED','網站尚未連接後端服務，請聯絡服務管理者。');return
        target=urlsplit(upstream)
        connection=(HTTPSConnection if target.scheme=='https' else HTTPConnection)(target.hostname,target.port,timeout=25)
        hop={'connection','keep-alive','proxy-authenticate','proxy-authorization','te','trailer','transfer-encoding','upgrade'}
        hop.update(x.strip().lower() for x in self.headers.get('Connection','').split(','))
        headers={k:v for k,v in self.headers.items() if k.lower() not in hop|{'host','content-length'}}
        length=int(self.headers.get('Content-Length','0'))
        body=self.rfile.read(length) if length else None
        try:
            connection.request(self.command,self.path,body=body,headers=headers)
            response=connection.getresponse();data=response.read()
            self.send_response(response.status)
            for key,value in response.getheaders():
                if key.lower() not in hop|{'content-length','server','date','cache-control','x-content-type-options'}:self.send_header(key,value)
            self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers()
            if self.command!='HEAD':self.wfile.write(data)
        except (OSError,HTTPException):
            self.api_error('BACKEND_UNAVAILABLE','無法連線至網站後端，請稍後重試；若持續發生，請聯絡服務管理者。')
        finally:connection.close()
    def api_error(self,code,message):
        body=json.dumps({'error':{'code':code,'message':message}},ensure_ascii=False).encode()
        self.send_response(502);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if urlsplit(self.path).path.startswith('/api/'):
            self.proxy_api();return
        super().do_GET()
    def do_HEAD(self):
        if urlsplit(self.path).path.startswith('/api/'):self.proxy_api()
        else:super().do_HEAD()
    def do_POST(self):
        if urlsplit(self.path).path.startswith('/api/'):self.proxy_api()
        else:self.send_error(405)
    do_PUT=do_POST
    do_PATCH=do_POST
    do_DELETE=do_POST
    do_OPTIONS=do_POST
    def translate_path(self, path):
        relative=unquote(urlsplit(path).path).lstrip('/')
        if any(part in ('.','..') for part in Path(relative).parts):return str(ROOT/'dist'/'__missing__')
        for folder in ('public','dist'):
            base=ROOT/folder;candidate=(base/relative).resolve()
            if candidate.is_relative_to(base) and candidate.is_file():return str(candidate)
        # Old open tabs may still reference pre-optimization image URLs.
        if Path(relative).suffix in ('.png','.jpg','.jpeg'):
            for folder in ('public','dist'):
                base=ROOT/folder;candidate=(base/relative).with_suffix('.webp').resolve()
                if candidate.is_relative_to(base) and candidate.is_file():return str(candidate)
        if not relative or relative in ('training','training/','teach','teach/','full','full/','demo','demo/','city','city/','terms','terms/','privacy','privacy/') or relative.startswith('place/'):
            return str(ROOT/'dist/index.html')
        return str(ROOT/'dist/__missing__')
    def end_headers(self):
        path=urlsplit(self.path).path
        if not path.startswith('/api/'):
            hashed=bool(re.fullmatch(r'/assets/[^/]+-[A-Za-z0-9_-]{8,}\.(js|css)',path))
            self.send_header('Cache-Control','no-store' if getattr(self,'_response_code',200)>=400 else 'public, max-age=31536000, immutable' if hashed else 'no-cache' if path.endswith(('.html','.js','.json')) or not Path(path).suffix else 'public, max-age=3600')
            self.send_header('Vary','Accept-Encoding')
            if getattr(self,'_static_compressed',False):self.send_header('Content-Encoding','gzip')
        self.send_header('X-Content-Type-Options','nosniff')
        super().end_headers()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Life Reroll 前端測試伺服器')
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=5173)
    parser.add_argument('--api-proxy',default=os.environ.get('LIFE_API_PROXY','http://127.0.0.1:8000'),help='同來源 /api 的後端網址')
    args=parser.parse_args()
    target=urlsplit(args.api_proxy)
    if args.api_proxy and (target.scheme not in ('http','https') or not target.hostname or target.username or target.password or target.query or target.fragment or target.path not in ('','/')):parser.error('--api-proxy 須為後端 http(s) 根網址')
    if not (ROOT/'dist/index.html').is_file():parser.error('缺少 dist/index.html，請先執行 npm ci 與 npm run build。')
    print(f'遊戲前端：http://{args.host}:{args.port}/full',flush=True)
    with ThreadingHTTPServer((args.host,args.port),Handler) as server:
        server.api_proxy=args.api_proxy
        try:server.serve_forever()
        except KeyboardInterrupt:pass
