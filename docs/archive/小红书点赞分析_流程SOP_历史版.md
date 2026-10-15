# 小红书点赞每日总结 · 流程 SOP（固化版）

> 用途：定时任务「小红书点赞每日总结」每次执行的完整可复用流程。首次固化为 2026-08-30，基于当日 11 条新增视频成功执行的实践经验与调试产物（`_xhs_dd_inputs.json`、`_dd_send.py`、`_dd_extract.py`、`_xsec_links_20260830.json`）。
> 目标：少浪费、快提取、快提问、结束后清理自己打开的标签页。

---

## 0. 关键路径速查

| 项 | 值 |
|---|---|
| 赞过页 | `https://www.xiaohongshu.com/user/profile/{uid}?tab=liked`（当前 uid `<XHS_USER_ID>`） |
| 飞书 Base | `<FEISHU_BASE_TOKEN>`，表 `<FEISHU_TABLE_ID>` |
| lark-cli | 完整路径调用（见规则文件），`--as user`，`--format json`（勿用 ndjson） |
| kimi-webbridge HTTP API | `POST http://127.0.0.1:10086/command`，body `{"action":"evaluate","args":{"code":"..."},"session":"xhs"}`，返回 `{"data":{"value":...}}` |
| 点点对话 | 输入框 `textarea.textarea--v1-caret`；发送按钮 `div.submit-button-wrapper`；答案元素 `.ai-message`（取最后一条） |
| 输出目录 | 报告 `D:\workbuddy 工作空间\小红书点赞分析_YYYY-MM-DD.md`；原始存档 `D:\workbuddy 工作空间\点点分析结果\raw_YYYYMMDD\raw_{序号}_{note_id}.txt` |

---

## 1. 环境准备

1. 检查 kimi-webbridge 守护进程：
   ```powershell
   & "$env:USERPROFILE\.kimi-webbridge\bin\kimi-webbridge" status
   ```
   未运行则 `start`；必要时清理陈旧 PID 文件。守护进程必须运行，因为全流程走其本地 HTTP API 驱动用户真实浏览器。
2. 确认用户已登录小红书（www.xiaohongshu.com）。

## 2. 拉取最新点赞列表（一次 evaluate 批量提取，勿进详情页）

用 kimi-webbridge HTTP API 执行一次 JS，把「赞过」页当前已渲染的全部卡片一次性提取出来：

```javascript
(() => {
  const uid = /\/user\/profile\/([^/?]+)/.exec(location.pathname)?.[1] || '';
  const items = [];
  // 赞过页卡片容器，选择器按页面结构调整（必要时先 inspect 一次）
  const cards = document.querySelectorAll('section.note-item, div.note-item');
  cards.forEach((c) => {
    const a = c.querySelector('a.cover') || c.querySelector('a');
    const href = a ? (a.getAttribute('href') || '') : '';
    // 只要包含 note id 的链接；优先带 xsec_token 的完整链接
    const m = href.match(/([0-9a-f]{24})/);
    if (!m) return;
    const id = m[1];
    const full = href.startsWith('http') ? href
      : (href.startsWith('/user') ? 'https://www.xiaohongshu.com' + href
      : 'https://www.xiaohongshu.com/user/profile/' + uid + '/' + id + href.includes('xsec_token') ? href.split('?')[1] || '' : '');
    const title = (c.querySelector('.title, a.title')?.innerText || '').trim();
    const author = (c.querySelector('.author, .name, .author-wrapper .name')?.innerText || '').trim();
    const like = (c.querySelector('.like-wrapper .count, .count, .like')?.innerText || '').trim();
    const type = /视频|笔记/.test(c.innerText) ? ((c.innerText.includes('视频') ? '视频' : '笔记')) : '';
    items.push({ id, href, title, author, like, type });
  });
  return JSON.stringify(items);
})()
```

要点：
- **必须带 xsec_token**。纯 `/explore/{id}` 链接会被点点返回 `NOT_FOUND`（见 `xhs_xdian_results.txt` 历史记录）。若一次拿不到完整 xsec 链接，回到「赞过」页的卡片 a 标签里取完整 href（形如 `/user/profile/{uid}/{note_id}?xsec_token=...&xsec_source=pc_user`）。
- 一次拿全：标题、作者、点赞数、类型；**不要**逐条点进详情页（慢且可能触发反爬 404）。
- 若页面只渲染了部分，滚动到底后再次 evaluate 补拉，直到没有新卡片或达到上限（约 30~40 条即可）。

## 3. 读取飞书已有记录（一次拿全）

```powershell
& "C:\Users\<USER_NAME>\.real\.bin\node\lark-cli.exe" base +record-list --base-token <FEISHU_BASE_TOKEN> --table-id <FEISHU_TABLE_ID> --as user --format json
```
（命令路径以当前项目规则文件为准。）取出全部已有记录的**链接**清单；缺链接的记录用**标题**兜底。保存快照供比对。

## 4. 找出新增

- 以链接为准：赞过列表中的链接不在表格记录里 → 新增。
- 同一链接只处理一次：取消赞后重赞、标题被作者改动，都不重复总结。
- **若无新增**：跳过总结与表格更新，走第 7 步清理后，回复只说明「本次无新增」。

## 5. 点点总结（复用同一对话标签页，逐条快速提问）

全程**只用一个**小红书点点对话标签页，不每条新开标签页。用 kimi-webbridge HTTP API 直接 evaluate，避免逐帧快照：

1. 打开一个点点对话标签页（若没有就打开一个），记住其 tab 索引/URL。
2. 对每条新增视频，构造提问：
   `请总结这个小红书视频的内容，给出内容概要、主题分类、关键信息点：{完整xsec链接}`
3. **注入文字**（type 命令会丢文字，必须用 JS 原生 setter + input 事件）：
   ```javascript
   (() => {
     const ta = [...document.querySelectorAll('textarea')].find(t => t.offsetParent !== null);
     if (!ta) return 'no ta';
     ta.focus();
     const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
     setter.call(ta, PROMPT);
     ta.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: PROMPT }));
     return 'injected:' + ta.value.length;
   })()
   ```
   （`PROMPT` 用 JSON 字符串内联；也可退回 `document.execCommand('insertText', false, msg)` 方案。）
4. **发送**：点击 `div.submit-button-wrapper`（用 JS `.click()`，勿用 opencli click --nth 0）：
   ```javascript
   document.querySelector('div.submit-button-wrapper')?.click();
   ```
5. **等待并取答案**：1~2 秒短增量轮询，`document.querySelectorAll('.ai-message').length` 比发送前 +1 即就绪；取最后一条：
   ```javascript
   (() => {
     const ms = [...document.querySelectorAll('.ai-message')];
     const last = ms[ms.length - 1];
     return last ? (last.innerText || '').trim() : '';
   })()
   ```
   备选：取 `.main-container` innerText。
6. 每条原始回复（含【用户提问】+【点点回复】）存到 `D:\workbuddy 工作空间\点点分析结果\raw_YYYYMMDD\raw_{序号}_{note_id}.txt`。

## 6. 生成报告 + 批量写入飞书

1. 汇总报告 Markdown：`D:\workbuddy 工作空间\小红书点赞分析_YYYY-MM-DD.md`（总览表 + 逐条详情）。
2. 飞书写入：用 `base +record-batch-create` **一次性**写全部新增。字段：标题、序号（按现有最大序号顺延）、作者、点赞数、链接、内容类型、分类（统一「小红书点赞分析」）、总结、话题标签、存档文件。
3. JSON 参数转义：**用 Python subprocess 调用 lark-cli** 传 JSON payload，避免 PowerShell 引号转义问题（示例见下）。PowerShell 脚本中**不要用 head 管道**。
   ```python
   import subprocess
   cmd = [LARK_CLI, "base", "+record-batch-create",
          "--base-token", "<FEISHU_BASE_TOKEN>",
          "--table-id", "<FEISHU_TABLE_ID>",
          "--json", payload_json, "--as", "user", "--format", "json"]
   subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
   ```

## 7. 收尾清理（关闭自己打开的标签页）

全部处理完成后，对比任务开始前浏览器已存在的标签页清单，**关闭本次任务自己打开/产生的标签页**：
- 小红书点点对话标签页（URL 含 `ai_chat` 或标题含「点点」）
- 本次拉取用的「赞过」profile 标签页（若是任务打开的）
- 任务期间新开的任何 `xiaohongshu.com` 页面

只保留任务前用户原有标签页。若用的是 `browser_tabs({action:'list'})`，先记下任务前 tab 列表，结束时按 index 关闭新增的。

## 8. 回复规范

回复只给出交付物文件路径和新增数量，不展示表格内容或详细说明。

---

## 常见坑与对策

| 坑 | 对策 |
|---|---|
| 点点输入框 type 不保留文字 | JS 原生 setter + input 事件注入 |
| 发送按钮点错（点到附件按钮） | 定位 `div.submit-button-wrapper` 用 JS `.click()` |
| 直接访问笔记 URL 反爬 404 / 点点 NOT_FOUND | 从「赞过」页卡片取带 xsec_token 的完整链接 |
| lark-cli `--format ndjson` 报错 | 用 `--format json` |
| PowerShell 传 JSON 参数被拆分 | 用 Python subprocess 调用 lark-cli |
| 逐帧快照慢 | 全程走 kimi-webbridge HTTP API (`127.0.0.1:10086/command`) 直接 evaluate |
| 固定长等待浪费 | 1~2s 短增量轮询 `.ai-message` 数量变化 |
| 每视频开新标签页浪费 | 复用同一点点对话标签页 |

## 关键历史参考（保留勿删）

- 成功写入记录：`D:\workbuddy 工作空间\_lark_records.json`（31 条旧记录快照）
- 2026-08-30 新增元数据：`D:\workbuddy 工作空间\_liked_list_20260830.json`
- 2026-08-30 xsec 链接：`D:\workbuddy 工作空间\_xsec_links_20260830.json`
- 点点 DOM 结构：`D:\workbuddy 工作空间\_xhs_dd_inputs.json`
