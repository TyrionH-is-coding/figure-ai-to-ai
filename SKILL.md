---
name: figure-ai-to-ai
description: 将科研绘图需求或参考图转成可编辑 SVG，再用 Adobe Illustrator 保存原生 AI 文件与出版预览。适用于绘图到SVG到AI全流程、位图机制图重建、描摹后的毛边与浅色碎片修复和现有矢量图局部修改；优先本地几何重建，复杂轮廓可用本地自动追踪。
---

# Figure AI → AI

从灵感到矢量：AI 绘图 → 可编辑 SVG → Adobe Illustrator。

交付可继续编辑的 `master.svg`、`master.ai`、Illustrator 导出的预览 PNG，以及简短的检查结果。`.ai` 指 Adobe Illustrator 文件。

这是从已验证的本地科研图工作流提炼出的独立 skill。SVG 转换和 AI 导出均在本机完成；图像模型生成/修改参考图是独立的一步，使用该模型本身的数据处理方式。无需配置付费矢量服务或 Cell-LCT 密钥。

## 先确定当前阶段

- 只有文字需求：整理科学结构与标签，用可用的内置图像生成工具生成参考图。用户已给详细提示词时保留其科学约束。遵循当前 imagegen 工具/skill 的调用方式，不锁定某个历史模型名。
- 已有位图：先看图，记录所有文字、箭头关系、重复元素、配色与需要保留的部分。
- 已有通过检查的 SVG/AI：从现有矢量源局部修改；不必重新生成参考位图。
- 用户只要 SVG、局部改图或方案：停在请求的阶段，不强制执行整个流程。

读 [references/workflow.md](references/workflow.md) 获得参考图、文字清单与质量判定规则。需要 Illustrator 导出时再读 [references/illustrator.md](references/illustrator.md)。

## 默认路径：效果优先的几何重建

1. 确定参考图与科学内容。通常采用白底、二维、统一描边和受控色板；具体风格服从用户。没有来源的表位、机制关系和精确残基位置不应由绘图补全。
2. 将图分解为语义对象：主体轮廓、连接线、箭头、标记、文字、重复小元素。使用少量平滑 Bézier、椭圆等原语重建 SVG。每类对象用稳定 `id`/`g` 分组，重复小元素各自可编辑。
3. 文字用真正的 `<text>/<tspan>`；保留 Unicode、上标、单位和标签含义。SVG 里嵌入 PNG 或把所有文字转轮廓，不算达成可编辑交付。
4. 修订优先只改有关对象。标签与其目标一起调整；连线端点落到目标边界，避免穿过文字和产生冒头短线。用户确认过的其他区域保留。
5. 执行结构检查，再渲染查看全图和改动局部。通过后导入 Illustrator，保存新 `.ai` 并导出 PNG，读回 AI 检查对象与文字。

这里的“AI 描绘”通常是 Illustrator 将 SVG 几何导入为原生对象，并非第二次视觉识别。已有 SVG 不需要再次 Image Trace。若用户明确要逐笔播放，可在现有 Cell-LCT 缓存播放器可用时采用它；先读取其当前入口说明，报告该依赖，不将它作为本 skill 必需组件。

## 备选路径：本地自动追踪

大量不规则轮廓难以直接重建时，使用 VTracer 生成候选，再按参考图检查。对已有图改动文字区域，先用图像编辑工具去字，保留所有非文字结构；文字清单必须在去字前保存。

```powershell
# 将 $skillDir 设为本 SKILL.md 所在目录；$jobDir 为新建任务目录。
py -3.12 "$skillDir/scripts/svg_pipeline.py" trace --input "$jobDir/clean.png" --output-dir "$jobDir/trace"
py -3.12 "$skillDir/scripts/svg_pipeline.py" merge-text --svg "$jobDir/trace/faithful-geometry.svg" --manifest "$jobDir/text-manifest.json" --output "$jobDir/master.svg"
```

运行前以 `--help` 核对当前脚本参数。追踪可选依赖见 `scripts/requirements-trace.txt`，装到任务虚拟环境即可；基础检查和文字合并只需要 Python 标准库。

候选不自动按 PSNR 或颜色数选优。曾经出现的浅色“半透明”碎片其实是抗锯齿像素被追踪为不透明浅色路径；`opacity=1` 不能证明视觉质量合格。若一轮候选仍有毛边、吞掉空白或小结构、箭头损坏，就转几何重建，避免无休止调参。不要套用凝血酶原示例的固定色板。

## 检查与 AI 导出

```powershell
py -3.12 "$skillDir/scripts/svg_pipeline.py" inspect "$jobDir/master.svg" --expected-text 12
powershell.exe -NoProfile -File "$skillDir/scripts/export_illustrator.ps1" `
  -SvgPath "$jobDir/master.svg" -AiPath "$jobDir/master.ai" `
  -PngPath "$jobDir/preview.png" -ExpectedText 12 -Dpi 300
```

`12` 是示例，必须换成本图实际预期文字数。原生导出助手会先调用 SVG 检查，缺少默认 `py -3.12` 时用 `-PythonExe` 指定可用 Python。它在单独文档导入 SVG，不依赖当前画布是否为空；只保存新的路径，不覆盖源文件，不关闭用户原有文档。运行时可启动已安装的 Illustrator；若用户要求不得启动，则先用 `-Probe` 检查并尊重该限制。

确认原生路径存在、没有栅格/链接对象、文字仍可编辑，再看 Illustrator 导出的 PNG。字体计数或文件存在不足以证明所有标签无截断；检查上下标、中文、连线、描边和层叠。导出默认 300 dpi，实际物理尺寸由 SVG 的画布尺寸决定。

结构检查通过但未运行 Illustrator 时，只能报告“SVG 已检查，AI 阶段未验证”。Illustrator 卡住时保护已有文档与文件，停止继续投递命令，不强杀、不重新叠加绘图。图像模型或软件确实不可用时说明缺失环节，不宣称全流程完成。

## 输出约定

每次任务创建新目录或版本后缀，保留原图和旧版。保存选定参考图、必要的文字清单/生成脚本、SVG、AI、PNG和检查报告即可，不要求复制所有实验候选。使用简短正常进度说明，不包含密码、API key 或无关宣传。

交付时说明采用几何重建还是追踪、实际完成哪些验证，附可点击文件。具体科研示例只用于展示绘图方法，不把示例结论推广成所有课题的绘图规则。
