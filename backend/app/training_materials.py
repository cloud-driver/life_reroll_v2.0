"""Bounded private document ingestion. No executable office content or live OCR."""
import base64,io,re,zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

MAX_BYTES=8*1024*1024
MAX_TEXT=160000

def decode(name,data):
 if not isinstance(name,str) or not isinstance(data,str):raise ValueError('INVALID_FILE')
 if len(data)>MAX_BYTES*4//3+8:raise ValueError('MATERIAL_TOO_LARGE')
 name=PurePosixPath(name.replace('\\','/')).name[:120]
 if not name or '.' not in name:raise ValueError('FILE_TYPE_NOT_SUPPORTED')
 kind=name.rsplit('.',1)[1].lower()
 if kind not in ('pdf','docx','pptx','txt','md'):raise ValueError('FILE_TYPE_NOT_SUPPORTED')
 try:raw=base64.b64decode(data,validate=True)
 except (ValueError,TypeError):raise ValueError('INVALID_FILE')
 if not raw:raise ValueError('FILE_EMPTY')
 if len(raw)>MAX_BYTES:raise ValueError('MATERIAL_TOO_LARGE')
 return name,kind,raw

def extract(kind,raw):
 sections=[]
 def add(label,text):
  text=text.replace('\x00','').strip()
  if text:
   for n in range(0,len(text),1800):sections.append({'label':label+(f'，片段 {n//1800+1}' if len(text)>1800 else ''),'text':text[n:n+1800]})
 if kind in ('txt','md'):
  try:text=raw.decode('utf-8-sig')
  except UnicodeError:raise ValueError('TEXT_ENCODING_INVALID')
  add('文字資料',text)
 elif kind=='pdf':
  from pypdf import PdfReader
  try:
   r=PdfReader(io.BytesIO(raw))
   if r.is_encrypted:raise ValueError('ENCRYPTED_DOCUMENT')
   if len(r.pages)>100:raise ValueError('TOO_MANY_PAGES')
   for i,p in enumerate(r.pages):
    # Avoid extremely expanded page streams before text extraction.
    contents=p.get_contents()
    if contents and len(contents.get_data())>8*1024*1024:raise ValueError('MATERIAL_EXPANDED_TOO_LARGE')
    add(f'第 {i+1} 頁',p.extract_text() or '')
  except ValueError:raise
  except Exception:raise ValueError('INVALID_FILE')
 else:
  try:
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    if len(z.infolist())>2000 or sum(x.file_size for x in z.infolist())>32*1024*1024:raise ValueError('MATERIAL_EXPANDED_TOO_LARGE')
    names=['word/document.xml'] if kind=='docx' else sorted([n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)],key=lambda n:int(re.search(r'(\d+)\.xml',n)[1]))
    if len(names)>100:raise ValueError('TOO_MANY_PAGES')
    for i,n in enumerate(names):
     data=z.read(n)
     if b'<!DOCTYPE' in data or b'<!ENTITY' in data:raise ValueError('INVALID_FILE')
     tree=ET.fromstring(data)
     if kind=='docx':
      ps=tree.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p')
      for j,p in enumerate(ps):add(f'第 {j+1} 段',''.join(p.itertext()))
     else:add(f'投影片 {i+1}','\n'.join(t.text or '' for t in tree.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}t')))
  except ValueError:raise
  except Exception:raise ValueError('INVALID_FILE')
 if sum(len(s['text']) for s in sections)>MAX_TEXT:raise ValueError('MATERIAL_TEXT_LIMIT')
 if len(sections)>200:raise ValueError('MATERIAL_SECTION_LIMIT')
 return sections
