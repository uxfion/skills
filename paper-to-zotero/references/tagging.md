# Tagging

Tags answer one question: *how would the user look for this paper?* They are not a summary of everything the paper is. Tag what you are **certain** of; a tag without a source, or one you cannot verify, is left off.

## Two kinds of tags on one item

| Kind | Zotero type | Who writes it | What to do with it |
| --- | --- | --- | --- |
| Source keywords | automatic (1, shown orange) | the authors' own keywords (article page, PubMed, OpenAlex) and arXiv subject categories — not MeSH terms, not publisher index terms | Keep. They are the source's own words, and Zotero can hide or bulk-delete automatic tags at any time. |
| Curated tags | manual (0) | the agent, by this file | Add. Reuse an existing tag whenever one fits; create a new one only when nothing fits, and list every new tag in the report. Manual tags that predate this scheme are folded into it (renamed to the canonical form or replaced) — the user has released them. |

## Curated tag forms

| Dimension | Form | Examples |
| --- | --- | --- |
| Method | `method/<Name>` | `method/Diffusion`, `method/Flow Matching`, `method/GAN`, `method/Transformer`, `method/Mamba` |
| Task | `task/<Name>` | `task/Super-resolution`, `task/Denoising`, `task/Enhancement`, `task/Segmentation`, `task/IQA` |
| Modality | `modality/<Name>` | `modality/Ultrasound`, `modality/MRI`, `modality/CT`, `modality/Natural image` |
| Dataset | `dataset/<Name>` | `dataset/BUSI`, `dataset/DIV2K` |
| Common name | bare | `CycleGAN`, `Restormer`, `DDPM`, `SR3` |
| Venue | bare | `CVPR`, `ICCV`, `ECCV`, `ICML`, `ICLR`, `NeurIPS`, `AAAI`, `ACL`, `MICCAI`, `TMI`, `MedIA`, `JBHI`, `TIM`, `npj Digital Medicine`, `NC`, `Nature Medicine`, `arXiv` |

Rules per dimension:

- **Prefix** is lowercase and fixed; the value is the term as the field writes it (mostly English), one canonical spelling per concept — `task/Super-resolution`, never also `task/Superresolution`. Tags are case-sensitive in Zotero, so check the existing tag list before typing a new spelling.
- **Up to 5 per dimension.** Tag what discriminates: a paper's methods and tasks, the modality it works on, the datasets it introduces or is evaluated on (as stated in the paper — never from memory). A branch that is widely searched under a broader family gets the family too (a rectified-flow paper carries `method/Flow Matching` and `method/Diffusion`; a text-to-image paper carries `task/Text-to-image` and `task/Image generation`). A dimension that would only repeat the title's noise is left empty.
- **Common name** only when the community actually uses one — usually the model name (`CycleGAN`, `Restormer`), which is often absent from the title; when a paper is known under two names, give both (`Stable Diffusion` and `LDM`). Never coin a name.
- **Venue** is the standard abbreviation without a year (the year is a field). A journal without a community abbreviation (beyond TMI, MedIA, JBHI, TIM, NC…) takes its NLM abbreviation as PubMed prints it *and* the initialism, e.g. `Comput Biol Med` and `CBM`, so both spellings find it. A preprint gets `arXiv`; an arXiv copy of a paper known to be published elsewhere gets both `arXiv` and the venue.
- **Dataset** uses the dataset's own name as its authors write it.

## Choosing tags for one paper

1. List the library's existing tags (the `zotero` skill's `tags` command) — that list is the vocabulary.
2. From the item's title, abstract, venue and, when needed, the PDF's first page, pick the tags above. Prefer an existing tag; add a new one only for a concept the vocabulary lacks.
3. Write source keywords as automatic tags and curated tags as manual tags, so the two stay distinguishable in Zotero.
4. Report: the curated tags chosen, which of them are new to the library, and the source keywords kept.

## Tidying existing items

Work through the library in batches (one collection at a time). For each batch, produce the change list first — per item: source keywords kept, curated tags to add, tags proposed for removal, pre-scheme manual tags to rename — and write only after the user has confirmed it. An item whose metadata is broken (no date, venue or DOI) is noted for a separate fix, not repaired in a tag batch. Candidates for removal are automatic tags that discriminate nothing, such as publisher-generated index terms (`Training`, `Task analysis`, `Feature extraction`); spelling variants of one concept are merged to the canonical form. Subject categories from arXiv stay. Manual tags that predate this scheme stay as they are unless the user asks to fold them in.
