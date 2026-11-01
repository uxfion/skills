# paper-to-zotero: the proxy's login form — `fetch` names it neither a gate nor the agent's next click

Logged 2026-10-30, while saving the baseline for the split (spec `20261030-paper-to-zotero-split-spec.md` §10 step 0). After the split this belongs to paper-fetch's `fetch`.

**What was run.** `p2z.py fetch --pass 1` on three records, one of them `he2020mask` (Mask R-CNN, TPAMI, DOI `10.1109/TPAMI.2018.2844175`).

**What was seen.** The publisher route went to `https://doi.org/10.1109/tpami.2018.2844175`, and the Zotero Connector redirected it to the institution's EZproxy login. `fetch` stopped with:

```json
{"slug": "he2020mask", "code": "stopped", "route": "publisher", "why": "no_pdf_link", "gate": false,
 "url": "https://login.<proxy-domain>/login?qurl=…", "title": ""}
```

The page (`opencli browser state`) was a plain login form: empty `<title>`, the Connector's banner "Zotero automatically redirected your request to ieeexplore.ieee.org through the proxy at <proxy-domain>", then `Please enter your username: / Please enter your password:` with `input[name=user]`, `input[type=password]`, a Login button.

**What I did, and the user's correction.** I took the page for a gate: brought it to the front, sent a push alert, waited, then recorded `gate_timeout` for the publisher route, and again for the discovery route when `fetch` stopped there with `why: sign_in`. The user: 「这个你自己点击，这个问题之前遇到过的，在p2z中肯定也提到过」. `references/publishers.md` (*Discovery systems and aggregators*, *Signed out*) does say it: the discovery system's own "Sign in" control, then the institution entry of its "Login using:" dialog, leads to the institution's single sign-on, which signs in at once while its session is alive; only a password prompt there is the user's gate. I had not read publishers.md before working the stop, although SKILL.md points there for every page `fetch` stops on.

**What followed.** In pass 2, a few minutes later, the same publisher route went through the proxy without any form (the proxied IEEE page loaded), and the discovery system showed the user signed in. So the single sign-on was alive by then; whether the user signed in meanwhile or the session came back on its own is not known.

**Why it hurts.**
- `fetch` reports the proxy's login form as `no_pdf_link`, the same word as a page that loaded and offers no PDF. The hint ("hand it to a browser agent") is right, but nothing says which clicks get past it, so the stop is easy to mistake for a gate.
- SKILL.md's *Gate* lists "a login form" among the gate markers. That is true of the single sign-on's password page, not of the proxy's form while the single sign-on can still be reached through a click.

**Direction (to settle in paper-fetch).** Recognise the proxy's login form by its structure (`input[type=password]` on the proxy's login host), and give it a stop of its own, say `why: proxy_login`, whose hint names the move: sign in through the discovery system (publishers.md), then rerun. A password prompt on the single sign-on's host is the gate. One more title pattern is not the fix.

Also seen: `p2z.py wait --until ieeexplore` ended at once as `passed`, because the Connector's banner on the login page itself says "ieeexplore.ieee.org". `--until` must name something only the page *after* the gate shows. SKILL.md's example ("Access provided by") is right; the mistake was mine.
