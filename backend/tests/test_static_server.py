import importlib.util
import threading
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def test_prebuilt_server_routes_assets_and_api_boundary():
    root=Path(__file__).resolve().parents[2]
    frontend=root/'frontend'
    if not frontend.is_dir():frontend=root/'life-reroll-frontend-20261016-212920'
    spec=importlib.util.spec_from_file_location('frontend_server',frontend/'serve.py')
    server_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(server_module)
    server=ThreadingHTTPServer(('127.0.0.1',0),server_module.Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        for route in ('/','/full','/demo','/city','/place/work'):
            response=urlopen(base+route);assert response.status==200
            assert b'<html' in response.read().lower()
        response=urlopen(base+'/config.js')
        assert response.read()==(frontend/'public/config.js').read_bytes()
        assert response.headers['Cache-Control']=='no-cache'
        assert urlopen(base+'/event-media.json').status==200
        assert urlopen(base+'/scene-home.png').status==200
        for route,code in (('/missing.js',404),('/../package.json',404),('/api/v1/bootstrap',502)):
            try:urlopen(base+route)
            except HTTPError as e:assert e.code==code
            else:raise AssertionError('unexpected static API or file response')
    finally:
        server.shutdown();server.server_close();worker.join()


def test_same_origin_proxy_preserves_session_mutations_and_pdf():
    frontend=Path(__file__).resolve().parents[2]/'life-reroll-frontend-20261016-212920'
    spec=importlib.util.spec_from_file_location('frontend_proxy_server',frontend/'serve.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    requests=[]
    class Backend(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.command,self.path))
            if self.path.endswith('.pdf'):
                body=b'%PDF-1.4\nproxy-test';self.send_response(200);self.send_header('Content-Type','application/pdf');self.send_header('Content-Disposition','attachment; filename="report.pdf"')
            else:
                body=b'{"data":{"maintenance":false}}';self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('X-Session-Token','test-session');self.send_header('Set-Cookie','life_session=test-session; HttpOnly; Path=/; SameSite=lax')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_POST(self):
            requests.append((self.command,self.path))
            assert self.headers['Authorization']=='Bearer test-session'
            assert self.headers['Cookie']=='life_session=test-session'
            assert self.headers['X-CSRF-Token']=='test-csrf'
            assert self.headers['Idempotency-Key']=='same-request'
            body=self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(409);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_DELETE(self):
            requests.append((self.command,self.path));self.send_response(204);self.end_headers()
    upstream=ThreadingHTTPServer(('127.0.0.1',0),Backend)
    proxy=ThreadingHTTPServer(('127.0.0.1',0),module.Handler)
    proxy.api_proxy=f'http://127.0.0.1:{upstream.server_port}'
    workers=[threading.Thread(target=s.serve_forever,daemon=True) for s in (upstream,proxy)]
    for worker in workers:worker.start()
    base=f'http://127.0.0.1:{proxy.server_port}'
    try:
        response=urlopen(base+'/api/v1/bootstrap?locale=zh-TW')
        assert json.load(response)=={'data':{'maintenance':False}}
        assert response.headers['X-Session-Token']=='test-session'
        assert 'HttpOnly' in response.headers['Set-Cookie']
        assert response.headers['Cache-Control']=='no-store'
        body=b'{"error":{"code":"STALE_VERSION"}}'
        request=Request(base+'/api/v1/mutate',data=body,headers={'Authorization':'Bearer test-session','Cookie':'life_session=test-session','X-CSRF-Token':'test-csrf','Idempotency-Key':'same-request','Content-Type':'application/json'})
        try:urlopen(request)
        except HTTPError as error:
            assert error.code==409;assert error.read()==body
        else:raise AssertionError('backend conflict must remain a conflict')
        response=urlopen(base+'/api/v1/reports/report.pdf')
        assert response.read()==b'%PDF-1.4\nproxy-test'
        assert response.headers['Content-Type']=='application/pdf'
        assert response.headers['Content-Disposition']=='attachment; filename="report.pdf"'
        assert urlopen(Request(base+'/api/v1/session',method='DELETE')).status==204
        assert requests==[('GET','/api/v1/bootstrap?locale=zh-TW'),('POST','/api/v1/mutate'),('GET','/api/v1/reports/report.pdf'),('DELETE','/api/v1/session')]
        upstream.shutdown();upstream.server_close();workers[0].join()
        try:urlopen(base+'/api/v1/bootstrap')
        except HTTPError as error:
            assert error.code==502;assert json.load(error)['error']['code']=='BACKEND_UNAVAILABLE'
        else:raise AssertionError('unavailable backend must not fall back to HTML')
    finally:
        for server in (upstream,proxy):server.shutdown();server.server_close()
        for worker in workers:worker.join()


def test_precompressed_static_etags_head_and_private_boundary():
    import gzip
    frontend=Path(__file__).resolve().parents[2]/'life-reroll-frontend-20261016-212920'
    spec=importlib.util.spec_from_file_location('compressed_server',frontend/'serve.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    server=ThreadingHTTPServer(('127.0.0.1',0),module.Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    base=f'http://127.0.0.1:{server.server_port}'
    asset=next(p for p in (frontend/'dist/assets').glob('index-*.js') if p.stat().st_size>1024)
    route='/assets/'+asset.name
    try:
        raw=urlopen(base+route);payload=raw.read()
        compressed=urlopen(Request(base+route,headers={'Accept-Encoding':'gzip'}))
        assert compressed.headers['Content-Encoding']=='gzip'
        assert gzip.decompress(compressed.read())==payload
        assert compressed.headers['Vary']=='Accept-Encoding'
        assert 'immutable' in compressed.headers['Cache-Control']
        assert compressed.headers['ETag']!=raw.headers['ETag']
        head=urlopen(Request(base+route,method='HEAD',headers={'Accept-Encoding':'gzip'}))
        assert head.read()==b'' and head.headers['Content-Length']==compressed.headers['Content-Length']
        try:urlopen(Request(base+route,headers={'If-None-Match':raw.headers['ETag']}))
        except HTTPError as e:assert e.code==304 and e.read()==b''
        else:raise AssertionError('expected conditional hit')
        for encoding in ('gzip;q=0','gzip;q=0, *;q=1','identity'):
            res=urlopen(Request(base+route,headers={'Accept-Encoding':encoding}))
            assert not res.headers.get('Content-Encoding') and res.read()==payload
        assert urlopen(base+'/scene-home.webp').headers['Content-Type']=='image/webp'
        assert urlopen(base+'/scene-home.png').read()==urlopen(base+'/scene-home.webp').read()
        for path in ('/source-assets/scene-home.png','/../backend/mail-config.json'):
            try:urlopen(base+path)
            except HTTPError as e:assert e.code==404
            else:raise AssertionError('private source must not be served')
        try:urlopen(base+'/assets/missing-12345678.js')
        except HTTPError as e:
            assert e.code==404 and e.headers['Cache-Control']=='no-store'
        else:raise AssertionError('missing build chunk must not be cached')
    finally:server.shutdown();server.server_close();worker.join()
