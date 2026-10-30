#!/usr/bin/env python3
"""Expose the existing training site only on this Mac's authenticated Tailscale IPv4."""
import argparse,ipaddress,json,os,shutil,socket,subprocess,sys,time
from pathlib import Path
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[1]
TAILNET_V4=ipaddress.ip_network('100.64.0.0/10')

def tailscale_ip(status):
 if status.get('BackendState')!='Running':raise ValueError('Tailscale 尚未連線，請先開啟並連線。')
 for value in status.get('TailscaleIPs',[]):
  try:ip=ipaddress.ip_address(value)
  except ValueError:continue
  if ip.version==4 and ip in TAILNET_V4:return str(ip)
 raise ValueError('尚未取得 Tailscale IPv4 位址，請確認連線狀態後重試。')

def detect_ip():
 cli=shutil.which('tailscale')
 if not cli:
  app=Path('/Applications/Tailscale.app/Contents/MacOS/Tailscale')
  if app.is_file():cli=str(app)
 if not cli:raise ValueError('找不到 Tailscale，請先安裝並登入。')
 try:
  result=subprocess.run([cli,'status','--json'],env={**os.environ,'TAILSCALE_BE_CLI':'1'},capture_output=True,text=True,timeout=8,check=True)
  return tailscale_ip(json.loads(result.stdout))
 except (subprocess.SubprocessError,OSError,json.JSONDecodeError):raise ValueError('無法讀取 Tailscale 狀態，請確認應用程式已啟動並連線。')

def available_site(host,port):
 try:
  with urlopen(f'http://{host}:{port}/api/v1/bootstrap',timeout=1) as r:
   return r.status==200 and 'terms_version' in json.load(r).get('data',{})
 except (OSError,ValueError):return False

def main():
 parser=argparse.ArgumentParser(description='Life Reroll 手機 Tailscale 私有入口')
 parser.add_argument('--check',action='store_true');parser.add_argument('--port',type=int,default=5180)
 parser.add_argument('--local-port',type=int,default=5180);parser.add_argument('--api-port',type=int,default=8010)
 args=parser.parse_args()
 try:
  for port in [args.port,args.local_port,args.api_port]:
   if not 1<=port<=65535:raise ValueError('連接埠須介於 1 至 65535。')
  address=detect_ip()
  if args.check:print(address);return 0
  for _ in range(40):
   if available_site('127.0.0.1',args.local_port):break
   time.sleep(.25)
  else:raise ValueError('本機網站尚未就緒，請先執行 start-training-local.command，再重試手機入口。')
  if available_site(address,args.port):
   print(f'手機入口已在執行：http://{address}:{args.port}/training',flush=True);return 0
  with socket.socket() as probe:
   try:probe.bind((address,args.port))
   except OSError:raise ValueError('Tailscale 網址或連接埠無法使用，請確認 VPN 連線與連接埠是否被其他程式占用。')
  print(f'手機開啟 Tailscale，與這台 Mac 加入同一個網路。\n學員：http://{address}:{args.port}/training\n講師：http://{address}:{args.port}/teach\nMac 與本機網站須持續執行；Ctrl-C 停止這個手機入口。',flush=True)
  os.execv(sys.executable,[sys.executable,str(ROOT/'life-reroll-frontend-20261016-212920/serve.py'),'--host',address,'--port',str(args.port),'--api-proxy',f'http://127.0.0.1:{args.api_port}'])
 except ValueError as exc:print(str(exc),file=sys.stderr);return 1

if __name__=='__main__':sys.exit(main())
