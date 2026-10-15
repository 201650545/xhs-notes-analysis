---
name: multi-store-sync-delete
description: 多数据源同步真删 SOP——dry-run 校验、分批删云端行、删本地文件与 JSON 键、双向孤儿终检。Use when 批量删除多端同步的笔记/记录或清退云端镜像残留行；勿用于删除单个无关文件。
---

# 多数据源同步真删

同一条记录同时存在于多个必须保持一致的存储（本地文件、JSON 台账/索引/映射、云端表格）时，按本流程删除。用户偏好是**真删不留存档**——禁止自建备份目录、.bak、"待删"暂存区；仅允许"案例提炼后删"（先把不依赖工具版本的内容写进长期资产文件，再删原文）。

## 0. 盘清有几个"端"

典型四端，按实际项目裁剪：

1. 正文/全文文件（如 `b_answers/<id>.txt`）
2. 台账/批次索引 JSON（如 `_routing.json` / `_knowledge_base.json`）
3. ID→云端 record_id 映射 JSON（如 `_lark_map.json`）
4. 云端表格行（CLI 删行）

派生端按需追加：由 JSON 生成的卡片 md（删除时标题要做文件名安全化）、附属标签/复核状态 JSON（死引用要清空）。

## 1. 权威集合原则（最高频踩坑点）

- 删除集从**权威数据文件的键集合**减去显式保留集算出：`DROP = set(json_keys) - KEEP`，不要手列 DROP
- 二审判决台导出的 `verdict_*.json` 是合法的人工判决来源：直接用其中 `drop` 数组为 DROP、`keep` 为 KEEP；`pending` 一律不动（即使导出的是 draft）；`demo:true` 的文件只用于演练，apply 前先核实批次真实性
- **禁止手抄任何 ID 到脚本**：终端输出和子代理报告可能丢字符（实测 24 位 ID 被抄成 23 位，`id in dict` 静默判假、不报错，直接留下孤儿）
- 需要喂给命令行的 record_id 列表，由脚本 dump 到 `%TEMP%` 临时 JSON，PowerShell 再读
- 每个 ID 长度固定（如 24 位 hex），dry-run 里断言长度与字符集

## 2. dry-run 先行（不加 --apply 不写任何东西）

脚本骨架（CONFIG 按项目填）：

```python
import json, os, sys
# CONFIG
ANS = r"<全文目录>"
LEDGER = r"<台账JSON>"   # {"rows":[{"id":...}]} 或 {id: {...}}
MAP    = r"<ID到云端rec映射JSON>"
KEEP = {"<显式保留ID>"}
APPLY = "--apply" in sys.argv

ledger = json.load(open(LEDGER, encoding="utf-8"))
keys = {r["id"] for r in ledger["rows"]}  # 按实际结构调整
assert KEEP <= keys, "保留集有不在台账的ID: " + str(KEEP - keys)
DROP = sorted(keys - KEEP)
lmap = json.load(open(MAP, encoding="utf-8"))

errs, recs = [], []
for nid in DROP:
    if not os.path.exists(os.path.join(ANS, nid + ".txt")): errs.append(f"全文缺 {nid}")
    rec = lmap.get(nid)
    if not rec or not str(rec).startswith("rec"): errs.append(f"映射缺/坏 {nid}: {rec}")
    else: recs.append(rec)
for nid in KEEP:
    if not os.path.exists(os.path.join(ANS, nid + ".txt")): errs.append(f"保留全文缺 {nid}")
assert not errs, "\n".join(errs)
assert len(recs) == len(set(recs)) == len(DROP)
json.dump(recs, open(os.path.join(os.environ["TEMP"], "del_recs.json"), "w"))
print(f"DROP={len(DROP)} rec={len(recs)} 校验通过" + ("" if APPLY else "（dry-run）"))
if not APPLY: sys.exit(0)
# ---- apply 段：删全文、pop 映射与台账、派生 md、写回 JSON ----
```

规则：

- dry-run 与 apply 是**同一个脚本**，只有 `--apply` 分支差别；先跑 dry-run 给用户/自己看数字
- 改任何管线脚本后先 `py_compile`；本机 Python 失效时用项目既定的 uv Python 绝对路径

## 3. 云端分批删行

- Windows 命令行有长度上限，**每批 ≤ 44 个 `--record-id`**，批数 = ceil(N/44)
- PowerShell 5.1 用 `;` 分隔语句，不用 `&&`
- 每批必须回显成功标志（如 `"ok": true`），失败立即停，不继续后续批

```powershell
$recs = Get-Content "$env:TEMP\del_recs.json" -Raw | ConvertFrom-Json
foreach($s in 0..([math]::Ceiling($recs.Count/44)-1)){
  $batch = $recs[($s*44)..([math]::Min(($s+1)*44-1,$recs.Count-1))]
  $a = @("base","+record-delete","--base-token","<token>","--table-id","<table>","--as","user","--yes")
  foreach($r in $batch){ $a += @("--record-id",$r) }
  $res = & "<cli路径>" @a
  if($res -notmatch '"ok"'){ throw "批次 $s 失败: $res" }
}
```

云端先删、本地后删：云端失败时本地还在，可重跑；顺序反了会失去映射无法定位云端行。

## 4. 本地 apply

- 删全文文件、`pop` 映射键与台账条目，JSON 用 `ensure_ascii=False, indent=2` 写回
- 派生 md 的文件名 = 标题剔除 `\ / : * ? " < > | # [ ] ^` 并 `strip().rstrip(".")`；缺失要显式报告（可能标题安全化规则变过）
- **批次结业**（整批清空）：rows 置 `[]`、count 置 0，并写 `archived_at` + 结业说明；**不要跑"扫描全文目录重建索引"的脚本**——会把幸存的保留笔记重新卷回已结业批次
- 附属 JSON（标签覆盖、复核队列）清空对已删 ID 的死引用

## 5. 终检（必做，四类孤儿）

1. 保留清单每个 ID 的全文存在
2. 映射键 ⊆ 全文文件；全文文件 ⊆ 映射键（双向集合相等）
3. 映射值全部合法（如 `rec` 前缀）
4. 重新拉云端全表：行数 == 映射条数，record_id 集合完全相等（用 CLI 的 ndjson 导出到临时文件解析，别信分页 markdown）

## 6. 收尾

- 删除含已删内容的临时导出文件（ndjson/manifest/rec 列表），不留档
- 同步统计口径到项目 README、筛选规范类文件、项目记忆（累计删除数、现存数、批次状态）
- 给用户的简报只给**关键数字 + 文件路径**，不展示被删内容明细
- 云端若存在本地各批次之外的历史残留行，**不在授权范围**，先报数字和构成，等用户明确授权再删，删前同样跑集合校验
