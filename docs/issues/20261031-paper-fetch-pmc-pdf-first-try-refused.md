# paper-fetch: PMC's PDF refused on the bulk run's first try, fetched a minute later

2026-10-31, phase-1 live acceptance (spec `20261031-paper-skills-script-agent-division-spec.md` §8), UNet++ (`10.1109/TMI.2019.2959609`, PMC7357299, an NIH author manuscript).

- **What was run.** `pf.py fetch --pass 1 --route accepted` on the result. The candidate was the PMC article page `https://pmc.ncbi.nlm.nih.gov/articles/PMC7357299/` (`needs_browser: true`).
- **What was seen.** fetch tried the page's one PDF link and the check refused what came back (`code: refused`, note "1 PDF links tried"); a `page` handoff followed. About a minute later the paper agent ran `fetch --start <the same article page> --version accepted --session pf-zhou2020unet`, and that run fetched `…/pdf/nihms-1600374.pdf`, which passed the check.
- **Why it matters.** A PMC copy may need a second, later request before its PDF link serves the PDF (publishers.md already notes a JavaScript verification for plain HTTP and a reCAPTCHA on the PDF link). The handoff path recovered it, at the cost of a paper agent; a paper with several PMC candidates pauses on the first.
- **Not yet known.** Whether the first response was PMC's verification page, a viewer, or something else: the refused file sat in `unverified/` and went with the live-test directory.
- **Suggested.** On the next real run, keep the refused response and look at it; then a dated hint in publishers.md's PMC bullet, worded from what it was.
