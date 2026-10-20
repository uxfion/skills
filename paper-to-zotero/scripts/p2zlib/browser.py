"""The user's Chrome through `opencli browser <session>`: open a page, run JavaScript in it, carry bytes out of it.

Pages open in the background (--window foreground for pages the user should see). Bytes leave the page as base64 in
window.__p2z_b64, read in chunks. find() lists what on any page may lead to the paper's PDF, best first:
  1. the PDF the page declares: citation_pdf_url, <link rel=alternate type=application/pdf>
  2. the documents it embeds: iframe, embed and object sources (a pdf.js viewer in any frame is flagged: `viewer`)
  3. links whose text or aria-label says PDF ("PDF", "Download PDF", "View PDF", "Get PDF", "Full text PDF"), or
     whose path ends in .pdf or has a /pdf/ segment; the page's own site first; purchase links left out
Whatever a candidate yields is only the paper once claim has checked it: the finder finds, the check judges.
"""
import base64
import json
import subprocess

from .cli import CANNOT, Stop

OPEN_TIMEOUT, EVAL_TIMEOUT = 60, 120
CHUNK = 1_000_000  # base64 characters per read

VIEWER_FIND = r"""const W=[window];for(const f of document.querySelectorAll('iframe,frame')){try{if(f.contentWindow&&f.contentWindow.document)W.push(f.contentWindow)}catch(e){}}
let A=null;for(const w of W){try{if(w.PDFViewerApplication){A=w.PDFViewerApplication;break}}catch(e){}}"""
FIND_JS = ("/*p2z:find*/(()=>{" + VIEWER_FIND + r"""const out=[],seen=new Set(),here=location.hostname;
const add=(u,why)=>{try{const a=new URL(u,document.baseURI).href;if(!/^https?:/.test(a)||seen.has(a))return;seen.add(a);out.push({url:a,why:why})}catch(e){}};
const m=document.querySelector('meta[name="citation_pdf_url"]');if(m&&m.content)add(m.content,'citation_pdf_url');
for(const l of document.querySelectorAll('link[rel~="alternate"][type^="application/pdf"]'))add(l.href,'alternate');
for(const f of document.querySelectorAll('iframe[src],embed[src],object[data]'))add(f.src||f.data,'frame');
const buy=/\b(buy|purchase|rent|price|cart)\b/i,links=[];
for(const a of document.querySelectorAll('a[href]')){const t=((a.innerText||'')+' '+(a.getAttribute('aria-label')||'')).trim(),p=a.pathname||'';
if(buy.test(t)||buy.test(a.href))continue;if(/\bpdf\b/i.test(t)||/\.pdf$/i.test(p)||/\/pdf\//i.test(p))links.push({h:a.href,same:a.hostname===here})}
links.sort((x,y)=>(y.same?1:0)-(x.same?1:0));for(const l of links)add(l.h,'link');
return {href:location.href,title:document.title||'',mark:window.__p2z_mark||null,viewer:!!(A&&A.pdfDocument),candidates:out}})()""")
MARK_JS = "/*p2z:mark*/(()=>{window.__p2z_mark='__TOKEN__';return location.href})()"
FETCH_JS = r"""/*p2z:fetch*/(async()=>{try{const r=await fetch(__URL__,{credentials:'include'});
const ct=r.headers.get('content-type')||'';const b=new Uint8Array(await r.arrayBuffer());
const h=String.fromCharCode.apply(null,b.subarray(0,1024));const pdf=h.indexOf('%PDF-')>=0;let n=0;
if(pdf){let s='';for(let i=0;i<b.length;i+=32768)s+=String.fromCharCode.apply(null,b.subarray(i,i+32768));
window.__p2z_b64=btoa(s);n=window.__p2z_b64.length}
return {status:r.status,ct:ct,url:r.url,size:b.length,pdf:pdf,b64len:n}}catch(e){return {error:String(e)}}})()"""
HTML_JS = r"""/*p2z:html*/(()=>{const h='<!DOCTYPE html>\n'+document.documentElement.outerHTML;
const b=new TextEncoder().encode(h);let s='';for(let i=0;i<b.length;i+=32768)s+=String.fromCharCode.apply(null,b.subarray(i,i+32768));
window.__p2z_b64=btoa(s);return {size:b.length,b64len:window.__p2z_b64.length,href:location.href}})()"""
VIEWER_DATA_JS = ("/*p2z:viewer-data*/(async()=>{try{" + VIEWER_FIND +
                  r"""if(!A||!A.pdfDocument)return {pdf:false};const d=await A.pdfDocument.getData();
const b=d instanceof Uint8Array?d:new Uint8Array(d);let s='';for(let i=0;i<b.length;i+=32768)s+=String.fromCharCode.apply(null,b.subarray(i,i+32768));
window.__p2z_b64=btoa(s);return {pdf:true,size:b.length,b64len:window.__p2z_b64.length}}catch(e){return {pdf:false,error:String(e)}}})()""")
ANCHORS_JS = r"""/*p2z:anchors*/(()=>({href:location.href,anchors:[...document.querySelectorAll('a[href]')].map(a=>({text:(a.innerText||'').trim().replace(/\s+/g,' '),href:a.href})).filter(a=>a.text)}))()"""
WATCH_JS = r"""/*p2z:watch*/(()=>{const u=__UNTIL__;let found=false;if(u){try{found=!!document.querySelector(u)}catch(e){}
found=found||((document.body&&document.body.innerText)||'').indexOf(u)>=0}
return {href:location.href,title:document.title||'',found:found}})()"""
CHUNK_JS = "/*p2z:chunk*/(()=>{const s=window.__p2z_b64;return typeof s==='string'?s.slice(__A__,__B__):null})()"
CLEAR_JS = "/*p2z:clear*/(()=>{delete window.__p2z_b64;return true})()"


class Browser:
    def __init__(self, session="p2z", window="background"):
        self.session, self.window = session, window

    def run(self, *args, timeout=EVAL_TIMEOUT, window=False):
        """-> (stdout, None) or (None, the error line)."""
        argv = ["opencli", "browser", self.session, *args] + (["--window", self.window] if window else [])
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            raise Stop("no_opencli", exit=CANNOT, hint="opencli is not on PATH: references/install.md.") from None
        except subprocess.TimeoutExpired:
            return None, f"opencli {args[0]} timed out"
        if p.returncode != 0:
            return None, ((p.stderr or p.stdout).strip().splitlines() or [f"exit {p.returncode}"])[-1]
        return p.stdout, None

    def open(self, url):
        """Navigate the session's tab -> None, or the error."""
        return self.run("open", url, timeout=OPEN_TIMEOUT, window=True)[1]

    def eval(self, js, timeout=EVAL_TIMEOUT):
        out, err = self.run("eval", js, timeout=timeout)
        if err is not None:
            return None, err
        try:
            return json.loads(out.strip()), None
        except ValueError:
            return out.strip(), None

    def value(self, js):
        """eval() of a snippet that answers an object -> the object, {} on any failure."""
        got, _ = self.eval(js)
        return got if isinstance(got, dict) else {}

    def carry(self, total):
        """The base64 the last snippet left in the page -> bytes, or None."""
        parts = []
        for start in range(0, total, CHUNK):
            chunk, err = self.run("eval", CHUNK_JS.replace("__A__", str(start)).replace("__B__", str(start + CHUNK)))
            chunk = (chunk or "").strip()
            if err is not None or not chunk or chunk == "null":
                return None
            parts.append(chunk)
        self.run("eval", CLEAR_JS, timeout=30)
        try:
            return base64.b64decode("".join(parts)) if parts else None
        except ValueError:
            return None

    def find(self):
        """The current page: {href, title, mark, viewer, candidates: [{url, why}]}, best first."""
        return self.value(FIND_JS)

    def mark(self, token):
        """Mark the current document: a navigation drops the mark, a download keeps it."""
        self.eval(MARK_JS.replace("__TOKEN__", token))

    def fetch(self, url):
        """Request url inside the page, with its cookies -> (PDF bytes or None, why not)."""
        meta, err = self.eval(FETCH_JS.replace("__URL__", json.dumps(url)))
        if err is None and isinstance(meta, dict) and meta.get("pdf"):
            data = self.carry(int(meta.get("b64len") or 0))
            if data:
                return data, None
        if not isinstance(meta, dict):
            return None, err or "no answer"
        return None, meta.get("error") or f"{meta.get('status')} {meta.get('ct')}".strip()

    def viewer(self):
        """The bytes of a pdf.js viewer's document in the current tab, or None."""
        meta = self.value(VIEWER_DATA_JS)
        return self.carry(int(meta.get("b64len") or 0)) if meta.get("pdf") else None

    def html(self):
        """The current page's HTML -> (bytes, its url), or (None, None)."""
        meta = self.value(HTML_JS)
        data = self.carry(int(meta.get("b64len") or 0)) if meta.get("b64len") else None
        return (data, meta.get("href")) if data else (None, None)

    def anchors(self):
        """The current page's links with their text: {href, anchors: [{text, href}]}."""
        return self.value(ANCHORS_JS)

    def watch(self, until=None):
        """{href, title, found}: whether the page shows `until` (text, or a CSS selector)."""
        return self.value(WATCH_JS.replace("__UNTIL__", json.dumps(until)))
