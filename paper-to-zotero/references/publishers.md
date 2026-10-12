# Publisher sites: what the tools will not tell you

Context for step 3 of [`paper-to-zotero`](../SKILL.md), learned from real runs. Commands belong to the `opencli-browser` skill; this file holds only what is specific to fetching paper PDFs. Add a publisher once a run has verified it, and mark guesses as unverified. Every file from any source — an open-access link, a discovery system, a click — is the paper only once `check_pdf.py` says so: a correction notice, another paper and a proxy's error page all arrived looking right (2026-10).

## Chrome's PDF setting decides everything

The flow needs Chrome set to **download** PDFs: `chrome://settings/content/pdfDocuments` → "Download PDFs" (隐私和安全 → 网站设置 → 更多内容设置 → PDF 文档 → 下载 PDF 文件). Only the user can change it: browser automation cannot open `chrome://` pages, so this is a gate.

- Setting on: a top-level navigation to a PDF downloads it. A PDF embedded in a page (`iframe` / `embed`) shows a placeholder with an "Open / 打开" button instead; navigating the tab to the embedded URL is what that button does.
- Setting off (built-in viewer): once a tab shows a PDF, every command on that tab fails with `attach_failed … Cannot access a chrome-extension:// URL of different extension`. The viewer is itself an extension, and one extension cannot attach to a tab hosting another. The `opencli-browser` docs diagnose this message as a 1Password conflict; on a PDF tab it is the viewer. Ask the user to switch the setting, then restart step 3 in a fresh session.
- "Ask where to save each file before downloading" turned on: a click that should download instead opens the system's Save As dialog, which automation cannot see — it looks like "nothing happened". Ask the user to confirm the dialog or turn the option off.

## Reach of browser automation

Page content only. Browser chrome is out of reach: extension toolbar buttons (so the Zotero Connector plugin cannot be driven), extension shortcuts such as `Ctrl+Shift+S`, the PDF viewer's save button, native dialogs.

Recognising the downloaded file: `opencli browser <session> wait download <narrow pattern>` — a substring of the expected filename or URL, such as the DOI suffix or arXiv id. Verified 2026-09: it does not report earlier downloads, it returns the full path of the new file, and a second call after completion times out rather than re-reporting. Run it right after the click with a generous `--timeout`; publisher PDFs of 10 MB can take half a minute. A download that finished before the call — while the user was passing a gate, or because the user clicked the PDF button for you — is invisible to it: look in the Downloads folder for files newer than the run's `.started` marker before clicking anything again, and before every wait. Two downloads of one paper happen (2026-10); the second copy is not attached again.

## Getting the bytes (verified 2026-10)

In order of preference, once the article page has loaded and any gate is passed:

1. **In-page request.** `fetch(<PDF link>, {credentials: 'include'})` inside the article page, then take the bytes out base64-encoded in chunks through `browser eval`. A `content-type` of PDF is the file; HTML means no access, or a gate the session has not passed. Nothing lands in Downloads and the PDF viewer is never involved. Take the link from the page (`citation_pdf_url`, the "Download PDF" anchor), never from a pattern.
2. **Open the link in the tab**, as a click would, when the in-page request is refused (403, HTML, a cross-origin `TypeError`). With the download setting on, Chrome downloads it; catch it with `wait download` and the Downloads scan.
3. **A PDF inside a pdf.js viewer** (aggregator readers): `PDFViewerApplication.pdfDocument.getData()` in the frame that hosts the viewer gives the bytes; take them out the same way.

On a proxied page (next section) `citation_pdf_url` still names the publisher's own host; fetched from the proxied origin it is a cross-origin request without the proxy's cookies, and comes back as HTML. When the current host is a proxied form of the link's host, request only the link's path on the current origin.

## The Zotero Connector's proxy redirect (verified 2026-10)

The user's Zotero Connector sends publisher hosts it has associated with the institution's proxy (EZproxy) through that proxy; the page shows "Zotero automatically associated <host> with a previously defined proxy". Two articles of one publisher may go different ways — one redirected, one not — and the association, once made, sticks. A host the proxy does not cover then lands on the proxy's **"Host Needed"** page or a **404 on the proxy host**: the institution has no access through this route. That is not a gate and not worth retrying; record it for the host, tell the user once, and take the next route (an open copy, the discovery system). An open-access journal reached this way (JAMA Netw Open via jamanetwork.com) was blocked although it needs no proxy at all: open-access articles go to their un-proxied address or PMC first.

## Gates that do not look like login pages

All of these are solved by the user in seconds — alert them and wait at the gate instead of working around it:

- Chrome not running, or the OpenCLI bridge extension not connected (every `opencli browser` call fails to attach).
- A purchase / "Get access" page with no login prompt: the subscription is not recognised. Click the site's institutional sign-in entry ("Institutional Sign In", "Access through your institution") first; the login page that follows is the gate.
- A CAPTCHA or "verify you are human" page, on the publisher or on a search engine — sometimes only on the PDF link, after the article page loaded fine (PMC).
- A Cloudflare check ("请稍候…" / "Just a moment…"). In the automation tab it usually passes by itself within 10–15 s (NEJM AI, Lancet, JAMA, OUP; 2026-10); one morning it looped on "verification successful, waiting for response" on several publishers and passed in the afternoon. Alert the user and wait at least 30 s; if it loops, ask the user to click the box. Only a check that still loops goes on the list for the user to fetch by hand.
- A cookie wall ("Cookies must be enabled"): the user allows cookies and reloads.
- The Save As dialog above.

## Pages nobody can pass

Not gates: waiting does not help and the user cannot fix them by logging in. Recognise them, tell the user once per host the first time one shows (before moving on, not only in the report), and do not send that host another request this run.

| page | meaning | next |
| --- | --- | --- |
| "Host Needed", or a 404 on the proxy host | the proxy does not cover this publisher | open copy, discovery system, or the no-PDF branch |
| institution logo **and** "<institution> does not subscribe to this content" | no subscription (ScienceDirect shows this; see below) | the same |
| Cloudflare "Sorry, you have been blocked / You are unable to access <host>", no checkbox | the site has blocked the whole browser, the user's own visits included (medRxiv, 2026-10, after a few automated requests) | stop every request to the host, tell the user; Europe PMC or the server's API for the metadata |
| OpenReview `/pdf?id=…` and `api2.openreview.net/notes?id=…` answering 403 for a conference not held yet | not public yet (NeurIPS 2026 in 2026-10; ICLR, ICML, COLM of the same year worked) | the arXiv version, else a text-only snapshot of the conference's virtual page; the report says to attach the PDF after the conference |

## Open copies and metadata services (2026-10)

- **PMC**: a plain HTTP client gets a JavaScript verification page, so PMC is a browser route. The article page may open on a cookie wall and the PDF link (`…/articles/PMC<n>/pdf/main.pdf`) on a reCAPTCHA — two gates in a row; once passed, the same link downloads. The file arrives as `main.pdf`, so name the attachment yourself (`attach_file.py --filename`). Lancet and BMJ papers on PMC had no PDF.
- **Europe PMC**: `?pdf=render` returns HTML, not the PDF.
- **medRxiv / bioRxiv**: behind Cloudflare, which blocks the browser after a few programmatic requests (table above). Leave generous gaps between papers, keep requests in one session few, and prefer their API and Europe PMC.
- **Rate limits seen**: the arXiv API answered 429 after about 60 calls; OpenReview searches hit `ChallengeRequiredError` after about 45, for curl and the opencli adapter alike; DBLP was unreachable from one machine. Parallel subagents share these limits.
- **Open-access links** from OpenAlex and others can point at an unrelated paper; an institutional repository entry can be metadata without a PDF. An open copy counts only once its file has passed `check_pdf.py`.

## Conference proceedings (plain HTTP, verified 2026-10)

The published version of most ML and vision conference papers is a free file; take the link from the paper's page or the volume listing, not from a pattern.

- **NeurIPS** (`proceedings.neurips.cc`): the paper page `/hash/<h>-Abstract-<track>.html` links `/file/<h>-Paper-<track>.pdf`, which is the main text only — the appendix is a separate Supplemental file, attached only when asked. The 2025 main track is listed at `/paper_files/paper/2025/vol38-main-conference`. 2022–2025 papers carry a Crossref DOI `10.52202/…` that resolves to the printed proceedings' sales page (SKILL.md step 2 says where it goes).
- **ICLR**: `proceedings.iclr.cc` for 2024–2026 (not 2023); earlier years only OpenReview and the conference's virtual pages.
- **OpenReview**: inside an OpenReview page, `api2.openreview.net/notes/search?term=<title>` finds the forum id; a paper often has a CoRR and a conference note — choose by `venue`. `/pdf?id=<forum>` fetched in-page works for public papers.
- **PMLR**: PDF links on the volume page now point to `raw.githubusercontent.com/mlresearch/v<volume>/main/assets/<id>/<id>.pdf`, which downloads directly; the old URL pattern is wrong.
- **CVF Open Access**: replace `/html/` by `/papers/` in the paper page's URL.
- **ACL Anthology** (TACL volumes included) and **MICCAI** (`papers.miccai.org`, "Main Paper (Open Access Version)").

## Discovery systems and aggregators (verified 2026-10, by hand)

When the publisher says no access, the institution may still have the paper through an aggregator, and only its library discovery system knows. In one run three of four such papers were in ProQuest.

- **Primo** (Ex Libris): the search page's own request, `primaws/rest/pub/pnxs`, returns for every result `pnx.links.linktopdf` / `linktohtml` / `linkunpaywall`, readable without parsing the page. Its links are not always right: one PDF link for a JAMIA paper downloaded a JMIR paper, twice.
- **ProQuest**: `<proxied ProQuest host>/docview/<id>/fulltextPDF` shows the PDF in a same-origin pdf.js iframe with no outer download link; wait for `iframe.contentWindow.PDFViewerApplication.pdfDocument` and take the bytes with `getData()`. "Get PDF" in the discovery system opens a new tab that does not belong to the opencli session, and `bind` may grab an older tab instead — open the `fulltextPDF` page in the session yourself. A paper the discovery system does not index can be searched in ProQuest directly by title. Other aggregators appear in the facets (Journals@Ovid, EBSCOhost).

## Verified publishers

### IEEE Xplore (2026-09)

- A subscribed article page shows "Access provided by: <institution>".
- The PDF button (`a[href*='stamp.jsp']`, text "PDF") opens a viewer page whose `iframe` (`stampPDF/getPDF.jsp?…`) is the real PDF, so the embedded-URL move always applies. The selector matches two links on the article page (`--nth 0`); simpler is to open the viewer page directly, `<host>/stamp/stamp.jsp?tp=&arnumber=<n>`, read the iframe's `src` with `browser eval`, and open that — the download then starts and `wait download <arnumber>` catches it (verified 2026-09).
- After an institutional login the site may be served from an EZproxy host (`ieeexplore-ieee-org.<proxy-domain>`); it behaves identically. Store the canonical `ieeexplore.ieee.org` URL on the attachment, not the proxy host.
- Abstract and keywords: `xplGlobal.document.metadata` on the article page (`abstract`, `keywords[].kwd`). The "IEEE Keywords" list there is index terms generated by IEEE, not the authors' keywords; the authors' own list is labelled "Author Keywords".
- CVPR / ICCV papers usually have a free copy on CVF Open Access.
- Every download is stamped with the licensee and date, so two downloads of one paper never share an MD5: match a leftover in Downloads to its attachment by title and key, not by hash.

### ScienceDirect / Elsevier (2026-09, partially)

- The first visit in a browser session hits a Cloudflare Turnstile page (title "请稍候…" / "Just a moment…", `#captcha-box`, `input[name=cf-turnstile-response]`); it usually passes by itself within ~20 s, but it is a gate: alert first, then watch.
- Institutional access is shown by `#gh-inst-icon-btn` (aria-label "<institution> Institutional Access") or a logo `img` whose alt reads "You have institutional Access via <institution>". **No subscription** looks like: that logo present, `div[data-testid=no-access-banner]` saying "<institution> does not subscribe to this content on ScienceDirect", the URL rewritten from `/science/article/pii/<PII>` to `/science/article/abs/pii/<PII>`, only "Purchase PDF" and "Access through another organization" offered, no `a[href*='pdfft']`. That is not a gate: take the no-PDF branch.
- An unsubscribed abstract page renders no keywords block at all; the authors' keywords and the abstract come from PubMed instead (`pubmed search "<title words>"` → the hit with the same DOI → `pubmed article <pmid> --full-abstract`), which also gives the PMID for `extra`.
- With access (unverified): "View PDF" opens a reader under `/pdfft`. Article pages are addressed by PII; the DOI is in the page's `citation_doi` meta tag, or resolve PII → DOI through Crossref: `https://api.crossref.org/works?filter=alternative-id:<PII>`. Author keywords: `div.keywords-section .keyword` (they match PubMed's author keywords).

### Others (2026-10, one batch of about 35 papers, logged in)

- **In-page request of `citation_pdf_url` worked**: PNAS, Patterns (Cell Press), BMJ, Nature, CHI and FAccT papers on their publisher pages.
- **OUP** (JAMIA, JAMIA Open): a short Cloudflare check that passes by itself; the in-page request often returns an empty document or HTML, while opening the PDF link makes Chrome download the file.
- **ACM Digital Library**: the in-page request answered 403; the user's click on the PDF button downloaded the file.
- **nature.com journals** (Nat Med, Nat Biomed Eng), **NEJM AI**, **Science**: the PDF link returns HTML, opened directly too — mostly no subscription; Science through the proxy is "Host Needed".
- **Nature portfolio "Article in Press"** pages and their `_reference.pdf` files (npj journals) are the **unedited accepted manuscript**, not the typeset version: record `file_version: accepted`, and replace the attachment once the typeset PDF is out.
- **jamanetwork.com**: "Host Needed" through the proxy, 403 without it — open-access JAMA Netw Open articles included; take them from PMC.

## Unverified expectations

- Springer / Nature: `citation_pdf_url` is the PDF itself, so the "Download PDF" button should download directly. Author keywords are in `citation_keywords` meta tags. Observed 2026-09: the institutional sign-in runs through `wayf.springernature.com` — that page is the gate; an unsubscribed chapter shows only a preview and a "Log in via an institution" entry.
- Wiley: the button opens an `/doi/epdf/` reader; the file lives under `/doi/pdfdirect/`.

## Symptoms

| symptom | meaning | next move |
| --- | --- | --- |
| click, then `wait download` times out and no `.crdownload` appears | the click opened a viewer page, or the Save As dialog is up | navigate to the embedded PDF's URL; if that fails too, check the PDF setting and the Save As option |
| `.crdownload` lingers | large file or slow link | keep waiting |
| the user says the file downloaded, but `wait download` timed out | the download finished before or outside the wait | list Downloads newer than `.started`, check that file and attach it — do not click again |
| `wait text` / `wait selector` answers `detached_mid_command` | the tab navigated while waiting (a login redirect does this) | poll `state` every 15 s instead; the gate is still the same gate |
| `attach_failed … chrome-extension://` | built-in PDF viewer is on | PDF setting above |
| downloaded "PDF" is HTML, or its text is a login / access-denied page | the gate was not really passed | wait at the gate again |
| in-page request of the PDF link returns HTML on a proxied host | cross-origin request without the proxy's cookies | request the link's path on the current origin |
| "Host Needed", a 404 on the proxy host, "Sorry, you have been blocked" | a page nobody can pass | table above: tell the user once, leave the host alone |
| paywalled page without "Access provided by", offering purchase | no subscription, or the login expired | institutional sign-in entry, then the gate; still nothing → discovery system, open copy, or the no-PDF branch |
| institution logo shown *and* a "does not subscribe" banner, URL contains `/abs/` | the institution has no subscription — not a gate | do not click purchase; look once for an open copy, else save the item without a PDF and say why |
| every `opencli browser` call fails to attach | Chrome closed or the bridge extension disconnected | gate: ask the user |
