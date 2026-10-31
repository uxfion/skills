# paper-to-zotero: `fulltext_links` lists no CVF Open Access copy for a CVPR paper

> 已解决（2026-10-31）：spec `docs/specs/20261031-paper-skills-script-agent-division-spec.md` §10。CVF 写进 paper-fetch 的 `references/publishers.md`（*Conference proceedings*），作为带日期的提示，由 agent 去 CVF 的列表页找，fulltext_links 里不写某一家的代码。


Logged 2026-10-30, while saving the baseline for the split (spec `20261030-paper-to-zotero-split-spec.md` §10 step 0). After the split this belongs to paper-fetch's `fulltext_links`.

**What was run.** `doi_to_item --doi 1709.01507`, then `doi_to_item --redraft 10.1109/CVPR.2018.00745` (Squeeze-and-Excitation Networks, CVPR 2018), then `prepare`.

**What was seen.** The record's `links` held one item, `https://arxiv.org/pdf/1709.01507` (`version: preprint`). No CVF Open Access link, though CVF hosts the CVPR 2018 paper. Pass 1's open route had nothing to try; the publisher and discovery routes went to the institution's login; the file came from the preprint route (arXiv v4, the TPAMI-accepted text, not the CVPR one).

**Why it hurts.** `references/publishers.md` says CVPR and ICCV papers usually have a free copy on CVF Open Access, and the attachment-title scheme treats a CVF copy of CVPR 2018 as `Published-CVF`. Missing it costs a trip through the institution's login and leaves the item with a different version of the paper than the one it describes.

**Direction.** CVF Open Access URLs follow the venue and year (`openaccess.thecvf.com/content_cvpr_2018/html/<First_Author>_<Title_Words>_CVPR_2018_paper.html`), so for a CVF venue `fulltext_links` can look the paper up on the venue's listing page (one request per venue and year) instead of relying on OpenAlex or Unpaywall to know the copy.
