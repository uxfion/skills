# Gates

Read when a page in the `pf` session asks for something only the user can give, or `fetch` stops with `gate: true`.

## What a gate is

A gate is anything the user can pass and you cannot: the institution's single sign-on asking for a password, a CAPTCHA ("Are you a robot?", "verify you are human"), a cookie wall, an authorization prompt, a purchase page whose institutional sign-in you have already clicked, Chrome or the OpenCLI extension not running, a Save As dialog. Recognise one by its markers: page title "请稍候…" / "Just a moment…" / "Are you a robot?", `input[name=cf-turnstile-response]`, `#captcha-box`, "Get access". Read `state` (URL and title) after **every** navigation or click on a publisher site, because a gate is an unexpected page, not an error.

A login form is not yet a gate. The single sign-on is often still alive: the discovery system's own "Sign in" control, then the institution entry of its "Login using:" dialog, signs in at once, and after that the proxy's own username and password form lets the next request through (references/publishers.md, *Discovery systems and aggregators*). Those clicks are yours. Only a password prompt on the single sign-on itself is the user's.

## At a gate

The moment a marker shows, alert first — before any further `wait` or `state`, even when the widget says it has verified and is waiting — then watch it; it may pass by itself, and the alert cost nothing.

Wait at a gate once per pass. **Alert the user** with a push notification (load the tool if it is deferred) — and, when you are a subagent, a `SendMessage` to the main conversation with the same line, since only the main conversation reaches the user's screen. Say which page waits and what to do. When `fetch` stopped on it (`gate: true`), the page is in front of the user already; a gate page you or the browser agent reached, open there (`opencli browser open <url> --session pf --window foreground`). Every click on the way to it is the browser agent's: what reaches the user is the gate itself, already in front of them. They pass it in that tab (sign in, tick the box); a login holds for the whole of Chrome. *Then* wait up to 5 minutes, reading the page only:

```bash
uv run scripts/pf.py wait <result>   # --until "Access provided by": text or selector only the passed gate shows
```

`--until` names what only the page *after* the gate shows; a word the gate page itself carries (the Zotero Connector's proxy banner names the publisher's host) ends the wait at once. It looks at the tab and at the paper's file every 10 seconds and ends on whichever comes first:
- `arrived` — the file came another way (the user downloaded it): go on with the next paper. The gate itself was not passed, so the next paper behind it may wait afresh.
- `passed` — the page shows `--until`, or, without it, its URL or title changed: continue where you stopped.
- `timeout` after 5 minutes: record `pf.py fetch --pass N --verdict gate_timeout <result>`, leave the gate tab as it is, open a new tab for what follows (`opencli browser tab new --session pf`, then `tab select` it), and rerun `fetch`, which takes the paper's next route. Other papers behind the same gate skip that route for the rest of the pass: `pf.py fetch --pass N --route publisher --verdict gate_timeout <their results>`; the next pass meets the gate afresh.

A login from another window leaves the gate tab as it was, so the user's word ("登好了") is what ends that wait: run it in the background where the harness tells you when a command ends, so their reply reaches you meanwhile, and stop it when the reply comes; in the foreground, give the command a timeout above 300 s. Record every gate you hit (page, time, what you were doing) for the report.

## Pages nobody can pass

The proxy's "Host Needed", a site's block page: not gates. Tell the user at once, record the verdict, and leave that host alone for the rest of the run (references/publishers.md, *Pages nobody can pass*). A missing subscription concerns one paper; the next paper on the same site is tried as usual.
