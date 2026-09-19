# Figure AI → AI

**从灵感到矢量。** 第一个 AI 是人工智能，第二个 AI 是 Adobe Illustrator。

这是一个 Codex skill：把科研绘图需求或参考图转成可编辑 SVG，再在 Illustrator 中保存原生 `.ai` 与出版预览。原名称为 `scientific-figure-to-illustrator`。

## 工作流程

文字需求或参考图 → 科学结构与标签确认 → 平滑几何重建 / 本地轮廓追踪 → 活文字 SVG → Illustrator 原生 AI → 导出预览与视觉检查。

- 简洁机制图优先使用少量几何对象重建，避免自动追踪产生毛边和浅色碎片。
- 复杂轮廓可选本地 VTracer，逐图检查候选，不保证任意图片一键达到出版质量。
- 保留可编辑文字、独立对象和旧版文件；现有矢量图可直接局部修改。
- SVG 转换不依赖付费矢量接口；图像模型与 Illustrator 仍需各自可用的能力和许可。

## 安装和调用

将本仓库克隆到 Codex 的 skills 目录下，目录名为 `figure-ai-to-ai`。Windows 默认安装示例：

```powershell
git clone https://github.com/TyrionH-is-coding/figure-ai-to-ai.git "$env:USERPROFILE/.codex/skills/figure-ai-to-ai"
```

若目标目录已存在，请先检查已有版本，不要覆盖。私有仓库需要 GitHub 访问权限。安装后新开 Codex 会话，输入：

> 使用 $figure-ai-to-ai，根据这张参考图生成可编辑 SVG 和 Adobe Illustrator AI 文件，保留活文字，检查边缘、上下标和重叠。

入口是 [SKILL.md](SKILL.md)。完整流程见 [workflow.md](references/workflow.md)，原生导出注意事项见 [illustrator.md](references/illustrator.md)。

## 环境与验证

- SVG 检查和文字合并：Python 标准库；示例命令使用 Python 3.12。
- 本地自动追踪（可选）：安装 `scripts/requirements-trace.txt` 中的 Pillow 和 VTracer，建议独立虚拟环境。
- 原生 AI 导出助手：Windows、PowerShell、已安装的 Adobe Illustrator；默认 COM 标识对应 Illustrator 2026。
- 图像生成：使用当前 Codex 环境提供的图像模型，不绑定固定模型版本。

```powershell
python -m unittest discover -s tests -v
node tests/test_exporter.js
```

单元测试与结构检查不能替代科学内容审核和最终视觉检查。原生导出会检查对象、文字及重新打开后的结果，仍需查看实际导出的 PNG。

本仓库不含 API 密钥、个人课题资料或历史图稿。它不是 Adobe 官方产品，也不捆绑 Illustrator 或第三方服务。
