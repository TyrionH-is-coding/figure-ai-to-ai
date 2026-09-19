# Illustrator 原生导入、保存与读回

## 运行条件

Windows、已安装 Adobe Illustrator、Windows PowerShell 5.1、Python 3.11+。默认 Python 调用为 `py -3.12`；其他环境通过 `-PythonExe <绝对路径>` 指定。默认 COM 注册名为本流程实测的 Illustrator 2026 `Illustrator.Application.30`；不同版本用 `-ProgId` 指定实际注册名。避免在通用 ProgID 卡住时不断追加连接。

```powershell
powershell.exe -NoProfile -File "$skillDir/scripts/export_illustrator.ps1" -Probe
```

Probe 只查注册信息和运行进程，不创建文档、不启动 Illustrator。导出用 COM 和 ExtendScript 驱动已安装软件，并按需启动软件；不要求先手工建空白文档。

## 导出

先完成 SVG 和文字检查。AI、PNG 及 `AI路径.qa.json` 均需为新路径。指定同一任务输出目录，源 SVG 保留。

```powershell
powershell.exe -NoProfile -File "$skillDir/scripts/export_illustrator.ps1" `
  -SvgPath "$jobDir/master.svg" -AiPath "$jobDir/master.ai" `
  -PngPath "$jobDir/preview.png" -ExpectedText 3 -Dpi 300
```

流程是：SVG 预检 → 单独打开 SVG → 统计原生路径/文字/栅格/链接 → 保存 `.ai` → 关闭并重新打开本次新存的 AI → 对比对象计数和文字内容 → 导出预览 PNG → 输出 QA JSON。不删除或关闭用户其他文档，不把 PNG 放入 AI 伪装为可编辑矢量。完成后保留本次 AI 文档打开。

打开文档由宿主 COM 单独调用，然后才调用 ExtendScript 访问 DOM；不要把 open、即时读对象、close、reopen 全塞进同一次脚本求值。本机 Illustrator 30.0.0 曾因此报“there is no document”，分阶段调用已通过实机测试。

透明度、渐变、剪切效果等在此平面工作流中会被预检拒绝；应从源 SVG 中做明确的适配，不能在导出后通过栅格化掩盖。如果源 SVG 已在 Illustrator 打开，助手会拒绝接管它；先复制为新的任务文件，再对副本导出。

SVG 导入可能将多行或上标拆成多个原生文本框，不能要求两边的框数机械相等。助手会比较源 SVG 与原生文字的完整字符库存（仅忽略空白），并记录是否逐组相等；字符丢失会失败。若 `splitTextRequiresVisualReview=true`，必须逐标签核对拆分、顺序与位置；字符库存相同本身不能证明语义顺序正确。AI 保存后重新打开还需保持实际文本框、内容和路径计数一致。

QA 记录 Illustrator 版本、原生对象计数、AI 读回计数、实际文字和字体、画板尺寸及导出分辨率。它验证可编辑结构，最终 PNG 必须用图片查看工具检查。若当前 Computer Use 支持原生应用，可额外在 AI 画面点击路径/文字查看；原生控制不可用时明确说明采用 Illustrator 原生导出与读回验证。

随包 `assets/smoke.svg` 使用 Microsoft YaHei 显示中文，单独为 `Ca²⁺` 指定 Segoe UI Symbol；本机测试中 Microsoft YaHei 的上标加号发生缺字，即使字符库存仍相同。新机器仍需确认字体实际存在及渲染结果，不能将一次字体通过当作跨机器保证。

## 出错与恢复

SVG 检查失败时不启动 Illustrator。应用调用失败则报告该阶段，保留输入及已产出的新文件；不自动覆盖重试，换新版本名或检查已完成的文件。

COM 调用偶尔会因应用对话框或忙碌而暂停。超过合理等待时检查进程是否响应，暂停投递后续命令，不强杀 Illustrator。如果用户使用的是旧版 Cell-LCT 逐批播放器，恢复需要其原始 `.ai`、immutable geometry cache 和 playback checkpoint；不能用本 skill 的整图导入向原图重复追加。
