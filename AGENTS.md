# AGENTS.md · 小红书点赞分析

> **继承 `D:\记忆\通用规范`（handbook v1.0），以下仅列本项目特有约束与例外。**
> 通用纪律（角色分工、执行纪律、安全红线、知识管理定界）不再重复，以 handbook 为准；冲突时本文件优先。

## 项目是什么

小红书点赞笔记：每日定时任务抓取点赞 → 点点 AI 深度分析 → 飞书云镜像 + Obsidian 知识库。
结构与运行见 `README.md`；目录：`00_项目驾驶舱_可视化中心/`（人工阅读层）、`知识库/`（99 篇七大类）、`b_answers/`（全文事实层）、`_系统数据/`（11 个管线 JSON，勿改名移出）、`scripts/`、`docs/`。

## 自动识别的策略

用户说"筛选/处理/审判笔记、继续、一审二审、这篇留不留"等 → **必须先读
`00_项目驾驶舱_可视化中心/笔记筛选规范.md` 再动手**，不要重新设计流程。
要点：助手只给预判和理由，用户做最终判决；一审不动数据；判删四处同步真删（全文+台账+映射+飞书行）；长期资产入精选保留库；可脱离工具版本的方法提炼入保留_案例与方法.md。

## 本机/项目例外（相对 handbook 的补充）

- 跑脚本用 uv 独立 Python：`C:\Users\郭永涛\AppData\Roaming\uv\python\cpython-3.11.15-windows-x86_64-none\python.exe`（本机系统 Python 已失效）
- PowerShell 5.1 不支持 `&&`；中文 JSON body 写临时文件再 `curl.exe --data-binary @文件`
- 每天 01:00（北京时间）定时任务 `XHS_LikeManager_Daily`（pythonw 无窗口；2026-10-09 由 10:17 调整，WakeToRun 已开睡眠也会唤醒）；改 `scripts/` 与 `_系统数据/` 必须保证其不断，改动先 dry-run/py_compile
- lark-cli 现行路径：`C:\Users\郭永涛\.trae-cn\plugins\trae-remote-official\lark\1.0.5\bin\lark-cli.exe`；调 `@文件` 参数时 subprocess 的 cwd 须设为 `_系统数据/`
- 管线 JSON 的读写位置常量已全部指向 `_系统数据/`（5 个 py + 2 个 ps1），不要再写回根目录

## 接手四读（任何 Agent 开场必读，2026-09-30 融合登记）

1. **路由**：`D:\记忆\项目清单\projects.yaml` —— 我在哪、兄弟项目在哪、归档去哪查
2. **规范**：`D:\记忆\通用规范`（handbook v1.0）＋ 本文件（项目例外）＋ `00_项目驾驶舱_可视化中心/笔记筛选规范.md`（筛选细则）
3. **记忆**：`D:\记忆`（人的长期记忆真源）＋ 当前 Agent 自己的会话记忆目录
4. **收尾**：本轮事实写进 `D:\记忆\轮次记录\YYYY-MM-DD.md`（Work vault 内，写入即进 Obsidian，无需另传）
