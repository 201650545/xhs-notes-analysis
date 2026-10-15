---
name: xhs-like-daily
description: 小红书点赞每日管线（A取消旧赞/B新笔记v3分析/C旧信息时效复核）的执行与补跑手册。Use when 用户要求跑或补跑点赞任务、取消旧点赞、分析新点赞笔记、点点总结、联网复核旧笔记，或这些任务失败/被跳过时排查。勿用于批量筛选删除（用 multi-store-sync-delete）。
---

# 小红书点赞每日管线

执行/补跑/排查 A·B·C 三个任务。本文件只是**入口与红线**，逐步操作以脚本和 docs 为唯一真相源，勿在本文件复制长 SOP（双写会腐烂）。

## 任务是什么

| 任务 | 干的事 | 关键常量（scripts/xhs_like_manager.py 顶部为准） |
|---|---|---|
| A | 枚举全部点赞，取消旧赞 | 保留最近 `KEEP_RECENT=100` 篇；当日随机配额；连续失败 5 次主动终止防风控 |
| B | 对新点赞做点点 v3 深度分析，分析后取消 | 每日分析上限 `B_DAILY_MAX=20`；全文落 `b_answers/<note_id>.txt`，上行飞书并写 `_lark_map.json` |
| C | 旧信息联网时效复核（Kimi，独立子进程 review_stale.py） | 每日 ≤3 篇 |

## 怎么跑

- 日常由计划任务 `XHS_LikeManager_Daily` 自动跑（仅交互登录时运行，错过开机补跑）；无窗口 pythonw
- 手动/补跑（在 `scripts\` 目录下，用 uv Python，本机系统 Python 已失效）：
  - `…\uv\python\cpython-3.11.15-windows-x86_64-none\python.exe xhs_like_manager.py --only A|B|C`
  - 其他开关：`--quota N`（A 测试配额）、`--enumerate-only`（只枚举）、`--backfill N`（回溯 N 篇）
- 是否运行过/结果如何：看 `logs\mgr_YYYY-MM-DD.log`，不要靠猜

## 红线（违反必返工或触发风控）

1. **登录态会过期，代码无法绕过**：症状=个人主页无"点赞"tab、出现登录遮罩。确诊后只能让用户在真实 Chrome 扫码/手机号重登，别尝试脚本绕过
2. **A 大枚举+取消后不要立刻跑 B**：B 读接口会被限流（empty_response 约十几分钟后 bootstrap 失败中止）。补跑 B 前冷却约 1 小时（用一次性计划任务延后启动）
3. **排除类不分析直接取消**：做菜类与影视解说类，关键词在 `scripts/batch_final.py` 的 `KW_EXCLUDE`（manager 与回溯都调 `excluded()`）；改排除词只改这一处
4. **点点提问走 v3 分区模板**（docs/04），必须含"笔记内容/联网补充"分区；提示词安全线 ≤588 字（首页搜索框约 836 字硬拦截，超长静默不发送、不报错）；视频内操作提示词要原样输出
5. **浏览器输入**：Vue 受控组件必须 JS setter+input 事件注入、用回车/JS click 发送；链接必须 CDP 物理键盘 Ctrl+V 粘贴才能触发卡片识别
6. **链接要带 xsec_token**，note_id 匹配路径末端 24-hex（uid 同为 24 位，别取错）；无 token 的 /explore 链接点点返回 NOT_FOUND
7. 点点答案要双重平稳态轮询（连续 2 次文本一致、过滤"思考中"占位），防流式截断
8. 全程复用同一点点 `ai_chat` 标签页，结束关闭本次新开的全部标签页
9. Windows 调 webbridge：JSON body 写唯一命名临时文件再 `curl.exe --data-binary @file`，中文内联必坏；lark-cli 中文路径参数同理，用 `@./file` 且 cwd 设在 `_系统数据`

## 结果放哪（落位即契约，别换地方）

- v3 分析全文：`b_answers/<24位ID>.txt`（前三行：版本标记/标题/原链接）
- 管线状态：`_系统数据/`（`_new_tasks.json` B 基线与 processed、`_lark_map.json`、`_liked_snapshot/_liked_all_full`、`_unlike_progress` 等 11 个 JSON，勿改名移出）
- 飞书表：单向上行云镜像（本地唯一可写），现存行与 `_lark_map.json` 一致
- 日报：`reports/小红书点赞分析_YYYY-MM-DD.md`；运行日志：`logs/mgr_YYYY-MM-DD.log`
- 新分析出的笔记按筛选制处理，筛选与真删走 `multi-store-sync-delete` + `00_项目驾驶舱_可视化中心/笔记筛选规范.md`，不在本 skill 范围

## 出问题的排查顺序

1. 读当天 `logs/mgr_*.log` 末尾 traceback
2. webbridge：`kimi-webbridge status` 看 running/extension_connected；502 按 docs/02 §1.2 重装官方扩展并激活 sidepanel
3. 登录态：见红线 1
4. 限流：见红线 2，冷却后只补失败的任务
5. 点点 DOM/发送/截断问题：docs/02 §5 与 docs/03 踩坑记录
6. 修管线脚本后先 `py_compile`，再用 `--only`+`--quota` 小样本验证

## 文件地图

- 入口脚本：`scripts/xhs_like_manager.py`（A/B/C 调度，常量在顶部）
- 复核子进程：`scripts/review_stale.py`；排除词与批量收尾：`scripts/batch_final.py`
- 提问模板：`docs/04-问点点深度提问模板.md`
- 踩坑全集：`docs/03-踩坑记录与治理对策.md`；初代手工 SOP（部分路径已失效，仅 DOM/JS 片段仍可参考）：`docs/02`
- 项目约定与读取顺序：根 `AGENTS.md` → `README.md`
