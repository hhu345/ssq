# HANDOVER — 双色球选号 App 交接文档（给接手的 AI 开发者）

> 写给接手本项目的 AI（workbuddy）。请**先完整读完本文档再动代码**。

## 1. 项目是什么

双色球（中国福利彩）历史数据分析与选号 Android App，Kivy 框架，Python 单文件 `main.py`（约 2000 行）。
- 已有桌面 Web 版 + PyInstaller exe（在上级目录 `E:\longxia-project\主程序\`，与本 App 共享算法思路但代码独立）。
- 本项目只关心 `ssq_mobile/` 目录。
- 用户是地下空间结构工程师，非程序员；沟通请用中文，直接、简洁。

## 2. 文件清单（需要全部交接）

```
ssq_mobile/
  main.py                          # 全部业务逻辑 + UI（核心，约2000行）
  buildozer.spec                   # 打包配置（图标/启动页/权限/字体已配好）
  .github/workflows/build-android.yml  # GitHub Actions 云构建（两段式，勿回退！）
  icon.png                         # App 图标 1536x1536
  splash.png                       # 启动页 1600x2848
  simhei.ttf                       # 中文字体（9.3MB，已注册为默认字体）
  test_all.py                      # 业务逻辑回归测试 20 项（必须保持全过）
  HANDOVER.md                      # 本文档
```

- GitHub 仓库：`https://github.com/hhu345/ssq`（main 分支）。远程 URL 内嵌完整 token，用 `git remote get-url origin` 提取。
- 其余 test_*.py / diag_*.py / 0001.* 截图为临时调试文件，未提交，可忽略/清理。

## 3. 当前进度（2026-09-07）

### 已完成且稳定
- 全部业务功能：数据抓取（福彩 findDrawNotice 接口）、九维分析评分、加权选号（4 种玩法）、约束过滤、回测对比、购彩记录（存/删/复制/一键对奖）。
- 累计修复 10+ 类真机闪退，构建链路稳定（build #46 验证通过）。
- **UI 改版第一步已完成**：主题系统（浅/深双色板 `_Theme`/`C()`）+ 全套新组件库已写入 main.py 并通过语法/业务测试：
  - `Card`（圆角+柔和阴影卡片）、`Capsule`（圆角胶囊号码）、`Icon`（canvas 自绘线性图标：home/chart/target/loop/list/copy/trash/sun/moon/chev）、`IconBtn`、`PButton`（primary/soft/ghost/danger）、`TInput`（圆角输入框）、`TSpinner`（主题化下拉）、`SoftSlider`（自绘触控滑条）、`MixBar`（权重占比条）、`FoldPanel`（折叠面板）、`Toast`（浮出提示）、`SectionTitle`、`Hint`（自适应高度）、`_lbl`、`_bg`。
  - 兼容垫片：`_title_row`/`_hint`/`_ball_label`/`_row` 保留旧签名转调新样式，所以旧页面代码目前**能跑**。

### 未完成（接手者的任务）
**5 个页面 + 导航栏 + App 外壳仍是旧代码，尚未使用新组件库**（已验证：页面代码中 Card/Capsule/FoldPanel/IconBtn 使用次数为 0）。按用户新需求重写：

1. `OverviewScreen`（概览）、`AnalysisScreen`（分析）、`GenerateScreen`（选号）、`BacktestScreen`（回测）、`RecordsScreen`（记录）——全部改为卡片式新 UI。
2. 旧 `TabBar` 类 → 新 `BottomBar`（图标+文字 tab，纯白底，选中主色 #165DFF，未选中浅灰；上方加一行 8-9sp 合规小字）。
3. `SSQApp.build` → 挂 BottomBar、`Window.clearcolor = C('bg')`、实现 `rebuild_theme()`（主题切换时重建全部页面并恢复输入状态，BottomBar.refresh()）。
4. 深色模式切换入口：概览页标题右侧 IconBtn（light 模式显示 moon，点击 toggle）。
5. 业务回调（`_generate`/`_get_constraints`/`_latest_code`/`_save_ticket`/`_save_all`/`_run`/`_save_record`/`_del_record`/`_do_check` 等）逻辑**原样保留**，只换视觉组件；`_toast` 内部改用 `Toast()`。

## 4. 用户新需求原文（改版目标，必须完整满足）

彩票分析手机 APP，一共 5 个页面：概览、分析、选号、回测、记录，保留全部原有业务逻辑、全部参数、全部功能，只做 UI 视觉与交互改版，纯移动端触屏操作，不要 PC 鼠标交互。

整体风格：现代简洁轻量化移动端 UI，卡片式设计，圆角柔和，不要老旧原生安卓表单风格，摒弃大块生硬红蓝色方块。

全局规范：
- 主色调：沉稳深蓝色 #165DFF，背景使用浅灰白；热号用暖红色调，冷号用灰蓝色调，避免高饱和刺眼色块。
- 字体：思源黑体无衬线字体，区分标题、正文、辅助说明小字，次要信息用浅灰色弱化。
- 组件统一：所有号码改成圆角胶囊标签样式；卡片统一圆角 12-16px，搭配轻微柔和阴影；按钮使用圆角，适配手指点击，按钮尺寸符合移动端触控标准。
- 支持浅色 / 深色两套模式。
- 所有页面底部增加固定合规小字提示：本工具仅做历史数据统计演示，彩票开奖完全随机，无法预测开奖结果，不构成购彩建议。
- 底部导航栏：图标 + 文字组合 tab，当前选中项显示主色，未选中为浅灰色；导航背景纯白，轻量化，不要深色厚重底栏。

各页面：
- 概览页：最新开奖封装成独立卡片，开奖号码放大突出，奖池、销售额等信息作为次要小字。热号冷号：放弃老式方块平铺，使用标签流式布局，搭配小型简易条形图展示出现频次。历史开奖列表精简，每条记录号码使用圆角胶囊展示，减少页面拥挤。
- 分析页：红球蓝球评分网格，改为热力网格卡片，分数高低用颜色深浅区分；手指点击格子弹出分数详情弹窗。频率图表放大，优化移动端适配，用横向条形图直观展示号码出现频次。
- 选号页：权重滑块改成移动端适配的可视化滑条，页面可以直观看到四项权重占比示意。和值、奇偶、跨度等约束条件，设置为可折叠面板，默认收起，减少页面信息过载，参数提示用浅灰色辅助文字。生成出来的号码统一圆角胶囊样式；存入、批量存入按钮做轻量化触控按钮。
- 回测页：回测输入参数区域设置为可折叠面板，默认收起，页面主要展示"开始回测"操作按钮。回测输出结果：保留原有全部数值，搭配移动端适配的柱状对比图表，直观对比策略与随机样本的中奖分布。
- 记录页：每一条记录封装独立小卡片，号码用圆角胶囊；复制、删除改为图标按钮，点击触发操作。期号日期筛选使用移动端下拉组件，不用老式输入框。

禁止事项：不要 PC 端鼠标 hover、鼠标点击这类交互；全部交互基于手机手指触摸；原有全部业务参数、回测逻辑、选号逻辑完整保留，只改界面外观。

## 5. 代码边界（红线）

`main.py` 中 **1-约700 行是业务层，禁止改动逻辑**：
- `DataManager`（get_data/next_code/add_record/delete_record/check_records/save/load）
- 算法：`frequency/omissions/tail_freq/zone_freq/red_scores/blue_scores/check_constraints/draw_weighted/draw_n/_judge/_one_backtest`
- 常量：`RED_COUNT=33, BLUE_COUNT=16, RED_PICK=6, W_FREQ=0.30, W_OMIT=0.35, W_TAIL=0.20, W_ZONE=0.15`
- `get_data(n)` 的网络策略：仅在缓存为空或 n<=1000 且数据不足时才联网（这是性能修复，勿回退）。
- `next_code()` = 历史最新期号+1（用户规则，勿改）。

数据源字段：`rows[i] = {code, date, week, red[], blue, sales, poolmoney, prizes}`，`prizes[str(tier)] = {"count", "money"}`。
真机记录 JSON：`/data/user/0/org.lottery.ssq/files/ssq_records.json`（run-as 访问）。

## 6. 构建与发布（流程勿改）

- 本机无 WSL/Docker/Android SDK，**只能用 GitHub Actions 云构建**（用户否决过 WSL，太占内存）。
- workflow 是**两段式**：先让 buildozer 下载 SDK，再用其 sdkmanager 补装 `platforms;android-33`，然后正式构建。push 到 main 自动触发。
- git push 用代理 `127.0.0.1:7890`（需用户开 VPN；`git config http.proxy ...` 已配置）。
- 构建产物 = Actions artifact（APK armeabi-v7a）。下载 APK 用 Python requests（Authorization: Bearer <token>，实测 3+ MB/s）。
- 发布节奏：改完 → 本地测试全过 → commit → push → 等 build（约 25 分钟）→ 下载 APK → adb 装真机 → 用户验收。
- **用户下载 APK 后要删除项目文件夹里的 apk 文件（用户惯例）**。

## 7. 真机调试

- 手机：华为荣耀 YAL-AL00（Android 10, arm64-v8a），adb 序列号 `CUY0219702014648`，USB 调试已授权（adb 重启后需手机上重新确认弹窗）。
- adb 路径：`D:\Program Files\Netease\MuMu Player 12\nx_main\adb.exe`
- 安装流程：`adb uninstall org.lottery.ssq` → `adb push apk /data/local/tmp/ssq.apk` → `adb shell pm install /data/local/tmp/ssq.apk`（pm install 直接装比安装器快）。
- 崩溃定位：`adb logcat -c` → 启动 App → `adb logcat -d -s python:*` 抓 Python traceback。
- 截图：`adb exec-out screencap -p > x.png`；操作前先 `wm dismiss-keyguard` + `KEYCODE_WAKEUP` + keyevent 82（锁屏/熄屏截图会是白屏）。
- 操作屏幕：`input tap x y` / `input swipe ...`；屏幕 1080x2340，底部 tab y≈2200，tab x≈108/324/540/756/972。
- 模拟器 mumu12 是 x86_64，与 armeabi-v7a APK 不匹配，模拟器闪退不代表真机问题。

## 8. 已知坑（血泪教训，务必遵守）

1. **lambda 闭包捕获循环变量**：`w.bind(pos=lambda *a: setattr(w.bg, ...))` 在循环里必须写 `lambda *a, w=w: ...`（默认参数捕获）。已因此出过"5 张卡片背景全叠在一张上"的 bug。
2. **ScrollView minimum_height 不含 padding**：每个页面 content 用 `bind(minimum_height=lambda o,v: setattr(o,'height', v + dp(24)))` 补偿，勿删 +24。
3. **Label halign/valign 必须设 text_size** 才生效；`_lbl()` 已处理。
4. **Hint 文字必须自适应高度**（bind texture_size → height），固定 30dp 会溢出。
5. **本地桌面无法直接模拟手机密度**：`Config.set('graphics','density','3')` 无效；等效方案 = 开 360x780 窗口（density=1 时 1px=1dp）。
6. **Kivy 2.3.1 Spinner 无公开 open()**；程序化展开用 `_toggle_dropdown()`。
7. `Window.density` 不存在，是 `Window._density`。
8. `Window.screenshot(name=X)` 若目标编号文件已存在可能不生成新文件——跑诊断前先删旧的 `0001.*`，验证时取最新编号。
9. PowerShell 内联 python 复杂代码引号地狱 → 一律写临时脚本文件执行。
10. 视觉模型描述截图不可靠 → 用 PIL 像素统计（白带计数/特征色计数）交叉验证。
11. 中文必须用注册的 simhei（`LabelBase.register`），新组件不要指定别的 font_name。
12. `SoftSlider` 是自绘 Widget（非 Kivy Slider 子类），触摸逻辑在 on_touch_down/move，别改成 Slider（内部 graphics 会打架）。
13. 主题切换用**整页重建**方案：`SSQApp.rebuild_theme()` 遍历 5 个 Screen 的 rebuild()；每个 Screen 的 rebuild 要 snapshot/restore 输入状态（选号页权重/约束/玩法/期数注数、回测页 4 参数）。
14. 用户手机后续会换小米 15/15Ultra：布局全部用 dp/sp，已是密度自适应，无需特殊处理。

## 9. 验收标准（改版完成后）

1. `python test_all.py` 20/20 通过（业务逻辑零回归）。
2. 本地 360x780 窗口渲染 5 个页面 + 折叠面板展开/收起 + 深浅主题切换各截一张图，PIL 像素验证关键元素渲染（卡片白底、胶囊、tab 高亮）。
3. push → GitHub Actions 构建成功 → 真机安装 → 用户逐页验收。
4. 真机重点检查：底部合规小字固定可见、tab 图标+文字、记录页复制/删除图标按钮可点、选号页约束折叠默认收起、权重滑条手感、深色模式全页无白块。

## 10. 给接手 AI 的第一步建议

按顺序：通读 main.py 的 Screen 类（OverviewScreen 起到文件尾）→ 用新组件库逐页重写（建议顺序：BottomBar+App 外壳 → 概览 → 记录 → 选号 → 分析 → 回测）→ 每完成一页跑 `ast.parse` + `test_all.py` → 全部完成后按第 9 节验收。
