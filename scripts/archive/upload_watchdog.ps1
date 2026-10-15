# 2026-10-03 新增：detached 上传的成败判定器
# 背景：backup_quark.ps1 改成"发起即返回"后，任务本身不再知道上传有没有成功。
# 本脚本读 worker 留下的 result_<tag>.json，把结论写进当天日志，
# 并清理 pending 标记。判定走文件而非进程 cmdline（NSSM/WMI 盲区铁律）。
param()

$ErrorActionPreference = 'SilentlyContinue'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir    = Join-Path $scriptDir 'logs'
$todayLog  = Join-Path $logDir ((Get-Date -Format 'yyyy-MM-dd') -replace '^', 'backup_') + '.txt'

if (-not (Test-Path $logDir)) { exit 0 }

function Say($m) {
  $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $m
  Add-Content -LiteralPath $todayLog -Value $line -Encoding UTF8
}

# 只处理 1 天前的 pending：worker 正常几分钟内就结束，跨天说明真卡住了
$cutoff = (Get-Date).AddHours(-23)
foreach ($pf in Get-ChildItem $logDir -Filter 'pending_*.json' -ErrorAction SilentlyContinue) {
  $tag = $pf.BaseName -replace '^pending_', ''
  $rf  = Join-Path $logDir ("result_{0}.json" -f $tag)

  if (-not (Test-Path $rf)) {
    # 结果文件还没出现
    if ($pf.LastWriteTime -lt $cutoff) {
      Say ("upload STUCK [{0}] 已超过 23 小时仍无结果文件，疑似进程被杀；下次运行会自动续传（内容哈希秒传，不重复消耗流量）" -f $tag)
      Remove-Item $pf.FullName -Force -ErrorAction SilentlyContinue
    }
    continue
  }

  try {
    $r = Get-Content $rf -Raw -Encoding UTF8 | ConvertFrom-Json
  } catch {
    Say ("upload UNREADABLE [{0}] 结果文件解析失败：{1}" -f $tag, $_)
    Remove-Item $pf.FullName, $rf -Force -ErrorAction SilentlyContinue
    continue
  }

  if ($r.ok) {
    Say ("upload ok [{0}] 失败条目={1} 完成于 {2}" -f $tag, $r.failedItems, $r.finishedAt)
  } else {
    Say ("upload FAIL [{0}] 退出码={1} 失败条目={2} 完成于 {3}（可续传，下次自动重试）" -f $tag, $r.exitCode, $r.failedItems, $r.finishedAt)
  }
  Remove-Item $pf.FullName, $rf -Force -ErrorAction SilentlyContinue
}