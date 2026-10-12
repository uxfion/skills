# paddleocr：裁剪图紧贴边界

不改（2026-10-11）：贴边是 PaddleOCR 的默认行为，用户决定维持原样。查到的情况记在下面，以后要留边时从这里开始。

## 场景

2026-10-11，用户翻看第三批留出复验的框图和裁剪图后问：「你是刻意那么裁剪那么小的吗？我指的是裁剪的贴近边界，很贴近很贴近」。

实例：brodeur 第 12 页 Fig. 2，横轴标题 “Bond Differential Diagnosis Score” 被切掉一半；另有几处坐标轴标签、图例贴着裁剪边。

用户听完原因后说：「如果它是默认行为，那就不用改动它」，又让查 PaddleOCR 能不能调这个参数，并提醒：「这个是 layout 的参数吧？…万一是用于 OCR 或其他的一些参数，改了肯定会出问题的」。

## 原因

- 单块图是 PaddleOCR 自己裁的，按版面框原样切，不留边：`paddlex/inference/pipelines/layout_parsing/utils.py` 的 `_crop_image_region_for_pil`，即 `original_img[y_min:y_max, x_min:x_max]`。版本 paddleocr 3.7.0、paddlex 3.7.2。
- 合成整图沿用同样的做法：取各块框的并集，原样切（`parse.py` 的 `save_crop`）。
- 版面模型的框贴着内容画，偶尔画进内容里。

## 有没有参数

PaddleOCR 没有只管裁剪留边的参数。唯一相关的是 `layout_unclip_ratio`，它属于版面检测，不是裁剪参数：

- 作用：版面检测后，以框中心为基准，把宽高乘以这个比例（`paddlex/inference/models/object_detection/processors.py` 的 `unclip_boxes`）。
- 设置方式：
  - 命令行 `--layout_unclip_ratio`，只能填一个数；
  - Python 接口和产线配置还可以填（宽, 高），或按类别 id 填字典。PP-DocLayoutV3 里 chart 是 3，image 是 14。
- 默认值：PaddleOCR-VL 的配置里是 `[1.0, 1.0]`，不放大。
- 放大后的框流向整条流水线（`paddleocr_vl/pipeline.py`）。所以它改的不只是裁剪：
  - 重叠框过滤 `filter_overlap_boxes`：框放大后重叠变多，可能删掉框；
  - 送给 VL 识别的区域（`crop_by_boxes`）：正文、表格、公式框一起变大，相邻的行可能被读进来；
  - JSON 里的 `bbox`；
  - 保存下来的 `img_in_*` 裁剪图。
- 别和 `text_det_unclip_ratio` 搞混：那是 PP-OCR 文字检测的参数，搜 “unclip_ratio” 的结果大多是它。

## 相关 issue

- PaddleOCR #18327（2026-08-26），后转为讨论 #18335：「PaddleOcr-Vl-1.6 及 在aistudio中识别的图片截图总少了那么一点点」，请求「向边缘扩展一点点」。
  - 协作者 SWHL 于 2026-08-30 回复：「这个应该可以实现。不过应该要去改一下源码。PaddleOCR-VL.1.6中是前置了一个版面检测模型。」
  - 回复没有提 `layout_unclip_ratio`。
- 同题讨论 #18326 没有回复。
- 没找到有人用 `layout_unclip_ratio` 给图片留边的报告，也没找到它的副作用报告。

## 以后要留边时

不碰 `layout_unclip_ratio`。在裁剪这一步自己放宽：
- 只放宽裁剪图文件，JSON 的 `bbox` 保持原样；
- 碰到图注、正文就停。

2026-10-12 起，裁剪图会按 `--crop-dpi` 从 PDF 重新渲染再切（`parse.py` 的 `recrop`，见 [20261012-paddleocr-figure-crop-resolution-fixed.md](20261012-paddleocr-figure-crop-resolution-fixed.md)）。要留边时，在那里放宽框。
