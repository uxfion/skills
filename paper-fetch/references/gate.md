# Gates

Read when a page asks for something only the user can give. A paper agent meets the gate on its page and brings it to the front; the main conversation carries its line to the user.

## What a gate is

A gate is anything the user can pass and an agent cannot: the institution's single sign-on asking for a password, a CAPTCHA ("Are you a robot?", "verify you are human"), a cookie wall, an authorization prompt, a purchase page whose institutional sign-in has already been clicked, Chrome or the OpenCLI extension not running, a Save As dialog. Recognise one by its markers: page title "请稍候…" / "Just a moment…" / "Are you a robot?", `input[name=cf-turnstile-response]`, `#captcha-box`, "Get access". Read `state` (URL and title) after **every** navigation or click on a publisher site, because a gate is an unexpected page, not an error.

A login form is not yet a gate. The single sign-on is often still alive: the discovery system's own "Sign in" control, then the institution entry of its "Login using:" dialog, signs in at once, and after that the proxy's own username and password form lets the next request through (references/publishers.md, *Discovery systems and aggregators*). Those clicks are the paper agent's. Only a password prompt on the single sign-on itself is the user's.

## The paper agent at a gate

The moment a marker shows, alert first — before any further `wait` or `state`, even when the widget says it has verified and is waiting — then watch it; it may pass by itself, and the alert cost nothing. Wait at a gate once per pass.

1. Bring the page to the front: `opencli browser open <url> --session pf-<slug> --window foreground`. Every click on the way to it is yours: what reaches the user is the gate itself.
2. Send the main conversation one line (`SendMessage` with `to: "main"`; a subagent has no push notification of its own, so the main conversation pushes it): the paper, the page, what the user must do there.
3. Wait, reading the page only — about ten minutes, in one shell call with a timeout above the wait's (Claude Code: `timeout: 600000`):

```bash
uv run scripts/pf.py wait <result> --session pf-<slug>   # --until "Access provided by": text or selector only the passed gate shows
```

`--until` names what only the page *after* the gate shows; a word the gate page itself carries (the Zotero Connector's proxy banner names the publisher's host) ends the wait at once. It looks at the tab and at the paper's file every 10 seconds, and every minute opens the gate's address afresh in a tab of its own, since a login in another window leaves the gate's tab as it was. Nobody tells you when the user is through; the wait sees it, and ends on whichever comes first:
- `arrived` — the paper has its file (the user downloaded it): its `page` handoff has closed; `pf.py todo --dir <dir> --slug <slug>` says what is left.
- `passed` — `seen: tab`: the page shows `--until`, or, without it, its URL or title changed: go on where you stopped. `seen: fresh`: the fresh look got through: open the page again in your session and go on.
- `timeout` after about ten minutes: answer the `page` handoff `gate_timeout`, leave the gate tab as it is, and report. The paper is tried again at the next pass.

## The main conversation at a gate

On a paper agent's gate line, alert the user with a push notification (load the tool if it is deferred) and say in the conversation which paper waits, on which page, and what to do there; the page is in front of them already. They pass it in that tab (sign in, tick the box); a login holds for the whole of Chrome, so the other papers behind it pass too. Another paper agent that meets the same gate sends its own line: there is no list of gates to keep.

Nothing goes back to the agent: its wait sees the gate pass however the user passed it, and it goes on by itself. The user need not say they are through; when they do after a `gate_timeout`, its agent may hand the page back at once (`fetch --start <url> --session pf-<slug>`: a run on its own paper is never held) instead of waiting for the next pass. Record every gate (page, time, paper) for the report.

## Pages nobody can pass

The proxy's "Host Needed", a site's block page: not gates. The paper agent answers its `page` handoff with the verdict (references/publishers.md, *Pages nobody can pass*) and reports it; tell the user the first time one shows. A missing subscription concerns one paper; the next paper on the same site is tried as usual.
