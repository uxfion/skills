# Publisher sites: what the tools will not tell you

Context for step 3 of [`paper-to-zotero`](../SKILL.md), learned from real runs: what to do when `fetch` stops on a page and the page is yours to work. Commands belong to the `opencli-browser` skill; this file holds only what is specific to fetching paper PDFs. Add a publisher once a run has verified it, and mark guesses as unverified; when a site behaves differently from what is written here, follow the page and say so in the report's skill notes. Every file from any source — an open-access link, a discovery system, a click — is the paper only once it has gone through `claim` (which checks it): a correction notice, another paper and a proxy's error page all arrived looking right (2026-10).

## Chrome's PDF setting decides everything

The flow needs Chrome set to **download** PDFs: `chrome://settings/content/pdfDocuments` → "Download PDFs" (隐私和安全 → 网站设置 → 更多内容设置 → PDF 文档 → 下载 PDF 文件). Only the user can change it: browser automation cannot open `chrome://` pages, so this is a gate.

- Setting on: a top-level navigation to a PDF downloads it. A PDF embedded in a page (`iframe` / `embed`) shows a placeholder with an "Open / 打开" button instead; navigating the tab to the embedded URL is what that button does.
- Setting off (built-in viewer): once a tab shows a PDF, every command on that tab fails with `attach_failed … Cannot access a chrome-extension:// URL of different extension`. The viewer is itself an extension, and one extension cannot attach to a tab hosting another. The `opencli-browser` docs diagnose this message as a 1Password conflict; on a PDF tab it is the viewer. Ask the user to switch the setting, then restart step 3 in a fresh session.
- "Ask where to save each file before downloading" turned on: a click that should download instead opens the system's Save As dialog, which automation cannot see — it looks like "nothing happened". Ask the user to confirm the dialog or turn the option off.

## Reach of browser automation

Page content only. Browser chrome is out of reach: extension toolbar buttons (so the Zotero Connector plugin cannot be driven), extension shortcuts such as `Ctrl+Shift+S`, the PDF viewer's save button, native dialogs.

Downloads: the watcher (SKILL.md step 0) files whatever lands in Downloads, so a click needs no `wait download`. Opening a link that downloads leaves the tab on its old page, in the same document (2026-10). PMC's PDF link took 45–60 s from `open` to the file (2026-10-20). `opencli browser wait download <pattern> --timeout <ms> --session p2z` (OpenCLI 2.x) answers only once a matching download has completed or failed, and also counts one completed within the last `--timeout` before the call; it cannot tell a download not yet started from none coming (OpenCLI source, 2026-10-20).

## Getting the bytes (verified 2026-10)

`fetch` does these in order for each PDF candidate a page offers (its declared PDF, an embedded document or viewer, a link saying PDF; three at most), and looks once more through an HTML page a link opens; when it stops, do the same by hand where the page needs it (a button it could not see, a gate):

1. **In-page request.** `fetch(<PDF link>, {credentials: 'include'})` inside the article page, the bytes taken out base64-encoded in chunks through `browser eval`. A `content-type` of PDF is the file; HTML means no access, or a gate the session has not passed. Nothing lands in Downloads. Take the link from the page (`citation_pdf_url`, the "Download PDF" anchor), never from a pattern.
2. **Open the link in the tab**, as a click would, when the in-page request is refused (403, HTML, a cross-origin `TypeError`). With the download setting on, Chrome downloads it; the watcher (`claim --watch`) files it from Downloads.
3. **A PDF inside a pdf.js viewer** (aggregator readers): `PDFViewerApplication.pdfDocument.getData()` in the frame that hosts the viewer gives the bytes; `fetch` reads a viewer it lands on.

On a proxied page (next section) `citation_pdf_url` still names the publisher's own host; fetched from the proxied origin it is a cross-origin request without the proxy's cookies, and comes back as HTML. When the current host is a proxied form of the link's host, request only the link's path on the current origin (`fetch` does this when the config names the proxy). A plain `http://` link on an `https://` page (PMLR) is refused as mixed content: same fix.

## The Zotero Connector's proxy redirect (verified 2026-10)

The user's Zotero Connector sends publisher hosts it has associated with the institution's proxy (EZproxy) through that proxy; the page shows "Zotero automatically associated <host> with a previously defined proxy". Two articles of one publisher may go different ways — one redirected, one not — and the association, once made, sticks. A host the proxy does not cover then lands on the proxy's **"Host Needed"** page or a **404 on the proxy host**: the institution has no access through this route. That is not a gate and not worth retrying; tell the user once, leave that proxied host alone for the rest of the run, and take the paper's next route (an open copy, the discovery system). An open-access journal reached this way (JAMA Netw Open via jamanetwork.com) was blocked although it needs no proxy at all: open-access articles go to their un-proxied address or PMC first.

## Gates that do not look like login pages

All of these are solved by the user in seconds — alert them and wait at the gate instead of working around it:

- Chrome not running, or the OpenCLI bridge extension not connected (every `opencli browser` call fails to attach).
- A purchase / "Get access" page with no login prompt: the subscription is not recognised. Click the site's institutional sign-in entry ("Institutional Sign In", "Access through your institution") first; the login page that follows is the gate.
- A CAPTCHA or "verify you are human" page, on the publisher or on a search engine — sometimes only on the PDF link, after the article page loaded fine (PMC).
- A Cloudflare check ("请稍候…" / "Just a moment…"). In the automation tab it usually passes by itself within 10–15 s (NEJM AI, Lancet, JAMA, OUP; 2026-10); one morning it looped on "verification successful, waiting for response" on several publishers and passed in the afternoon. Alert the user and wait at least 30 s; if it loops, ask the user to click the box. Only a check that still loops goes on the list for the user to fetch by hand.
- A cookie wall ("Cookies must be enabled"): the user allows cookies and reloads.
- The Save As dialog above.

## Pages nobody can pass

Not gates: waiting does not help and the user cannot fix them by logging in. Record the verdict for the paper (`p2z.py fetch --pass N --verdict <word> <record>`), tell the user the first time one shows (before moving on, not only in the report), and take the paper's next route. Two of them close a whole host for the run; the others are about this one paper, and the next paper on the same site is tried as usual — a subscription covers journals, not sites.

| page | meaning | scope | verdict |
| --- | --- | --- | --- |
| "Host Needed", or a 404 on the proxy host | the proxy does not cover this publisher | that proxied host, this run | `proxy_unconfigured` |
| Cloudflare "Sorry, you have been blocked / You are unable to access <host>", no checkbox | the site has blocked the whole browser, the user's own visits included (medRxiv, 2026-10, after a few automated requests) | that host, this run: stop every request to it | `site_blocked` |
| institution logo **and** "<institution> does not subscribe to this content" | no subscription to this journal (ScienceDirect shows this; see below) | this paper | `no_access` |
| a purchase page after the institutional sign-in was clicked and passed | no access to this paper | this paper | `no_access` |
| OpenReview `/pdf?id=…` and `api2.openreview.net/notes?id=…` answering 403 for a conference not held yet | not public yet (NeurIPS 2026 in 2026-10; ICLR, ICML, COLM of the same year worked) | this paper | `not_public`: take the arXiv version; the report says to attach the PDF after the conference |

## Open copies and metadata services (2026-10)

- **PMC**: a plain HTTP client gets a JavaScript verification page, so PMC is a browser route (`p2z.py fetch --pass N --start <PMC article URL> <record>`). The article page may open on a cookie wall and the PDF link (`…/articles/PMC<n>/pdf/main.pdf`) on a reCAPTCHA — two gates in a row; once passed, the same link downloads. Lancet and BMJ papers on PMC had no PDF.
- **Europe PMC**: `?pdf=render` returns HTML, not the PDF.
- **medRxiv / bioRxiv**: behind Cloudflare, which blocks the browser after a few programmatic requests (table above). Leave generous gaps between papers, keep requests in one session few, and prefer their API and Europe PMC.
- **Rate limits seen**: the arXiv API answered 429 after about 60 calls; OpenReview searches hit `ChallengeRequiredError` after about 45, for curl and the opencli adapter alike; DBLP answered with a bot check from one machine. Parallel subagents share these limits.
- **Open-access links** from OpenAlex and others can point at an unrelated paper; an institutional repository entry can be metadata without a PDF. An open copy counts only once its file has passed the check.
- **opencli `browser network`**: its capture is read once — a second call returns `count: 0`. Save the output to a file first, then take keys from the file for `--detail`.

## Conference proceedings (plain HTTP, verified 2026-10)

The published version of most ML and vision conference papers is a free file; take the link from the paper's page or the volume listing, not from a pattern.

- **NeurIPS** (`proceedings.neurips.cc`): the paper page `/hash/<h>-Abstract-<track>.html` links `/file/<h>-Paper-<track>.pdf`, which is the main text only — the appendix is a separate Supplemental file, attached only when asked. The 2025 main track is listed at `/paper_files/paper/2025/vol38-main-conference`. 2022–2025 papers carry a Crossref DOI `10.52202/…` that resolves to the printed proceedings' sales page (SKILL.md step 2 says where it goes).
- **ICLR**: `proceedings.iclr.cc` for 2024–2026 (not 2023); earlier years only OpenReview and the conference's virtual pages. Its pages carry `citation_*` meta, so `doi_to_item.py --redraft <page URL>` drafts the item; NeurIPS, PMLR and ACL Anthology pages too (verified 2026-10). OpenReview-only venues (ICLR ≤ 2023, TMLR) put a challenge in front of scripts: draft the item from the papers.cool card and the forum page you read in the browser.
- **OpenReview**: inside an OpenReview page, `api2.openreview.net/notes/search?term=<title>` finds the forum id; a paper often has a CoRR and a conference note — choose by `venue`. `/pdf?id=<forum>` fetched in-page works for public papers.
- **PMLR**: PDF links on the volume page now point to `raw.githubusercontent.com/mlresearch/v<volume>/main/assets/<id>/<id>.pdf`, which downloads directly; the old URL pattern is wrong.
- **CVF Open Access**: replace `/html/` by `/papers/` in the paper page's URL.
- **ACL Anthology** (TACL volumes included) and **MICCAI** (`papers.miccai.org`, "Main Paper (Open Access Version)").

## Discovery systems and aggregators (verified 2026-10)

When the publisher says no access, the institution may still have the paper through an aggregator, and only its library discovery system knows: in one run three of four such papers were in ProQuest. `fetch`'s discovery route searches the title there, takes the result links whose text is the title, and works each record page; read on when it stops on one. The system's address is the config's `institution.discovery`, a search URL (the value stays in the local config, never in this repo).

- **Signed out**: a guest search shows only part of the results, so a paper that is there may be missing. Primo shows it twice: a "Sign in" control beside the account menu (whose own label stays "Open user actions menu button") and a notice "Sign in to get complete results and to request items". `fetch` stops on either with `why: sign_in`. Sign in through the page: the "Sign in" control, then the "Login using:" dialog's institution entry (not "External users"), leads to the institution's single sign-on; with its session still alive it signs in at once, else username and password are the user's — a gate (verified 2026-10-20).
- **Primo NDE** (Ex Libris): each result is an anchor to `fulldisplay?…&docid=…`, and the docid names the source — `cdi_crossref_primary_<doi>` (the published article), `cdi_proquest_journals_<docview id>`, `cdi_arxiv_primary_<id>` (the preprint). The full record lists "Get PDF" and "Read online" links per provider. The same title can come back three times (publisher, ProQuest, arXiv); a ProQuest record may hold the arXiv version. Its links are not always right: one PDF link for a JAMIA paper downloaded a JMIR paper, twice. The search page's own request (`primaws/rest/pub/pnxs`) carries the same links, but `browser network` captured nothing on 2026-10-18; the page is the reliable source.
- **ProQuest**: "Get PDF" leads to `docview/<id>/fulltextPDF`, which the proxy association opens through the institution: a same-origin pdf.js iframe with no outer download link, whose bytes `PDFViewerApplication.pdfDocument.getData()` gives (`fetch` reads such a viewer). Open these links in the session's own tab: "Get PDF" clicked on the page opens a tab that does not belong to the session. A paper the discovery system does not index can be searched in ProQuest directly by title. Other aggregators appear in the facets (Journals@Ovid, EBSCOhost).
- **Pacing**: licences forbid systematic downloading, and a proxy that sees too many full-text requests suspends the institution's account, not just this browser. `fetch.py` spaces every full-text request made through the institution 15 s apart; work done by hand on these sites keeps the same pace.

## Verified publishers

### IEEE Xplore (2026-09)

- A subscribed article page shows "Access provided by: <institution>".
- The page declares no `citation_pdf_url`; its PDF button (`stamp.jsp`, text "PDF") opens a reading page whose `iframe` (`stampPDF/getPDF.jsp?…`) is the real PDF, which `fetch` finds by looking through that page (by hand, verified 2026-10; through `fetch`, to verify on the next real run).
- After an institutional login the site may be served from an EZproxy host (`ieeexplore-ieee-org.<proxy-domain>`); it behaves identically.
- Abstract and keywords: `xplGlobal.document.metadata` on the article page (`abstract`, `keywords[].kwd`). The "IEEE Keywords" list there is index terms generated by IEEE, not the authors' keywords; the authors' own list is labelled "Author Keywords".
- CVPR / ICCV papers usually have a free copy on CVF Open Access: a route to the file, while the item stays the IEEE version.
- Every download is stamped with the licensee and date, so two downloads of one paper never share an MD5: match a leftover in Downloads to its attachment by title and key, not by hash.

### ScienceDirect / Elsevier (2026-09, partially)

- The first visit in a browser session hits a Cloudflare Turnstile page (title "请稍候…" / "Just a moment…", `#captcha-box`, `input[name=cf-turnstile-response]`); it usually passes by itself within ~20 s, but it is a gate: alert first, then watch.
- Institutional access is shown by `#gh-inst-icon-btn` (aria-label "<institution> Institutional Access") or a logo `img` whose alt reads "You have institutional Access via <institution>". **No subscription** looks like: that logo present, `div[data-testid=no-access-banner]` saying "<institution> does not subscribe to this content on ScienceDirect", the URL rewritten from `/science/article/pii/<PII>` to `/science/article/abs/pii/<PII>`, only "Purchase PDF" and "Access through another organization" offered, no `a[href*='pdfft']`. That is not a gate: `--verdict no_access` for this paper and on to its next route (the discovery system finds it more often than not); other ScienceDirect papers are tried as usual.
- An unsubscribed abstract page renders no keywords block at all; the authors' keywords and the abstract come from PubMed instead (`pubmed search "<title words>"` → the hit with the same DOI → `pubmed article <pmid> --full-abstract`), which also gives the PMID for `extra`.
- With access (unverified): "View PDF" opens a reader under `/pdfft`. Article pages are addressed by PII; the DOI is in the page's `citation_doi` meta tag, or resolve PII → DOI through Crossref: `https://api.crossref.org/works?filter=alternative-id:<PII>`. Author keywords: `div.keywords-section .keyword` (they match PubMed's author keywords).

### Others (2026-10, one batch of about 35 papers, logged in)

- **In-page request of `citation_pdf_url` worked**: PNAS, Patterns (Cell Press), BMJ, Nature, CHI and FAccT papers on their publisher pages.
- **OUP** (JAMIA, JAMIA Open): a short Cloudflare check that passes by itself; the in-page request often returns an empty document or HTML, while opening the PDF link makes Chrome download the file.
- **ACM Digital Library**: the in-page request answered 403; the user's click on the PDF button downloaded the file.
- **nature.com journals** (Nat Med, Nat Biomed Eng), **NEJM AI**, **Science**: the PDF link returns HTML, opened directly too — mostly no subscription; Science through the proxy is "Host Needed".
- **Nature portfolio "Article in Press"** pages and their `_reference.pdf` files (npj journals) are the **unedited accepted manuscript**, not the typeset version: label it `Accepted-Nature-in_press` (next section), and fetch the typeset PDF once it is out.
- **jamanetwork.com**: "Host Needed" through the proxy, 403 without it — open-access JAMA Netw Open articles included; take them from PMC.

## Versions on the page and on the file (2026-10)

Hints for a file's label ([attachment-titles.md](attachment-titles.md)), each seen on a few papers in October 2026. Publishers change their pages: what the page and the file in front of you show wins, and a marker that no longer holds goes into the report's skill notes.

- **IEEE Xplore**: the article page's `xplGlobal.document.metadata` has `isEarlyAccess: true` and `volume: "PP"` until the paper is in an issue (in_press). Page 1 of an Early Access file says which kind it is: "This is the author's version which has not been fully edited…" (`Accepted-IEEE-in_press`), or "accepted for inclusion in a future issue… Content is final as presented, with the exception of pagination" (`Published-IEEE-in_press`). An issue's article: no banner, a running head with volume, number and real pages. Early Access alone is no version: TNNLS's was typeset, TPAMI's and TIP's were author versions.
- **ScienceDirect**: an Article in Press page has no `citation_volume` and says "In Press, Journal Pre-proof" or "In Press, Corrected Proof"; the final page has volume (and issue) and no "In Press". A typeset proof PDF opens with `JID:… AID:… /REV … Prn:`, "••• (••••)" placeholders, "Available online xxxx" and a grey ARTICLE IN PRESS bar the text layer does not carry (`Published-Elsevier-in_press`). An accepted manuscript Elsevier shares (HAL and other repositories hold them) is headed "Version of Record: <ScienceDirect url>" and "Manuscript_<hash>", and closes with "This manuscript is made available under the CC BY NC user license"; its "Preprint submitted to <journal>" line is only the elsarticle template's. "View Open Manuscript" (`/science/article/am/pii/<PII>`, file `am.pdf`) is Elsevier's own accepted manuscript, free without a subscription (`Accepted-Elsevier`). The page may already be final while the file in hand is still the proof: label the file, not the page.
- **nature.com**: the page's `dataLayer` has `articleInPress` and `uneditedManuscript`; an Accelerated Article Preview page says "This version is subject to further edits and will be replaced automatically by the final Version of Record". In press, the PDF button points at `<id>_reference.pdf` while `citation_pdf_url` (`<id>.pdf`) answers HTML; once final, `<id>.pdf` is the final file and `_reference.pdf` is the earlier in-press file (or the same bytes). An older npj Article in Press PDF opens with "ARTICLE IN PRESS… We are providing an unedited version of this manuscript" (`Accepted-Nature-in_press`); the 2026 preview PDF says "Article in Press" on every page and nothing about editing.
- **RSNA (Radiology)**: a paper online before its issue prints "Radiology 2022; 000:1–8" (volume 000) on page 1 (`Published-RSNA-in_press`); the issue's version prints the volume and an article number ("2023; 306(3): e213199").
- **SpringerLink**: an unsubscribed chapter's `/content/pdf/<doi>.pdf` answers HTTP 204 with no body. A journal article's page says "Version of record <date>", and its PDF carries the journal's running head with volume and issue. The papers.miccai.org copy of a MICCAI chapter is the camera-ready (`Accepted-MICCAI`); supplementary files sit under `/esm/` (`…_MOESM1_ESM.pdf`).
- **ACM Digital Library**: a Just Accepted page shows that label at the head of the article with "Online AM: <date>" and no "Published:", volume, issue or pages (`Accepted-ACM-in_press`); the final page has "Published: <date>" with volume, issue and article number. The navigation bar on every page links "Just Accepted" too, and "Online AM" stays on final pages. A final PDF has "ACM Reference Format" and "Publication date:"; the Just Accepted PDF is the authors' own layout.
- **Wiley**: "Early View — Online Version of Record before inclusion in an issue", with no `citation_volume` or `citation_issue`, is the typeset final text not yet in an issue (`Published-Wiley-in_press`).
- **Open copies**: the CVF watermark is an image, and its words changed: CVPR 2016 to CVPR 2018 say "Except for this watermark, it is identical to the version available on IEEE Xplore" (`Published-CVF`; the page carries the proceedings' page number), CVPR 2019 to 2026 "identical to the accepted version; the final published version of the proceedings is available on IEEE Xplore" (`Accepted-CVF`). MICCAI's watermark, an image too (2024–2026): "identical to the accepted version, except for the format and this watermark; the final published version is available on SpringerLink" (`Accepted-MICCAI`). ECVA's copies carry no marker at all; a PMC author manuscript is `nihms-<id>.pdf` with "HHS Public Access / Author manuscript" on page 1; a HAL or eScholarship cover sheet cites the published version whatever the file is, so read page 2; a repository's own file label ("Accepted author manuscript") is the best evidence there is for its file. OpenReview's `content.venue` gives the status to copy ("ICLR 2027 Conference Submission", "ICLR 2025 Oral", "Accepted by TMLR"); `/pdf?id=<forum>` always serves the latest revision. An ACL Anthology `<id>.pdf` is the latest revision too: its revisions are `…v2.pdf`.

## Unverified expectations

- Springer / Nature: `citation_pdf_url` is the PDF itself, so the "Download PDF" button should download directly. Author keywords are in `citation_keywords` meta tags. Observed 2026-09: the institutional sign-in runs through `wayf.springernature.com` — that page is the gate; an unsubscribed chapter shows only a preview and a "Log in via an institution" entry.
- Wiley: the button opens an `/doi/epdf/` reader; the file lives under `/doi/pdfdirect/`.

## Symptoms

| symptom | meaning | next move |
| --- | --- | --- |
| click, then no file and no `.crdownload` in Downloads | the click opened a viewer page, or the Save As dialog is up | navigate to the embedded PDF's URL; if that fails too, check the PDF setting and the Save As option |
| `.crdownload` lingers | large file or slow link | keep waiting |
| the user says the file downloaded, but nothing was filed | the watcher is not running, or the file matched no record or several | `p2z.py claim --work <work> --scan`; a `left` line names the file — read it, then `p2z.py claim --work <work> --file <copy> --slug <slug>` files it through the check |
| `opencli browser wait text` / `wait selector` answers `detached_mid_command` | the tab navigated while waiting (a login redirect does this) | wait with `p2z.py wait <record>`, which reads the tab every 10 s and goes on through navigations |
| `attach_failed … chrome-extension://` | built-in PDF viewer is on | PDF setting above |
| downloaded "PDF" is HTML, or its text is a login / access-denied page | the gate was not really passed | wait at the gate again |
| in-page request of the PDF link returns HTML on a proxied host | cross-origin request without the proxy's cookies | request the link's path on the current origin |
| "Host Needed", a 404 on the proxy host, "Sorry, you have been blocked" | a page nobody can pass | table above: tell the user, leave the host alone this run |
| paywalled page without "Access provided by", offering purchase | no subscription, or the login expired | institutional sign-in entry, then the gate; still nothing → `--verdict no_access` and the paper's next route |
| institution logo shown *and* a "does not subscribe" banner, URL contains `/abs/` | no subscription to this journal — not a gate | `--verdict no_access` and the paper's next route; purchase is never one |
| every `opencli browser` call fails to attach | Chrome closed or the bridge extension disconnected | gate: ask the user |
