# Tagging

Tags answer one question: *how would the user look for this paper?* They are not a summary of everything the paper is. Tag what you are **certain** of; a tag without a source, or one you cannot verify, is left off.

This scheme is a starting point, not a closed list. The dimensions, the examples and the library's existing tags are what has been useful so far; a new paper may need a tag, a venue abbreviation or even a dimension that is not here yet — add it, and say so in the report so the user can keep or correct it. What the user changes in conversation is the rule from then on.

## Two kinds of tags on one item

| Kind | Zotero type | Who writes it | What to do with it |
| --- | --- | --- | --- |
| Source keywords | automatic (1, shown orange) | the authors' own keywords (article page, PubMed, OpenAlex) and arXiv subject categories — not MeSH terms, not publisher index terms | Keep. They are the source's own words, and Zotero can hide or bulk-delete automatic tags at any time. |
| Curated tags | manual (0) | the agent, by this file | Add. The existing tags are the spelling reference, not a cap: a concept that already has a tag reuses that spelling, a concept without one gets a new tag — normal for a new paper. List every new tag in the report. Manual tags from before this scheme stay as they are; fold them in (rename to the canonical form or replace) only when the user says so in the session. |

## Curated tag forms

| Dimension | Form | Examples |
| --- | --- | --- |
| Method | `method/<Name>` | `method/Diffusion`, `method/Flow Matching`, `method/GAN`, `method/Transformer`, `method/Mamba` |
| Task | `task/<Name>` | `task/Super-resolution`, `task/Denoising`, `task/Enhancement`, `task/Segmentation`, `task/IQA` |
| Modality | `modality/<Name>` | `modality/Ultrasound`, `modality/MRI`, `modality/CT`, `modality/Natural image` |
| Dataset | `dataset/<Name>` | `dataset/BUSI`, `dataset/DIV2K` |
| Common name | bare | `CycleGAN`, `Restormer`, `DDPM`, `SR3` |
| Venue | `venue/<Abbr>` | `venue/CVPR`, `venue/ICCV`, `venue/NeurIPS`, `venue/MICCAI`, `venue/TMI`, `venue/MedIA`, `venue/JBHI`, `venue/npj Digital Medicine`, `venue/arXiv` |
| Article type | `type/<Kind>` | `type/Survey` |

Rules per dimension:

- **Prefix** is lowercase and fixed; the value is the term as the field writes it (mostly English), one canonical spelling per concept — `task/Super-resolution`, never also `task/Superresolution`. Tags are case-sensitive in Zotero, so check the existing tag list before typing a new spelling.
- **Up to 5 per dimension.** Tag what discriminates: a paper's methods and tasks, the modality it works on, the datasets it introduces or is evaluated on (as stated in the paper — never from memory). A branch that is widely searched under a broader family gets the family too (a rectified-flow paper carries `method/Flow Matching` and `method/Diffusion`; a text-to-image paper carries `task/Text-to-image` and `task/Image generation`). A dimension that would only repeat the title's noise is left empty.
- **Common name**: the name the paper gives its model, system or framework — usually in the abstract ("we propose EchoWDiff", "Here we present AMIFound"), often absent from the title (`CycleGAN`, `Restormer`). Read the abstract for it on every paper; a brand-new paper's name is how people will cite it. When a paper is known under two names, give both (`Stable Diffusion` and `LDM`). A name the paper never uses is not a tag. A benchmark or corpus takes `dataset/` (`dataset/GSM8K`, `dataset/MIMIC-CDM`); a method or idea, however catchy its name (`Scalable oversight`, `Temperature scaling`, `Semantic entropy`), takes `method/` or `task/` when that is how the user would look for the paper, and stays untagged otherwise. (One 2026-10 batch made 115 bare tags; the user then had to sort the datasets and concepts out by hand.)
- **Venue** (journal, conference, workshop, preprint server) is `venue/` plus the standard abbreviation without a year (the year is a field); the prefix lets the tag selector list every venue at once, and typing the bare abbreviation still finds it. A journal without a community abbreviation (beyond TMI, MedIA, JBHI, TIM, NC…) takes its NLM abbreviation as PubMed prints it *and* the initialism, e.g. `venue/Comput Biol Med` and `venue/CBM`, so both spellings find it. A preprint gets `venue/arXiv`; an arXiv copy of a paper known to be published elsewhere gets both `venue/arXiv` and the venue.
- **Article type** only when it is how the user would look for the paper: a survey or review gets `type/Survey`; a regular research paper gets none.
- **Dataset** uses the dataset's own name as its authors write it.
- **Not a dimension:** reading state, project priority or review progress (`to-read`, `P1`, `checked`) — those live in collections or notes, so the tag list keeps answering only what a paper *is*.

## Choosing tags for one paper

1. List the library's existing tags (`uv run scripts/read_library.py tags`) — the spelling reference: one spelling per concept.
2. From the item's title, abstract, venue and, when needed, the PDF's first page, pick the tags above — the existing spelling where the concept already has a tag, a new tag where it does not.
3. Write source keywords as automatic tags and curated tags as manual tags, so the two stay distinguishable in Zotero.
4. Report: the curated tags chosen, which of them are new to the library, and the source keywords kept. After a batch, list every new tag once, grouped by prefix, so the user can look them over in one go.

## Tidying existing items

The batch mechanics are organize.md's (*Tidying tags and collections*). What changes: automatic tags that discriminate nothing, such as publisher-generated index terms (`Training`, `Task analysis`, `Feature extraction`), are candidates for removal; spelling variants of one concept are merged to the canonical form; pre-scheme manual tags are renamed only when the user has released them. Subject categories from arXiv stay.
