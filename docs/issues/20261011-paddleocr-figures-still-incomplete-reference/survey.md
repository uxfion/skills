# Figure grouping survey: sources first (2026-10-12)

Scope: ideas for a top-down, caption-anchored "float region" figure grouper on top of PaddleOCR-VL-1.6 output. Sources only; nothing installed or run.

## 1. Upstream status (PaddleOCR / PaddleX / MinerU)

- **PaddleOCR**: no release after v3.7.0 (2026-06-11), which is still "Latest". https://github.com/PaddlePaddle/PaddleOCR/releases
  - Commits on main since v3.7.0 are docs/CI plus one feature, "[Feat] Support HPD-Parsing" (#18262, merged 2026-07-22). https://github.com/PaddlePaddle/PaddleOCR/pull/18262 , https://github.com/PaddlePaddle/PaddleOCR/commits/main
  - HPD-Parsing: a 1B VLM (InternVL3.5-1B backbone, Apache-2.0) built for throughput. Its blocks carry categories such as `image` and `image_caption`, and the docs say nothing about grouping panels, a whole-figure class, or linking captions to images. https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/HPD-Parsing.html , https://huggingface.co/PaddlePaddle/HPD-Parsing , README news 2026-07-22: https://github.com/PaddlePaddle/PaddleOCR/blob/main/README.md
- **PaddleX**: no release after v3.7.2 (2026-06-25). Since then the default branch has one commit, "Support PP-OCRv6 for HPI and HPS (#5165)". https://github.com/PaddlePaddle/PaddleX/releases , https://github.com/PaddlePaddle/PaddleX/commit/ffb6490
- **Models**: there is no PaddleOCR-VL newer than 1.6 and no PP-DocLayout newer than V3 on the PaddlePaddle HF org. The 2026-09-30 change to PP-DocLayoutV3 only edited the README, and the 2026-08 changes to PaddleOCR-VL-1.6 are eval metadata. https://huggingface.co/PaddlePaddle , https://huggingface.co/PaddlePaddle/PP-DocLayoutV3/commits/main , https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6/commits/main
- **Whole-figure class or figure merge option**: none found.
  - The PaddleOCR-VL pipeline options are `merge_layout_blocks` ("merge the layout detection boxes for cross-column or staggered top and bottom columns"), `layout_merge_bboxes_mode` (large/small/union, for overlapping or contained boxes), `use_ocr_for_image_block`, and `merge_tables`/`relevel_titles`/`concatenate_pages` in `restructure_pages()`. None of them merges sub-figures or ties captions to images. https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html
- **PP-DocBlockLayout** (the region detector PP-StructureV3 uses; RT-DETR-L, Apache-2.0) has one class, `Region` ("Block" in the PP-StructureV3 doc). It was trained on an in-house set of papers, PPT, magazines and contracts. The docs don't say what a Region covers. https://huggingface.co/PaddlePaddle/PP-DocBlockLayout , https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PP-StructureV3.html
  - In PaddleX v3.7.2 `pipeline_v2.py`, layout blocks go to the region that contains them (`mode="small"`); the region box grows to the minimal enclosing box of its blocks; unmatched blocks get "SupplementaryRegion"s. The regions then only drive reading order (`xycut_enhanced` over `LayoutRegion`s). They are not exposed as figure groups. https://github.com/PaddlePaddle/PaddleX/blob/v3.7.2/paddlex/inference/pipelines/layout_parsing/pipeline_v2.py
  - Whether a Region box tends to wrap a whole multi-panel figure is undocumented; checking it would take an experiment.
- **Issue #18081** ("PaddleOCR-VL-1.5/1.6: images in the same row each come out on their own line"): OPEN. Opened 2026-05-29, assigned to liu-jiaxuan, no labels.
  - The only reply (SISTMrL, 2026-07-19) calls it a restructure-stage problem: several images side by side in one row get no in-row aggregation.
  - Suggested workaround: merge image blocks yourself by y-overlap of their bboxes in the JSON.
  - No fix linked. https://github.com/PaddlePaddle/PaddleOCR/issues/18081
- **Issue #18215** ("PP-DocLayoutV3 layout problems"): OPEN. Opened 2026-06-25 by hzkitty, assigned to Sunting78, no labels.
  - P1–P8 report reading-order errors, missed detections, a header misclassified, and a formula detected as a table. In each case PP-DocLayoutV2 was fine.
  - Last comment 2026-07-15. No maintainer reply in the thread. https://github.com/PaddlePaddle/PaddleOCR/issues/18215
- **MinerU after 4.0.10**: 4.0.11 (2026-10-08) and 4.0.12 (2026-10-11, Latest) change the API, router, OpenCV removal, CLI, CJK punctuation and Office hyperlinks.
  - On layout, 4.0.12 only says "restore PP-DocLayoutV2 model class thresholds and align Torch/ONNX output filtering with reading-order candidate validity".
  - Nothing on figure grouping. https://github.com/opendatalab/MinerU/releases/tag/mineru-4.0.11-released , https://github.com/opendatalab/MinerU/releases/tag/mineru-4.0.12-released
  - MinerU's VLM already had a multi-image container block, `image_block`, since about Feb 2026, so before 4.0.10 (see §4). It is not new upstream.

## 2. pdffigures2 / PDFFigures (2015) / DeepFigures

### PDFFigures 1 (Clark & Divvala, AAAI-15 Scholarly Big Data workshop)
- I did not retrieve the full text. The bibliographic entry is in the WS-15-13 proceedings: https://dblp1.uni-trier.de/db/conf/aaai/sbd2015.html. The summary below is from §3 of the 2016 paper: https://ai2-website.s3.amazonaws.com/publications/pdf2.0.pdf
- **Caption detection**: keyword search for "Figure N"-style phrases (Poppler text).
  - Consistency assumption: each figure is labelled once, so duplicates mean false positives. Formatting filters are applied iteratively (ends with period, ends with semicolon, bold, italic, different font size from the following words), each only if it doesn't remove every phrase for that figure.
  - Last resort: keep only phrases that start a paragraph.
- **Region identification**: the page is split into caption, graphical element, body text and figure text.
  - Paragraphs that are "too large or aligned to the left margin of a column" count as body text; everything else is figure text.
  - Headers and page numbers are found by repetition across pages.
  - Graphics are connected components of a text-free render.
- **Figure assignment**: up to 4 proposals per caption, one adjacent to each side.
  - Each is "maximally expanded" until it would overflow the page margin, overlap body text, or overlap a caption. In 2-column papers it may not cross the page centre unless the caption spans both columns.
  - The score favours large regions that contain graphics.
  - Every permutation of caption→proposal is scored, and overlapping regions score 0.
  - Adjacent figures that share one proposal are split at a central whitespace band.

### PDFFigures 2.0 (Clark & Divvala, JCDL 2016) — https://ai2-website.s3.amazonaws.com/publications/pdf2.0.pdf (DOI 10.1145/2910896.2910904); code: https://github.com/allenai/pdffigures2
- **(a) Body text vs figure text**: PDFFigures 2.0 never looks at a semantic label.
  - Premise: "the majority of text in a document is body text… body text will have a consistent format throughout the document. … text that is formatted in an anomalous way can be assumed to be figure text."
  - Document-wide modes: font, font size, line width, line spacing, word spacing, left margins.
  - Heuristics, in order:
    1. Text that overlaps a graphic region is figure text.
    2. Vertical text is figure text.
    3. Above-median word spacing is figure text (catches tables).
    4. Blocks several lines long at the modal line width are body text.
    5. Text smaller than the modal font size is figure text.
    6. Section titles (margin-aligned or centred, numbered or capitalised, non-standard font) are body text.
    7. Text aligned to a left margin is body text; whatever remains is figure text.
  - Page headers: the first lines on a page that sit well above the rest and at the same height on every page.
  - Captions grow line by line while the gap is under the median line space, the justification is similar, the line doesn't overlap a graphic, and the font is the same.
  - Caption-start filters added in 2.0: all-caps, abbreviated, single-line, font not the document's most common one, left-aligned with the text below.
- **(b) Region proposals** (`FigureDetector.scala`, https://github.com/allenai/pdffigures2/blob/master/src/main/scala/org/allenai/pdffigures2/FigureDetector.scala):
  - For each caption, find how far its box can expand in each direction before hitting "nonFigureContent" (body text and other captions). Build Left/Right/Up/Down proposals (each above a min width/height), expanded across the other axis (`boxExpandLR`/`boxExpandUD`).
  - Two columns: the column centre comes from body-text edges (`findCenterColumn`). Proposals are cropped to the caption's column unless they contain an element that crosses the centre (`cropToCenter`).
  - **Clustering prune (Up proposals only; the code has a TODO for Down)**, `clipUpwardRegion`:
    - If the proposal contains a significant graphic, seed a cluster with it.
    - Iteratively absorb graphics and text that lie within a small vertical distance of the cluster's top: ≤10 pt for text blocks under 3000 pt², ≤4 pt for larger text blocks, ≤20 pt for graphics.
    - Drop everything else. This guards against bullets or body text misclassified as figure text (paper Fig. 3).
  - Each proposal is cropped to the content inside it (`Box.crop`).
  - **Rejected** when the proposal partially intersects any word, when its edge cuts any figure element at 10–90 % of that element's area (`boxCutsFigure`, `cutFilterIntervalMin 0.1 / Max 0.9`), or when it lies within 30 pt of the top or left page edge.
  - Score (`scoreProposal`) = area / content-bounds area, +0.10 if it contains a graphic, +0.15 if it contains a graphic over 2000 pt².
    - Left/Right proposals ×0.75.
    - Split proposals get +2·whitespace-area/bounds, then ×0.75 (split from a different type) or ×0.5 (same type).
    - `None`, i.e. invalid, when it intersects another chosen proposal.
- **(c) Conflicts between captions**: all caption→proposal combinations are enumerated (cartesian product).
  - Total = sum of scores − number of invalid ones. Above 500k configurations the page is abandoned.
  - Two overlapping Up/Down proposals from different captions can be split at the **largest** whitespace band (in v1, the central one).
  - The split triggers more often in 2.0 and is down-weighted (see the scores above) to limit false splits of figures that contain whitespace.
- **Evaluation and errors**: a box counts as correct at IoU > 0.8 and the caption must also be correct. The abstract reports 94 % precision at 90 % recall on its new dataset of CS papers. The paper evaluates on CS-150 and on the new CS-Large (346 annotated papers).
  - "Errors tend to emerge in papers where figures are arranged in complex layouts, or are caused by difficulty correctly classifying blocks of text that do not match the usual flow of body text, such as equations, page headers, or text inside figures."
  - Table 4: text extraction errors are the main source, then text classification.
  - Qualitative failures: a page header taken into a figure, a 3-way figure layout not separated, table text taken for body text. (Same PDF.)

### DeepFigures (Siegel, Lourie, Power, Ammar, JCDL 2018) — https://arxiv.org/abs/1804.02445 ; code: https://github.com/allenai/deepfigures-open
- **LaTeX labels**: `\floatsetup` with a red (figure) or yellow (table) `\fcolorbox` frames every float. The PDF is recompiled and the page images are diffed against the original. Connected components of the diff give the float boxes (white borders are added to the original so they align).
  - Captions are recoloured (`\usepackage[labelfont={color=green},textfont={color=blue}]{caption}`).
  - The figure box = float box minus the caption, i.e. "the largest rectangular region inside the float that contains no caption text". The box therefore includes **all text inside the float**: axis labels, legends, sub-captions (a)(b) and every panel. The caption is a separate box.
- **PubMed labels**: captions are found with a modified Wagner–Fischer edit distance (free start and end) between the PMC XML caption and the PDFBox text.
  - The figure's PMC image file is located on the rendered page by multi-scale template matching (OpenCV `TM_CCOEFF_NORMED`, 45 scales, 10–95 % of the page).
  - Papers with similarity under 0.8 are dropped, e.g. when subfigures are laid out differently in the image file. The publisher image is the whole figure, with its internal text.
- **Scale and model**: 5.5 M induced labels, averaging 96.8 % precision on the LaTeX and XML sets. Model: OverFeat-style box regression on ResNet-101, 640×480 input, 20×15 grid.
- **Caption pairing**: captions are not detected by the network. They come from the pdffigures2 regex/text method, and figures are matched to captions by Hungarian assignment on centre distance (`min(#fig, #cap)` pairs).
  - "Training the model to predict captions reduced performance": captions are thin and visually indistinct.

### Reusable ideas, mapped to the four failure modes
- **Text-heavy panels, infographic sub-headings, flow-chart text rows left out**: decide membership by *not-body-text*, not by a figure label.
  - Learn the body-text profile per document (modal font size, line height, line width = column width, left-margin x positions, justification).
  - The region grows from the caption until it meets body-text-profile blocks, other captions, page margins or the column gutter. Anything inside is a member, whatever the layout model calls it.
- **Heatmap grids labelled `table` lost**: the caption type ("Figure N" vs "Table N") decides the float type. The content's class is irrelevant once the block sits inside the caption's float region.
- **Pure-text figures (prompt/output examples) get no crop**: in pdffigures2 the graphic is a bonus (+0.10/+0.15), not a gate. A region of non-body text bounded by body flow is still a valid figure.
  - Body-text detection must then tolerate monospace or boxed text (anomalous font → figure text).
- **Partial crops undetected**: two cheap completeness checks from pdffigures2.
  - Reject or extend a crop whose edge cuts any non-body element at 10–90 % of its area (`boxCutsFigure`).
  - Reject one that partially intersects a word.
  - Plus: the crop should reach the nearest body-text, caption or margin bound in the growth direction. Leftover non-body blocks between the crop and that bound mean it is incomplete.
- **Several figures on one page or in one column**: optimise jointly over all captions on the page (overlap means invalid), with a split at the largest whitespace band and a penalty on splits. Prefer Up/Down over Left/Right (×0.75).
- **Stray text pulled in**: cluster outward from the dominant graphic with small vertical gaps (`clipUpwardRegion`) to drop misclassified body text near a figure.
- **Pairing**: Hungarian assignment on centre distance (DeepFigures) is a simple global alternative to "nearest caption below".
- **The same top-down rule has produced ground truth at scale.** PubLayNet's figure labels use it: the potential box runs between the caption and the body text above, and the figure is the smallest box enclosing every text box, image and shape inside it. DocLayNet's guide defines the target semantics: "One Picture per Caption", internal text included (see §3).
- **DeepFigures label recipe**: arXiv LaTeX float boxes minus the caption are a natural source of *whole-figure* ground truth, for evaluating the redesign on the user's own arXiv papers without hand labels.

## 3. Later research (2019–2026), datasets, detectors

### Datasets whose "figure" box is the whole figure

- **PubLayNet** (Zhong et al. 2019, https://arxiv.org/pdf/1908.07836). 5 classes (text, title, list, table, figure); captions are labelled `text`.
  - Figure boxes come from geometry, not XML coordinates. First every text XML node is matched to PDF text. Then the body-text bbox is computed. The "potential box" is the largest box that fits between the top of the caption and the annotated text above it. The figure is the smallest box enclosing all text boxes, images and geometric shapes inside that potential box. Table bodies are assumed to sit below their caption (§III-B).
  - "When sub-figures exist, the whole figure panel is annotated as a single object. Sub-figures are not annotated individually" (Table I note d).
  - Figure-internal text is inside the box by construction.
  - In effect this is a pdffigures-style "caption anchors the region; body text bounds it" labeller.
  - Annotations are CDLA-Permissive-1.0 and images follow the PMC OA terms (https://github.com/ibm-aur-nlp/PubLayNet/blob/master/LICENSE.md). The repo's pre-trained models are Apache-2.0 (LICENSE.pretrained.model.md).
- **DocLayNet** labelling guide (https://raw.githubusercontent.com/DS4SD/DocLayNet/main/assets/DocLayNet_Labeling_Guide_Public.pdf; paper https://arxiv.org/abs/2206.01062). It has 11 classes, and Caption is separate.
  - §3.2: a Picture "may also contain text". Draw "the smallest boundary that comprises all elements (graphical and textual) that belong to the graphics", and "rather include a few pixels too many than too few".
  - §3.2.2: legends, axis texts and units belong to the Picture.
  - §3.2.3 "One Picture per Caption, if Captions Exist": one caption means one picture, "even if it has several sub-pictures".
  - §3.2.4: if each sub-picture has its own caption, each is a separate picture. With no captions it is a judgement call (touching / reasonable union rectangle).
  - §8.2.1: text between pictures leads to several pictures. Close pictures without separate text become one.
  - §8.2.6: a table inside a picture can be labelled Picture, e.g. when it has a single caption and interesting surrounding text.
  - So DocLayNet "Picture" is caption-anchored and whole-figure, with internal text included. This is exactly the target semantics.
- **DocStructBench** (DocLayout-YOLO paper, https://arxiv.org/html/2410.12628). 10 classes: Title, Plain Text, Abandon(ed) Text, Figure, Figure Caption, Table, Table Caption, Table Footnote, Isolated Formula, Formula Caption.
  - "Figure" is defined only as an isolated floating figure. Panel versus whole figure: not stated.
- **D4LA** (https://arxiv.org/html/2308.14978): 27 classes incl. Figure, with captions separate as FigureName / TableName. Mostly business documents (12 doc types, scientific publication/report among them). Panel rule: not found.
- **M6Doc** (https://github.com/HCIILAB/M6Doc): 74 labels; class list only in images and the Chinese guideline. Figure extent: not found. CC BY-NC-ND 4.0, full set gated behind an institutional agreement.
- **OmniDocBench** (https://github.com/opendatalab/OmniDocBench): `figure`, `figure_caption`, `figure_footnote`, plus explicit `relation: parent_son` links between figure/table and caption/footnote (`source_anno_id` → `target_anno_id`). Panel versus whole extent: not stated in the README.
- **DocBank** (https://github.com/doc-analysis/DocBank): token-level weak labels ("fully annotated at token-level"). It is not a region-box figure dataset, so it is of little use for whole-figure boxes. Apache-2.0 per README, but also "Please DO NOT re-distribute our data".
- **DocGenome** (https://github.com/UniModal4Reasoning/DocGenome, CC-BY-4.0): 500K arXiv papers auto-labelled from LaTeX with the DocParser pipeline. "Figure" is a floating unit; Caption is separate.
  - Relations: "implicitly-referred" (caption → its float), "explicitly-referred" (\ref), "identical". The caption–float link comes from LaTeX, so a figure equals its LaTeX float.
- **DocParser / arXivdocs** (https://arxiv.org/pdf/1911.01702): hierarchical labels, with FIGURE as parent of FIGURE GRAPHIC and FIGURE CAPTION (23 categories; relations `parent_of`, `followed_by`). Weak supervision from LaTeX.
  - This is the only dataset found that models "figure = graphic(s) + caption" as an explicit hierarchy. Code/weights availability: not confirmed.
- **DeepFigures induced labels** (see Q2): the LaTeX float box minus caption, so whole figure incl. internal text and sub-figures. PMC labels come from template-matching the XML figure image, i.e. the whole published figure image.

### Figure/caption extraction and compound-figure work (2019–2026)

- **SciCap** (https://arxiv.org/pdf/2110.11624): arXiv cs papers 2010–2020, >2M figures. Figures were extracted with **PDFFigures 2.0**.
  - Figures with subfigures were *removed*, using caption cues "(a)", "a)" and FigureSeparator (Tsutsui & Crandall 2017). 35.72% of figures had subfigures in their pilot study.
  - The repo has no license file (https://github.com/tingyaohsu/SciCap).
- **ACL-Fig** (https://arxiv.org/abs/2301.12293): 112,052 figures from ≈56K ACL Anthology papers, plus 1,671 manually typed into 19 categories.
  - It is figure-type classification, not localisation. The extractor used: not found.
  - CC BY-NC, gated: https://huggingface.co/datasets/citeseerx/ACL-fig
- **PDFigCapX** (Li, Jiang, Shatkay, Bioinformatics 2019, https://pmc.ncbi.nlm.nih.gov/articles/PMC6821181; tool https://www.eecis.udel.edu/~compbio/PDFigCapX): rule-based. It separates text from graphics first, then uses layout to find figure and caption pairs.
  - It is paired with **FigSplit** for compound-figure → subfigure splitting.
  - Web tool; open weights/code not found.
- **ScanBank** (Kahu et al., JCDL 2021, https://arxiv.org/abs/2106.15320): 10K scanned ETD pages with ~3.3K manually boxed figures and tables. YOLOv5 detector, which beats DeepFigures on scans. Figure versus panel rule: not found.
- **MedICaT** (Subramanian et al., EMNLP Findings 2020, https://arxiv.org/abs/2010.06000; https://github.com/allenai/medicat): 217K figures from PMC OA, ~75% compound.
  - Task: subfigure detection (Faster R-CNN R-50) plus subfigure↔subcaption alignment (BERT+CRF).
  - It works inside an already-cropped whole figure, so it goes the opposite direction from our grouping problem.
- **Compound figure separation**: ImageCLEF 2016 CFS benchmark; SimCFS / "side loss" (Yao, Huo et al., https://arxiv.org/abs/2208.14357, https://arxiv.org/abs/2107.08650; code https://github.com/hrlblab/ImageSeperation). These split a whole-figure image into panels and are not page-level.
- **Relation-graph layout**:
  - GraphDoc / DRGG (ICLR 2025, https://arxiv.org/abs/2502.02501): 80K pages, 4.13M relation annotations (parent/child/sequence/reference) between layout boxes. Generic; caption–figure is not singled out in the sources read.
  - SciPostLayoutTree (https://arxiv.org/abs/2511.18329) applies the same idea to posters.
  - These offer a learned "which boxes belong together" signal, but no off-the-shelf scientific-figure checkpoint was confirmed.
- No dedicated 2023–2026 paper was found on page-level "caption-anchored whole-figure region" extraction that supersedes pdffigures2/DeepFigures. Recent work moved into general layout detectors (DocLayNet-style Picture) and end-to-end doc VLMs.

### Off-the-shelf detectors with a whole-figure class

Licences and sizes are from the HF API (`/api/models/{id}`).

| id | arch / deps | trained on → figure semantics | license | size |
|---|---|---|---|---|
| `Aryn/deformable-detr-DocLayNet` (https://huggingface.co/Aryn/deformable-detr-DocLayNet) | Deformable DETR, HF transformers | DocLayNet → Picture = whole caption-anchored figure | Apache-2.0 | 41.1M params, 165 MB |
| `cmarkea/detr-layout-detection` (https://huggingface.co/cmarkea/detr-layout-detection) | DETR-R50, transformers | DocLayNet (11 classes incl. Picture, Caption); 91.27 F1 on 500 DocLayNet pages | Apache-2.0 | 42.9M, 172 MB |
| `docling-project/docling-layout-heron` (https://huggingface.co/docling-project/docling-layout-heron) | RT-DETR, transformers | DocLayNet-style Picture (already evaluated via docling, listed for completeness) | Apache-2.0 | 42.9M, 172 MB |
| `hantian/yolo-doclaynet` (https://huggingface.co/hantian/yolo-doclaynet) | ultralytics YOLOv10 / YOLO26 n–l | DocLayNet Picture | **AGPL-3.0** | 5.5–53 MB |
| `Armaggheddon/yolo11-document-layout` (https://huggingface.co/Armaggheddon/yolo11-document-layout) | ultralytics YOLO11 n/s/m | DocLayNet (11 classes incl. Picture, Caption) | card says MIT, but it needs the ultralytics runtime (AGPL-3.0) | 5.6–41 MB |
| `juliozhao/DocLayout-YOLO-DocStructBench` (https://huggingface.co/juliozhao/DocLayout-YOLO-DocStructBench; code https://github.com/opendatalab/DocLayout-YOLO) | YOLOv10 fork of ultralytics (`doclayout_yolo` pkg), 1024 px, 85.5 FPS on A100 | DocStructBench Figure / Figure Caption (panel rule not stated) | weights Apache-2.0, **code AGPL-3.0** | 40.7 MB |
| `juliozhao/DocLayout-YOLO-DocLayNet-Docsynth300K_pretrained` (linked from the DocLayout-YOLO README) | same | DocLayNet Picture; 93.4 mAP50 / 79.7 mAP | as above | ~40 MB |
| LayoutParser PubLayNet `lp://PubLayNet/mask_rcnn_X_101_32x8d_FPN_3x` (https://layout-parser.readthedocs.io/en/latest/notes/modelzoo.html) | Detectron2 (heavy, old build) | PubLayNet Figure = whole figure incl. subfigures; label map {0 Text, 1 Title, 2 List, 3 Table, 4 Figure} | Apache-2.0 (toolkit) | not found |
| `nlpconnect/PubLayNet-faster_rcnn_R_50_FPN_3x` (https://huggingface.co/nlpconnect/PubLayNet-faster_rcnn_R_50_FPN_3x) | Detectron2 | PubLayNet Figure | Apache-2.0 | 330 MB |
| `allenai/deepfigures-open` weights (https://github.com/allenai/deepfigures-open; weights at https://s3-us-west-2.amazonaws.com/ai2-s2-research-public/deepfigures/weights.tar.gz) | TensorBox / ResNet-101, old TensorFlow, Docker | LaTeX float minus caption; whole figure, with caption matching by Hungarian on centre distance | Apache-2.0 | not found; "research code, not for production" |
| `PaddlePaddle/PP-DocLayout_plus-L` (https://huggingface.co/PaddlePaddle/PP-DocLayout_plus-L) | RT-DETR-L, PaddleX (already in the pipeline) | its image/chart classes (the user found it covers ≥2 panels sometimes) | Apache-2.0 | not checked |

- The cleanest semantic match is the **DocLayNet Picture** class: one caption means one box incl. legends and internal text. Two DocLayNet-trained checkpoints load with plain HF transformers and Apache-2.0: Aryn deformable-DETR and cmarkea DETR.
- PubLayNet Figure has the same whole-figure semantics but is PMC-only (biomed) and caption-bounded by construction.
- Not found: any checkpoint trained specifically on a "figure incl. caption" (figure+caption union) class, or a HF RT-DETR checkpoint trained on PubLayNet/DocLayNet other than docling-heron.

## 4. VLM grounding for document regions

### Qwen3-VL: coordinate convention, prompts, sizes, serving
- **Box convention: relative 0–1000.** Tech report §3.2.4: "Different from Qwen2.5-VL, we adopt a normalized coordinate system scaled to the range [0, 1000]" (https://arxiv.org/pdf/2511.21631). The cookbook agrees: "default coordinate system has been changed from the absolute coordinates used in Qwen2.5-VL to relative coordinates ranging from 0 to 1000. (You don't need to calculate the resized_w)" (https://github.com/QwenLM/Qwen3-VL/blob/main/cookbooks/2d_grounding.ipynb).
- **Grounding prompts from the cookbook** (same URL):
  - Plain JSON: `locate every instance that belongs to the following categories: "...". Report bbox coordinates in JSON format.` Output items are `{"bbox_2d": [x1,y1,x2,y2], "label": ...}`.
  - Extra fields can be asked for by giving a template, e.g. `... in JSON format like this: {"bbox_2d": [x1, y1, x2, y2], "label": "vehicle", "type": ..., "color": ...}`.
  - Single-target referring: `Locate the top right brown cake, output its bbox coordinates using JSON format.`
  - Points: `point_2d`, or the XML form `<points x y>`.
  - JSON is the default format. The system prompt can be changed to get other formats.
- **Document parsing with boxes.** Prompt `qwenvl html` gives `data-bbox` on every element, in relative 0–1000 (the cookbook's draw helper says "坐标为相对 0-1000"). Prompt `qwenvl markdown` replaces images with coordinate placeholders (https://github.com/QwenLM/Qwen3-VL/blob/main/cookbooks/document_parsing.ipynb).
- **Where the parsing data came from.** An "in-house layout model first predicts the reading order and bounding boxes" and Qwen2.5-VL-72B recognises each region (https://arxiv.org/pdf/2511.21631 §3.2). Doc-parsing boxes therefore inherit that layout model's notion of a block. No whole-figure definition is given.
- **Sizes.** 2B, 4B, 8B and 32B dense, plus 30B-A3B and 235B-A22B MoE. Each comes as Instruct and Thinking (https://github.com/QwenLM/Qwen3-VL).
  - Official `-FP8` and `-GGUF` repos exist for every size, e.g. `Qwen/Qwen3-VL-8B-Instruct-FP8`. All are Apache-2.0 (HF API listing https://huggingface.co/api/models?author=Qwen&search=Qwen3-VL).
  - There are no official AWQ builds. Community ones include `cyankiwi/Qwen3-VL-8B-Instruct-AWQ-4bit`, `cyankiwi/Qwen3-VL-8B-Instruct-AWQ-8bit` and `cyankiwi/Qwen3-VL-32B-Instruct-AWQ-8bit` (https://huggingface.co/api/models?search=Qwen3-VL-8B-Instruct-AWQ).
- **vLLM.** Needs `vllm>=0.11.0` and `transformers>=4.57.0` (https://github.com/QwenLM/Qwen3-VL). The recipe also asks for `>=0.11.0` and suggests `--limit-mm-per-prompt.video 0` for image-only use; its hardware notes cover 235B only (https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3-VL.html).
- **VRAM.** There is no official table. Checkpoint sizes, which are a floor before KV cache and activations (HF file sizes via https://huggingface.co/api/models/Qwen/Qwen3-VL-8B-Instruct?blobs=true etc.):

  | Checkpoint | Weights on disk |
  |---|---|
  | 4B BF16 | 8.9 GB |
  | 8B BF16 | 17.5 GB |
  | 8B FP8 | 10.6 GB |
  | 30B-A3B FP8 | 32.3 GB |
  | 32B FP8 | 35.5 GB |

- **Successor: Qwen3.5 (Feb 2026), natively multimodal** ("Causal Language Model with Vision Encoder"). Sizes are 0.8B, 2B, 4B, 9B, 27B, 35B-A3B, 122B-A10B and 397B-A17B, with official FP8 and GPTQ-Int4 builds. Licence Apache-2.0 (https://huggingface.co/Qwen/Qwen3.5-9B; listing https://huggingface.co/api/models?author=Qwen&search=Qwen3.5).
  - The model card does not state the box convention. ms-swift says "Qwen3.5's bbox output uses normalized relative coordinates with a scale of 1000" and installs `vllm>=0.17.0` (https://swift.readthedocs.io/en/v4.1/BestPractices/Qwen3_5-Best-Practice.html).
  - At release the card asked for vLLM main/nightly.
- **Qwen2.5-VL used absolute pixel coordinates of the (resized) input image.** The report says it "uses coordinate values based on the actual dimensions of the input images" (https://arxiv.org/html/2502.13923, §2.1.2/§3.1). QwenVL HTML is `<p data-bbox="x1 y1 x2 y2">` (same source).

### Grounding accuracy evidence (edge precision)
- **Qwen3-VL RefCOCO-avg** (https://arxiv.org/pdf/2511.21631, Tables 2–4):

  | Model | RefCOCO-avg |
  |---|---|
  | 235B-A22B Instruct | 91.9 |
  | 32B Instruct | 91.9 |
  | 30B-A3B Instruct | 89.7 |
  | 8B Instruct | 89.1 |
  | 4B Instruct | 89.0 |
  | 2B Instruct | 85.6 |

- **ODinW-13 mAP** is 48.6 for 235B Instruct and 44.7 for 8B Instruct.
- **Qwen3-VL ScreenSpot-Pro** (same tables):

  | Model | ScreenSpot-Pro |
  |---|---|
  | 235B Instruct | 62.0 |
  | 32B Instruct | 57.9 |
  | 30B-A3B Instruct | 60.5 |
  | 8B Instruct | 54.6 |
  | 4B Instruct | 59.5 |

- **Qwen2.5-VL-72B:** RefCOCO val 92.7, ScreenSpot 87.1, ScreenSpot-Pro 43.6 (https://arxiv.org/html/2502.13923 Tables 6/9).
- **These benchmarks do not show crop-grade edges.** RefCOCO/REC scores count a box as a hit at IoU ≥ 0.5, and ScreenSpot counts a click inside the element. Neither measures how tight the box edges are. I found no source that quantifies Qwen3-VL box-edge tightness on document figures, and no general-VLM figure-class mAP on DocLayNet or OmniDocBench (not found).
  - SmolDocling reports qualitative Qwen2.5-VL layout errors on DocLayNet: recall misses on multi-column pages, and table/picture confusion (https://arxiv.org/pdf/2503.11576). This comes from a search summary and was not re-read.
  - Implication (inference, not sourced): use VLM boxes to pick or adjudicate regions, and snap the edges to detector or PDF geometry.

### Set-of-Mark prompting
- **What it is.** Yang et al. 2023 (Microsoft), arXiv 2310.11441. Off-the-shelf segmenters (SEEM/SAM) "partition an image into regions at different levels of granularity, and overlay these regions with a set of marks" (alphanumerics, masks, boxes). The model then answers with mark IDs instead of coordinates.
  - Zero-shot GPT-4V+SoM beat a fully fine-tuned specialist on RefCOCOg REC (https://arxiv.org/abs/2310.11441).
- **It can hurt weak readers.** Contrastive Region Guidance: "SoM generally decreases the performance of LLaVA-based models", because reading the marks needs OCR ability (https://arxiv.org/html/2403.02325 §4.2).
- **Document follow-ups:**
  - Doc-CoB: draws ID-marked layout boxes and re-renders the selected boxes. It reports that MLLMs often fail to match a box to its ID without extra training (https://arxiv.org/pdf/2505.18603, from a search summary).
  - DocTrace: Qwen3-VL-8B backbone, Aug 2026 (https://arxiv.org/abs/2608.03292). The search snippet says it ablates block-boundary+ID marks (37.7 vs 32.5). That was not verified from the full text.
- **Implication (inference):** a numbered-candidate overlay ("which of boxes 1..N belong to Figure 3?") suits a strong VLM such as Qwen3-VL-8B+ better than free-form coordinate regression.

### Doc VLMs and their figure boxes
- **MinerU2.5 / MinerU2.5-Pro (opendatalab).**
  - Layout covers image, chart (and chemical_structure in the text), image_caption, image_footnote, table_caption and others. Coordinates are relative; the client parses 0–1000 integers and divides by 1000 (https://arxiv.org/html/2509.22186; https://github.com/opendatalab/mineru-vl-utils/blob/main/mineru_vl_utils/mineru_client.py).
  - Middle JSON nests a parent `image` block with an `image_body` child and `image_caption`/`image_footnote` annotations (https://github.com/opendatalab/MinerU/blob/master/docs/next/middle-json/current-medium.md).
  - **Whole-figure container:** since Feb 2026 there is a block type `image_block` ("图像块(多图)", a multi-image container; https://github.com/opendatalab/mineru-vl-utils/blob/main/mineru_vl_utils/structs.py). Images and charts it covers are marked non-standalone, and captions it covers are dropped as internal (mineru_client.py).
  - The MinerU2.5-Pro-2605 card says "the missed detection rate for the `image_block` category has been significantly reduced" (https://huggingface.co/opendatalab/MinerU2.5-Pro-2605-1.2B, Apache-2.0).
  - Licences: 2509-1.2B is AGPL-3.0, Pro-2605 is Apache-2.0.
  - The paper does not say whether `image` includes the text inside the graphic. Note: MinerU 4.0.10 was already evaluated by the user. This `image_block` is likely what produced its "groups by panel letters/rows" behaviour (inference).
- **dots.ocr (rednote-hilab, MIT plus its own licence agreement, vLLM ≥ 0.11.0).**
  - Categories: Caption, Footnote, Formula, List-item, Page-footer, Page-header, Picture, Section-header, Table, Text, Title. Boxes are `[x1,y1,x2,y2]`.
  - "For the 'Picture' category, the text field should be omitted" (https://github.com/rednote-hilab/dots.ocr).
  - Boxes are absolute pixels on the smart-resized input, mapped back by `post_process_cells` (https://github.com/rednote-hilab/dots.ocr/blob/master/dots_ocr/utils/layout_utils.py).
  - Caption is a separate block with no grouping. Whether Picture includes internal text: not stated.
- **DeepSeek-OCR (MIT, 3.3B).**
  - `<image>\n<|grounding|>Convert the document to markdown.` gives `<|ref|>label<|/ref|><|det|>[[x1,y1,x2,y2]]<|/det|>`. Coordinates are normalised to 0–999: the demo divides by 999 and crops `image`-labelled boxes (https://github.com/deepseek-ai/DeepSeek-OCR; https://github.com/deepseek-ai/DeepSeek-OCR/blob/main/DeepSeek-OCR-master/DeepSeek-OCR-vllm/run_dpsk_ocr_image.py).
  - `Locate <|ref|>xxx<|/ref|> in the image.` does referring grounding.
  - DeepSeek-OCR-2 (Jan 2026, Apache-2.0, 3.4B; https://huggingface.co/deepseek-ai/DeepSeek-OCR-2): label set and box scale were not checked.
- **olmOCR-2-7B-1025 (Apache-2.0, Qwen2.5-VL-7B base).** Outputs linear text and Markdown only. The README mentions no boxes or layout regions (https://github.com/allenai/olmocr; https://huggingface.co/allenai/olmOCR-2-7B-1025).
- **Chandra / chandra-ocr-2 (datalab; weights are modified OpenRAIL-M, code Apache-2.0; served via vLLM).**
  - The `ocr_layout` prompt asks for `<div data-bbox="x0 y0 x1 y1" data-label=...>`, "Bboxes are normalized 0-1000" (https://github.com/datalab-to/chandra/blob/master/chandra/prompts.py).
  - Labels include Caption, Footnote, Image, Figure, Complex-Block, Diagram, Chemical-Block and others.
- **Surya / Marker (datalab).**
  - Surya maps raw `Image`→`Picture`, `Figure`→`Figure` and `Complex-Block`→`Figure` (https://github.com/datalab-to/surya/blob/master/surya/layout/label.py). So "Figure" covers composite or complex blocks and "Picture" covers plain images. No written definition was found.
  - Marker `group_caption_blocks` merges a Table/Figure/Picture with an adjacent Caption/Footnote. The rule is: neighbour in reading order and gap < 0.05 × page height. The result is a `FigureGroup`/`PictureGroup` (https://github.com/datalab-to/marker/blob/master/marker/builders/structure.py).
  - Licences: code Apache-2.0, weights modified AI Pubs OpenRAIL-M (https://github.com/datalab-to/surya).

## 5. Body text vs figure text (classic document analysis)

PDFFigures 2.0 states the established approach most directly. Body text is the document's dominant, consistent format, so outliers are figure text.
- **Its features**: modal font and font size; modal line width (≈ column width); modal line spacing and word spacing; modal left margins (column starts); vertical orientation; overlap with vector or bitmap graphics; above-median word spacing (tables). Section titles are rescued by margin alignment or centring, numbering or capitalisation, and a non-standard font. https://ai2-website.s3.amazonaws.com/publications/pdf2.0.pdf
- **Earlier HEP extractor** (Praczyk & Nogueras-Iso, "Automatic Extraction of Figures from Scientific Publications in High-Energy Physics", ITAL 2013; ref [10] in pdffigures2): clusters elements around large graphical regions. pdffigures2 took that clustering prune from it. (Same PDF.)
- **CERMINE**: does not separate figure text from body text at its first level. The SVM zone classifier (54 geometric and sequential features: zone size, position, neighbour distances, line height, previous zone's label, cross-page repetition) puts figures, tables and captions *inside* the "body" class. https://arxiv.org/abs/1710.10201 , https://link.springer.com/article/10.1007/s10032-015-0249-8
- **GROBID**: CRF/DL sequence labelling over pdfalto tokens. Layout features include font size, name, bold and italic, indentation, relative spacing, relative page position, character density, and the position of bitmap or vector graphics relative to text. The segmentation model works at line or zone granularity (zones "are never interrupting a line"), and separate figure and table models then label inside each figure or table zone. https://grobid.readthedocs.io/en/latest/Principles/
- **Docling**: no heuristic text classification. An ML layout model gives Picture clusters. Any regular cluster (text, section header, …) whose `intersection_over_self` with a Picture is > 0.8 becomes a *child* of that picture, and the picture box grows to enclose its children.
  - This is label-agnostic containment, but only inside a box the detector already drew.
  - Pictures covering more than 90 % of the page are discarded.
  - https://github.com/docling-project/docling/blob/main/docling/utils/layout_postprocessor.py
- **Takeaway**: a per-document body-text profile (font-size mode, line-height mode, line width ≈ column width, left-edge alignment to column margins, justified full lines, reading-flow continuity with the paragraphs before and after) is the standard discriminator. Graphics overlap and anomalous font, size or spacing mark figure text.
