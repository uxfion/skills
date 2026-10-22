"""The user's Chrome through `opencli browser <command> --session <session>` (OpenCLI 2.x): its own commands for
the page (open, get url/title/html, extract, find, wait text), and JavaScript for what it has none for: the paper's
PDF candidates (its `find` reports a few attributes, no meta content or frame src), a request inside the page with
its cookies, a pdf.js viewer's document.

Pages open in the background (--window foreground for pages the user should see). Bytes leave the page as base64 in
window.__p2z_b64, read in chunks. find() lists what on any page may lead to the paper's PDF, best first:
  1. the PDF the page declares: citation_pdf_url, <link rel=alternate type=application/pdf>
  2. the PDFs it embeds: iframe, embed and object sources that name a PDF (an ad, consent or CAPTCHA frame does not);
     a pdf.js viewer in any frame is flagged: `viewer`
  3. links whose text or aria-label says PDF ("PDF", "Download PDF", "View PDF", "Get PDF", "Full text PDF"), or
     whose path ends in .pdf or has a /pdf/ segment; the page's own site first; purchase links left out
Whatever a candidate yields is only the paper once claim has checked it: the finder finds, the check judges. Each
candidate carries what the page said of it, for the file's label (never read here): a link its text and the text
around it (`near`: its enclosing block's, as "View Open Manuscript" or "Early Access" sit beside a PDF button);
find() also gives the page's own description of the paper (`meta`: META_NAMES, the first value of each).
"""
import base64
import json
import subprocess
from urllib.parse import urljoin

from .cli import CANNOT, Stop

OPEN_TIMEOUT, EVAL_TIMEOUT = 60, 120
CHUNK = 1_000_000  # base64 characters per read

VIEWER_FIND = r"""const W=[window];for(const f of document.querySelectorAll('iframe,frame')){try{if(f.contentWindow&&f.contentWindow.document)W.push(f.contentWindow)}catch(e){}}
let A=null;for(const w of W){try{if(w.PDFViewerApplication){A=w.PDFViewerApplication;break}}catch(e){}}"""
# The meta tags whose content find() reports: what the page says the paper is (title, venue, dates, volume, type).
META_NAMES = r"^(citation_(title|publisher|journal_title|conference_title|date|publication_date|online_date|cover_date|volume|issue|firstpage|doi|article_type)|dc\.(type|publisher|date)|prism\.(publicationdate|volume|number)|og:site_name)$"
FIND_JS = ("/*p2z:find*/(()=>{" + VIEWER_FIND + r"""const out=[],seen=new Set(),here=location.hostname,meta={};
const sq=s=>(s||'').replace(/\s+/g,' ').trim();
for(const m of document.querySelectorAll('meta[name],meta[property]')){const n=(m.getAttribute('name')||m.getAttribute('property')||'').toLowerCase();if(new RegExp(__META__).test(n)&&m.content&&!(n in meta))meta[n]=sq(m.content).slice(0,200)}
const add=(u,why,text,near)=>{try{const a=new URL(u,document.baseURI).href;if(!/^https?:/.test(a)||seen.has(a))return;seen.add(a);out.push(Object.assign({url:a,why:why},text?{text:text}:{},near?{near:near}:{}))}catch(e){}};
const m=document.querySelector('meta[name="citation_pdf_url"]');if(m&&m.content)add(m.content,'citation_pdf_url');
for(const l of document.querySelectorAll('link[rel~="alternate"][type^="application/pdf"]'))add(l.href,'alternate');
for(const f of document.querySelectorAll('iframe[src],embed[src],object[data]')){const u=f.src||f.data||'';if(/pdf/i.test(u)||/pdf/i.test(f.type||''))add(u,'frame')}
const buy=/\b(buy|purchase|rent|price|cart)\b/i,links=[];
for(const a of document.querySelectorAll('a[href]')){const t=((a.innerText||'')+' '+(a.getAttribute('aria-label')||'')).trim(),p=a.pathname||'';
if(buy.test(t)||buy.test(a.href))continue;if(/\bpdf\b/i.test(t)||/\.pdf$/i.test(p)||/\/pdf\//i.test(p)){const b=a.parentElement&&a.parentElement.closest('li,p,div,section,td,dd,header,nav')||a.parentElement;
links.push({h:a.href,same:a.hostname===here,t:sq(t).slice(0,80),n:sq(b&&b.innerText).slice(0,160)})}}
links.sort((x,y)=>(y.same?1:0)-(x.same?1:0));for(const l of links)add(l.h,'link',l.t,l.n);
return {href:location.href,title:document.title||'',doc:performance.timeOrigin,viewer:!!(A&&A.pdfDocument),meta:meta,candidates:out}})()""").replace("__META__", json.dumps(META_NAMES))
FETCH_JS = r"""/*p2z:fetch*/(async()=>{try{const r=await fetch(__URL__,{credentials:'include'});
const ct=r.headers.get('content-type')||'';const b=new Uint8Array(await r.arrayBuffer());
const h=String.fromCharCode.apply(null,b.subarray(0,1024));const pdf=h.indexOf('%PDF-')>=0;let n=0;
if(pdf){let s='';for(let i=0;i<b.length;i+=32768)s+=String.fromCharCode.apply(null,b.subarray(i,i+32768));
window.__p2z_b64=btoa(s);n=window.__p2z_b64.length}
return {status:r.status,ct:ct,url:r.url,size:b.length,pdf:pdf,b64len:n}}catch(e){return {error:String(e)}}})()"""
VIEWER_DATA_JS = ("/*p2z:viewer-data*/(async()=>{try{" + VIEWER_FIND +
                  r"""if(!A||!A.pdfDocument)return {pdf:false};const d=await A.pdfDocument.getData();
const b=d instanceof Uint8Array?d:new Uint8Array(d);let s='';for(let i=0;i<b.length;i+=32768)s+=String.fromCharCode.apply(null,b.subarray(i,i+32768));
window.__p2z_b64=btoa(s);return {pdf:true,size:b.length,b64len:window.__p2z_b64.length}}catch(e){return {pdf:false,error:String(e)}}})()""")
CHUNK_JS = "/*p2z:chunk*/(()=>{const s=window.__p2z_b64;return typeof s==='string'?s.slice(__A__,__B__):null})()"
CLEAR_JS = "/*p2z:clear*/(()=>{delete window.__p2z_b64;return true})()"


class Browser:
    def __init__(self, session="p2z", window="background"):
        self.session, self.window = session, window

    def run(self, *args, timeout=EVAL_TIMEOUT, window=False):
        """One `opencli browser` command in this session -> (its result's data, None) or (None, the error)."""
        argv = ["opencli", "browser", *args, "--session", self.session] + (["--window", self.window] if window else [])
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            raise Stop("no_opencli", exit=CANNOT, hint="opencli is not on PATH: references/install.md.") from None
        except subprocess.TimeoutExpired:
            return None, f"opencli {args[0]} timed out"
        try:
            got = json.loads(p.stdout)
        except ValueError:
            return None, ((p.stderr or p.stdout).strip().splitlines() or [f"exit {p.returncode}"])[-1]
        if isinstance(got, dict) and got.get("ok"):
            return got.get("data"), None
        error = (got.get("error") if isinstance(got, dict) else None) or {}
        return None, (error.get("message") or error.get("code") or f"exit {p.returncode}").splitlines()[0]

    def answer(self, *args):
        """An opencli command whose data is an object -> the object, {} on any failure."""
        data, _ = self.run(*args)
        return data if isinstance(data, dict) else {}

    def get(self, what):
        """The current page's url, title or html -> the string, "" on any failure."""
        data, _ = self.run("get", what)
        return data if isinstance(data, str) else ""

    def open(self, url, front=False):
        """Navigate the session's tab (front: in a foreground window, for the user) -> None, or the error."""
        window, self.window = self.window, "foreground" if front else self.window
        try:
            return self.run("open", url, timeout=OPEN_TIMEOUT, window=True)[1]
        finally:
            self.window = window

    def eval(self, js, timeout=EVAL_TIMEOUT):
        """Run js in the page -> (the value it answers, None) or (None, the error)."""
        return self.run("eval", js, timeout=timeout)

    def value(self, js):
        """eval() of a snippet that answers an object -> the object, {} on any failure."""
        got, _ = self.eval(js)
        return got if isinstance(got, dict) else {}

    def carry(self, total):
        """The base64 the last snippet left in the page -> bytes, or None."""
        parts = []
        for start in range(0, total, CHUNK):
            chunk, _ = self.eval(CHUNK_JS.replace("__A__", str(start)).replace("__B__", str(start + CHUNK)))
            if not isinstance(chunk, str) or not chunk:
                return None
            parts.append(chunk)
        self.eval(CLEAR_JS, timeout=30)
        try:
            return base64.b64decode("".join(parts)) if parts else None
        except ValueError:
            return None

    def document(self):
        """The current document's identity (its performance.timeOrigin): a navigation changes it, even to the same
        address; a download keeps it -> a number, or None."""
        got, _ = self.eval("performance.timeOrigin")
        return got if isinstance(got, (int, float)) else None

    def find(self):
        """The current page: {href, title, doc (as document()), viewer, meta: {name: content}, candidates: [{url, why,
        text?, near?}]}, best first."""
        return self.value(FIND_JS)

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
        html = self.get("html")
        return (html.encode(), self.get("url")) if html.strip() else (None, None)

    def text(self):
        """The current page: {href, title, text: its body as Markdown (the first 20000 characters)}, {} on failure."""
        got = self.answer("extract", "--selector", "body", "--chunk-size", "20000")
        return {"href": got.get("url"), "title": got.get("title"), "text": got.get("content") or ""} if got else {}

    def controls(self):
        """The labels of the current page's links and buttons: aria-label and text."""
        got = self.answer("find", "--css", "a,button,[role=button]", "--limit", "1000", "--text-max", "60")
        labels = (" ".join(filter(None, ((e.get("attrs") or {}).get("aria-label"), e.get("text"))))
                  for e in got.get("entries") or [])
        return [" ".join(t.split()) for t in labels if t.strip()]

    def anchors(self):
        """The current page's links with their text: [{text, href}], each href absolute."""
        base = self.get("url")
        got = self.answer("find", "--css", "a[href]", "--limit", "5000", "--text-max", "500")
        return [{"text": " ".join(e["text"].split()), "href": urljoin(base, e["attrs"]["href"])}
                for e in got.get("entries") or []
                if (e.get("text") or "").strip() and (e.get("attrs") or {}).get("href")]

    def shows(self, until):
        """Whether the current page shows `until`: an element it selects, or its text."""
        return (bool(self.answer("find", "--css", until, "--limit", "1").get("matches_n"))
                or self.run("wait", "text", until, "--timeout", "1000")[1] is None)
