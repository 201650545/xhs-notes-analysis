$ErrorActionPreference = 'Stop'
$base = 'D:\Work\小红书点赞分析'
$data = Join-Path $base '_系统数据'
$enc = New-Object Text.UTF8Encoding($false)
$kb = [IO.File]::ReadAllText((Join-Path $data '_knowledge_base.json'), $enc) | ConvertFrom-Json
$noteRoot = Join-Path $base '知识库'
New-Item -ItemType Directory -Force -Path $noteRoot | Out-Null

# ---------- 时效复核状态（任务C 产物，可选） ----------
$reviewPath = Join-Path $data '_review_state.json'
$review = @{}
if (Test-Path $reviewPath) {
    $rs = [IO.File]::ReadAllText($reviewPath, $enc) | ConvertFrom-Json
    foreach ($p in $rs.notes.PSObject.Properties) { $review[$p.Name] = $p.Value }
}

function Q($s) {
    if ($null -eq $s) { return '""' }
    $t = ($s -replace "`r?`n", ' ') -replace '"', '\"'
    return '"' + $t + '"'
}

$used = @{}
$index = @()

foreach ($r in $kb.rows) {
    $cat = $r.category
    $dir = Join-Path $noteRoot $cat
    New-Item -ItemType Directory -Force -Path $dir | Out-Null

    $safe = ($r.title -replace '[\\/:*?"<>|#\[\]\^]', '').Trim().TrimEnd('.')
    if ([string]::IsNullOrWhiteSpace($safe)) { $safe = $r.id }
    if ($used.ContainsKey($safe)) { $safe = "$safe ($($r.id))" }
    $used[$safe] = 1

    $rawPath = Join-Path "$base\b_answers" $r.file
    $raw = [IO.File]::ReadAllText($rawPath, $enc)
    $lines = $raw -split "`r?`n"
    if ($lines.Count -gt 3 -and $lines[0].StartsWith('#') -and $lines[2].StartsWith('# http')) {
        $body = ($lines[3..($lines.Count - 1)] -join "`r`n").Trim()
    } else {
        $body = $raw.Trim()
    }

    $tagList = @()
    if ($r.tags) { foreach ($t in $r.tags) { $tagList += (($t -replace '[#\[\],]', '') -replace '\s+', '-') } }
    $tagBlock = if ($tagList.Count -gt 0) { (($tagList | ForEach-Object { '  - ' + (Q $_) }) -join "`r`n") } else { '  []' }
    $tagYaml = "主题标签:" + "`r`n" + $tagBlock + "`r`n" + "tags:" + "`r`n" + $tagBlock

    # ---------- 复核层 ----------
    $rv = $review[$r.id]
    $rvStatus = if ($rv) { [string]$rv.status } else { '' }
    $rvHist = @()
    if ($rv -and $rv.history) { $rvHist = @($rv.history) }
    $stale = ($rvStatus -eq '已升级' -or $rvStatus -eq '已失效')
    $latest = if ($rvHist.Count -gt 0) { $rvHist[0] } else { $null }

    $md = @()
    $md += '---'
    $md += '标题: ' + (Q $r.title)
    $md += '笔记ID: ' + (Q $r.id)
    $md += '大类: ' + (Q $cat)
    $md += '内容类型: ' + (Q $r.type)
    $md += '作者: ' + (Q $r.author)
    $md += $tagYaml
    $md += '一句话总结: ' + (Q $(if ($stale -and $latest -and $rvStatus -eq '已升级' -and $latest.new_summary) { $latest.new_summary } else { $r.summary }))
    $md += '原链接: ' + (Q $r.url)
    $md += '分析版本: "v3-分区版"'
    $md += '分析日期: 2026-09-23'
    $md += '全文字数: ' + $r.full_len
    if ($rv) {
        $md += '时效分级: ' + (Q $(if ($rv.tier -eq 'sensitive') { '高（福利/版本类）' } else { '低（长期有效类）' }))
        if ($rvStatus -and $rvStatus -ne '待复核') { $md += '信息状态: ' + (Q $rvStatus) }
        $md += '复核日期: ' + [string]$rv.next_review
        if ($rv.checked_at) { $md += '最近核实: ' + [string]$rv.checked_at }
    }
    $md += '---'
    $md += ''
    $md += '# ' + $r.title
    $md += ''
    # 状态警示条（置顶）
    if ($latest) {
        switch ($rvStatus) {
            '已升级' {
                $md += '> [!tip] ⬆️ 信息已更新（' + $latest.date + ' 联网核实）'
                $head = if ($latest.new_summary) { $latest.new_summary } else { $latest.facts }
                $md += '> ' + ($head -replace "`r?`n", ' ')
            }
            '已失效' {
                $md += '> [!danger] ❌ 此信息已失效（' + $latest.date + ' 联网核实）'
                $md += '> ' + ($latest.facts -replace "`r?`n", ' ')
            }
            '待人工核实' {
                $md += '> [!warning] ❓ 自动核实未成功（' + $latest.date + '），需人工确认'
            }
            '有效' {
                $md += '> [!success] ✅ ' + $latest.date + ' 联网核实仍有效'
            }
        }
        $md += ''
    }
    $md += '> [!abstract] 一句话总结'
    $md += '> ' + ($r.summary -replace "`r?`n", ' ')
    $md += ''
    $md += '- **大类**：' + $cat
    $md += '- **类型 / 作者**：' + $r.type + ' / ' + $r.author
    $md += '- **原链接**：[小红书原文](' + $r.url + ')'
    $md += '- **笔记ID**：`' + $r.id + '`　**分析版本**：v3-分区版'
    $md += ''

    # 历次联网复核结论（新结论在前）
    if ($rvHist.Count -gt 0) {
        $md += '## 时效更新（联网复核）'
        $md += ''
        foreach ($h in $rvHist) {
            $badge = switch ($h.verdict) { '有效' { '✅ 有效' } '已失效' { '❌ 已失效' } '已升级' { '⬆️ 已升级' } default { '❓ 无法核实' } }
            $md += '### ' + $h.date + ' · ' + $badge
            $md += ''
            if ($h.facts) { $md += '- **现状**：' + ($h.facts -replace "`r?`n", ' ') }
            if ($h.changes -and $h.changes -ne '无') { $md += '- **变化**：' + ($h.changes -replace "`r?`n", ' ') }
            if ($h.new_summary) { $md += '- **更新后总结**：' + ($h.new_summary -replace "`r?`n", ' ') }
            if ($h.sources) { $md += '- **来源**：' + ($h.sources -replace "`r?`n", ' ') }
            $md += ''
        }
    }

    # 原始分析：失效/升级后折叠保留（内容层事实快照不删除）
    if ($stale) {
        $md += '## 原始分析（已折叠存档）'
        $md += ''
        $md += '> [!quote]- 2026-09-23 原始分析（可能已过时，以顶部「时效更新」为准）'
        foreach ($bl in ($body -split "`r?`n")) { $md += '> ' + $bl }
        $md += ''
    } else {
        $md += '## 深度分析全文'
        $md += ''
        $md += $body
        $md += ''
    }
    $md += '---'
    $md += ''
    $tail = '> 所属总览：[[知识库总览]]　·　分类：' + $cat + '　·　笔记ID：`' + $r.id + '`'
    if ($rv -and $rvStatus -and $rvStatus -ne '待复核') { $tail += '　·　复核状态：' + $rvStatus }
    $md += $tail
    $md += ''

    $outPath = Join-Path $dir ($safe + '.md')
    [IO.File]::WriteAllText($outPath, ($md -join "`r`n"), $enc)

    $index += [PSCustomObject]@{
        cat   = $cat
        title = $r.title
        path  = '知识库/' + $cat + '/' + $safe
        type  = $r.type
        tags  = ($r.tags -join '、')
        sum   = $r.summary
    }
}

# ---------- 总览笔记 ----------
$catOrder = @('A工具资源', 'B技术实操', 'C创作设计', 'D搞钱变现', 'E学习成长', 'F视野观点', 'G生活其他')
$counts = @{}
foreach ($c in $catOrder) { $counts[$c] = ($index | Where-Object { $_.cat -eq $c }).Count }

$o = @()
$o += '---'
$o += '标题: "小红书点赞知识库总览"'
$o += '类型: "总览"'
$o += '笔记数: ' + $index.Count
$o += '生成日期: 2026-09-24'
$o += '---'
$o += ''
$o += '# 小红书点赞知识库总览'
$o += ''
$o += ('共 **' + $index.Count + '** 篇 v3 深度分析，按七大类组织。笔记在 `知识库\<大类>\` 下，每篇都带 YAML 属性（大类/主题标签/一句话总结/原链接）。')
$o += ''
$o += '> **精选保留库**：逐篇筛选后的长期资产层（保留笔记 + 脱离工具版本的提炼案例 + 一审记录），与本页普通库互不重复。'
$o += '> 入口 → [[精选保留库]]；通用方法见 [[保留_案例与方法]]；筛选过程见 [[一审预判_2026-09-28]]。'
$o += ''
$o += '## 一、大类分布'
$o += ''
$o += '```mermaid'
$o += 'pie showData'
$o += '    title 99 篇点赞笔记的大类分布'
foreach ($c in $catOrder) { $o += ('    "' + $c + '" : ' + $counts[$c]) }
$o += '```'
$o += ''
$o += '## 二、标签热度'
$o += ''
$tagCount = @{}
foreach ($i in $index) {
    if ([string]::IsNullOrWhiteSpace($i.tags)) { continue }
    foreach ($t in ($i.tags -split '、')) {
        if ([string]::IsNullOrWhiteSpace($t)) { continue }
        if ($tagCount.ContainsKey($t)) { $tagCount[$t]++ } else { $tagCount[$t] = 1 }
    }
}
$top = $tagCount.GetEnumerator() | Sort-Object -Property Value -Descending | Select-Object -First 15
$o += '```mermaid'
$o += 'xychart-beta'
$o += '    title "出现频次 Top 15 的主题标签"'
$o += '    x-axis [' + (($top | ForEach-Object { '"' + $_.Key + '"' }) -join ', ') + ']'
$o += '    y-axis "篇数" 0-' + ([Math]::Ceiling(($top | Select-Object -First 1).Value / 5) * 5)
$o += '    bar [' + (($top | ForEach-Object { $_.Value }) -join ', ') + ']'
$o += '```'
$o += ''
$o += '## 三、七大类索引'
$o += ''
foreach ($c in $catOrder) {
    $items = $index | Where-Object { $_.cat -eq $c }
    $o += ('### ' + $c + '（' + $items.Count + ' 篇）')
    $o += ''
    foreach ($i in $items) {
        $o += ('- [[' + $i.path + '|' + $i.title + ']] — ' + $i.sum)
    }
    $o += ''
}

$outDir = Join-Path $base '00_项目驾驶舱_可视化中心'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
[IO.File]::WriteAllText((Join-Path $outDir '知识库总览.md'), ($o -join "`r`n"), $enc)

# ---------- Bases 看板 ----------
$b = @()
$b += 'filters:'
$b += '  and:'
$b += '    - file.inFolder("小红书点赞分析/知识库")'
$b += ''
$b += 'properties:'
$b += '  标题:'
$b += '    displayName: 标题'
$b += '  大类:'
$b += '    displayName: 大类'
$b += '  内容类型:'
$b += '    displayName: 类型'
$b += '  作者:'
$b += '    displayName: 作者'
$b += '  主题标签:'
$b += '    displayName: 标签'
$b += '  一句话总结:'
$b += '    displayName: 一句话总结'
$b += '  分析日期:'
$b += '    displayName: 分析日期'
$b += '  时效分级:'
$b += '    displayName: 时效分级'
$b += '  信息状态:'
$b += '    displayName: 信息状态'
$b += '  复核日期:'
$b += '    displayName: 复核日期'
$b += '  最近核实:'
$b += '    displayName: 最近核实'
$b += ''
$b += 'views:'
$b += '  - type: table'
$b += '    name: 全部笔记'
$b += '    order:'
$b += '      - file.name'
$b += '      - 大类'
$b += '      - 内容类型'
$b += '      - 作者'
$b += '      - 主题标签'
$b += '      - 一句话总结'
$b += '    sort:'
$b += '      - property: 大类'
$b += '        direction: ASC'
$b += '  - type: cards'
$b += '    name: 卡片视图'
$b += '    order:'
$b += '      - file.name'
$b += '      - 一句话总结'
$b += '      - 大类'
$b += '      - 主题标签'
$b += '  - type: table'
$b += '    name: 视频类'
$b += '    filters:'
$b += '      and:'
$b += '        - 内容类型 == "视频"'
$b += '    order:'
$b += '      - file.name'
$b += '      - 大类'
$b += '      - 作者'
$b += '      - 一句话总结'
$b += '  - type: table'
$b += '    name: 按大类分组'
$b += '    groupBy:'
$b += '      property: 大类'
$b += '      direction: ASC'
$b += '    order:'
$b += '      - file.name'
$b += '      - 一句话总结'
$b += '      - 主题标签'
$b += '      - 作者'
$b += '      - 内容类型'
$b += '  - type: table'
$b += '    name: ⏰ 待复核'
$b += '    filters:'
$b += '      and:'
$b += '        - 复核日期 <= today()'
$b += '    order:'
$b += '      - file.name'
$b += '      - 时效分级'
$b += '      - 信息状态'
$b += '      - 复核日期'
$b += '      - 大类'
$b += '      - 一句话总结'
$b += '    sort:'
$b += '      - property: 复核日期'
$b += '        direction: ASC'
$b += '  - type: table'
$b += '    name: ⚠ 失效与升级'
$b += '    filters:'
$b += '      or:'
$b += '        - 信息状态 == "已失效"'
$b += '        - 信息状态 == "已升级"'
$b += '        - 信息状态 == "待人工核实"'
$b += '    order:'
$b += '      - file.name'
$b += '      - 信息状态'
$b += '      - 最近核实'
$b += '      - 大类'
$b += '      - 一句话总结'
[IO.File]::WriteAllText((Join-Path $outDir '知识库看板.base'), ($b -join "`r`n"), $enc)

'生成完成'
'笔记数: ' + $index.Count
'大类分布:'
foreach ($c in $catOrder) { '  ' + $c + ' = ' + $counts[$c] }
'总览: ' + (Join-Path $outDir '知识库总览.md')
'看板: ' + (Join-Path $outDir '知识库看板.base')
