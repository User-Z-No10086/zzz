# 下山的人 · 本体代码

> 一款用 Ren'Py 做的教学视觉小说：你说想学什么，AI 联网找资料、现场排一条学习路线；
> 六位 AI 娘当主讲，讲完在难点处考你，最后把自己讲的全擦掉，让你讲回去。

**本仓库只有本体代码**（`.rpy` + `.py` + 内容 JSON + 工具 + 文档），
不含 Ren'Py 引擎、立绘、字体、GUI 素材——这些用一条命令补齐。

![讲解](docs/screenshots/01b_claude_teach.png)

---

## 三步跑起来

```bash
# 1. 下载 Ren'Py 8.5.3 SDK（约 155 MB）
#    https://www.renpy.org/dl/8.5.3/renpy-8.5.3-sdk.zip
#    解压到任意目录，假设得到 renpy-8.5.3-sdk/

# 2. 补齐素材：从 SDK 复制 GUI/字体，并生成占位立绘
python tools/bootstrap.py --sdk renpy-8.5.3-sdk

# 3. 启动
renpy-8.5.3-sdk/renpy.exe .
```

`bootstrap.py` 做三件事，都不会覆盖你已有的文件：

| 步骤 | 内容 |
|---|---|
| 复制模板 | `gui.rpy` / `screens.rpy` / `options.rpy` 缺失时从 SDK 的 the_question 模板取 |
| 复制素材 | `game/gui/`（Ren'Py GUI 图）与 `game/fonts/SourceHanSansLite.ttf` |
| 生成占位 | 六位角色的 `normal.png`（纯标准库画的剪影）+ 背景图 |

想要真立绘：把自己的图覆盖到 `game/images/characters/<角色id>/normal.png`（建议 900×1300、透明底）。

## 想用真模型

```powershell
$env:ZHIPU_API_KEY="你的智谱 key"      # 或 $env:DEEPSEEK_API_KEY=...
renpy-8.5.3-sdk/renpy.exe .
```

不设也能玩：预置课程的讲解来自 `game/content/teach-cache.json`（预生成好的角色台词），
只是不能再现场生成新课程。

## 代码结构

```
game/
├── script.rpy          主流程：选课 → 选主讲 → 路径图 → 讲解/难点/反转 → 结局
├── screens_course.rpy  课程列表 + 学习路径图
├── hud.rpy             进度 HUD、选主讲
├── gal_setup.rpy       加载课程/角色、立绘、Runner 状态机、台词取值
├── engine/
│   ├── checks.py       四条硬校验 + 要点覆盖度 + 文本相似度
│   ├── novice.py       反转时的「初学者」
│   ├── teacher.py      主讲生成：人设提示词 + 硬/软校验 + 重试
│   ├── planner.py      课程规划：联网检索 → 生成课程 JSON
│   ├── llm.py          模型调用（智谱 / DeepSeek）
│   └── teachcache.py   台词缓存（带内容指纹）
├── content/            角色卡、课程、台词缓存
tools/
├── bootstrap.py        补素材（见上）
├── bake_teach.py       预生成台词缓存
├── eval_teach.py       讲解生成评测（成功率 / 人设符合度）
├── eval_reversal.py    反转判定评测
├── probe_voices.py     逐角色看生成效果
└── import_art.py       把原图处理成可用立绘（需要 Pillow）
docs/architecture.md    架构与设计取舍
```

引擎层是纯 Python（零第三方依赖），可以脱离 Ren'Py 直接跑评测：

```bash
python tools/eval_reversal.py     # 需要 Key
python tools/eval_teach.py
```

## 许可

代码 MIT（见 LICENSE）。立绘/字体/Ren'Py GUI 素材的授权见 NOTICE。
