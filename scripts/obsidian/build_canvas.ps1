$ErrorActionPreference = 'Stop'
$base = '<PROJECT_DIR>'
$vault = 'D:\Work'
$enc = New-Object Text.UTF8Encoding($false)
$data = Join-Path $base '_系统数据'
$kb = [IO.File]::ReadAllText((Join-Path $data '_knowledge_base.json'), $enc) | ConvertFrom-Json

$catOrder = @('A工具资源','B技术实操','C创作设计','D搞钱变现','E学习成长','F视野观点','G生活其他')
$catColor = @{
    'A工具资源' = '5'   # 青
    'B技术实操' = '1'   # 红
    'C创作设计' = '6'   # 紫
    'D搞钱变现' = '4'   # 绿
    'E学习成长' = '2'   # 橙
    'F视野观点' = '3'   # 黄
    'G生活其他' = '0'   # 灰
}

# ---------- 复现笔记文件名清洗 + 全局去重（与 xhs_build_notes.ps1 一致） ----------
$used = @{}
$rows = @()
foreach ($r in $kb.rows) {
    $safe = ($r.title -replace '[\\/:*?"<>|#\[\]\^]', '').Trim().TrimEnd('.')
    if ([string]::IsNullOrWhiteSpace($safe)) { $safe = $r.id }
    if ($used.ContainsKey($safe)) { $safe = "$safe ($($r.id))" }
    $used[$safe] = 1
    $rows += [pscustomobject]@{ r = $r; safe = $safe }
}

# ---------- 标签统计（清洗规则同笔记生成） ----------
function CleanTag($t) { return (($t -replace '[#\[\],]', '') -replace '\s+', '-') }
$tagCount = @{}
foreach ($x in $rows) {
    if (-not $x.r.tags) { continue }
    foreach ($t in $x.r.tags) {
        $c = CleanTag $t
        if ([string]::IsNullOrWhiteSpace($c)) { continue }
        if ($tagCount.ContainsKey($c)) { $tagCount[$c]++ } else { $tagCount[$c] = 1 }
    }
}
$topTags = @($tagCount.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 6)
$tagColor = @{}
for ($i = 0; $i -lt $topTags.Count; $i++) { $tagColor[$topTags[$i].Key] = [string](($i % 6) + 1) }

$nodes = New-Object System.Collections.ArrayList
$edges = New-Object System.Collections.ArrayList
$ei = 0

# ---------- 顶部：说明 + 两个入口 ----------
$intro = @"
## 🗺️ 点赞知识库全景

**99** 篇 v3 深度分析 · 按七大类**彩色分组** · 卡片即笔记

- **双击卡片** → 打开笔记全文（含标签、原链接、深度分析）
- **拖拽卡片/缩放画布** → 布局改动自动保存
- 右侧 **Top6 高频标签**为锚点，同色连线把跨大类的笔记串起来
- 表格/筛选/编辑属性请走 [[知识库看板]]，图表索引走 [[知识库总览]]
"@
[void]$nodes.Add([ordered]@{ id='intro'; type='text'; x=0; y=0; width=560; height=200; color='0'; text=$intro })
[void]$nodes.Add([ordered]@{ id='entry-overview'; type='file'; x=600; y=0; width=380; height=200
    file='小红书点赞分析/00_项目驾驶舱_可视化中心/知识库总览.md' })
[void]$nodes.Add([ordered]@{ id='entry-base'; type='file'; x=1020; y=0; width=380; height=200
    file='小红书点赞分析/00_项目驾驶舱_可视化中心/知识库看板.base' })

# ---------- 七大类分组 + 笔记卡片 ----------
$colX = @(0, 440, 880)
$topY = 260
$rowH = @{}
for ($row = 0; $row -lt 3; $row++) {
    $maxH = 0
    for ($col = 0; $col -lt 3; $col++) {
        $idx = $row * 3 + $col
        if ($idx -ge $catOrder.Count) { continue }
        $h = 50 + ((@($rows | Where-Object { $_.r.category -eq $catOrder[$idx] })).Count) * 76 + 10
        if ($h -gt $maxH) { $maxH = $h }
    }
    $rowH[$row] = $maxH
}
$rowY = @{}
$rowY[0] = $topY
$rowY[1] = $topY + $rowH[0] + 80
$rowY[2] = $topY + $rowH[0] + 80 + $rowH[1] + 80

for ($idx = 0; $idx -lt $catOrder.Count; $idx++) {
    $cat = $catOrder[$idx]
    $row = [Math]::Floor($idx / 3); $col = $idx % 3
    $gx = $colX[$col]; $gy = $rowY[$row]
    $items = @($rows | Where-Object { $_.r.category -eq $cat })
    $gh = 50 + $items.Count * 76 + 10

    [void]$nodes.Add([ordered]@{ id="grp-$cat"; type='group'; x=$gx; y=$gy; width=400; height=$gh
        label="$cat（$($items.Count)）"; color=$catColor[$cat] })

    $iy = $gy + 50
    foreach ($x in $items) {
        $rel = '小红书点赞分析/知识库/' + $cat + '/' + $x.safe + '.md'
        [void]$nodes.Add([ordered]@{ id=$x.r.id; type='file'; x=($gx+20); y=$iy; width=360; height=64; file=$rel })
        $iy += 76
    }
}

# ---------- 右侧：Top6 标签锚点 + 星形连线 ----------
$ax = 1360; $ay = $topY
foreach ($tg in $topTags) {
    $tag = $tg.Key; $cnt = $tg.Value
    [void]$nodes.Add([ordered]@{ id="tag-$tag"; type='text'; x=$ax; y=$ay; width=260; height=60
        color=$tagColor[$tag]; text="#### #$tag  ·  $cnt 篇" })
    foreach ($x in $rows) {
        if (-not $x.r.tags) { continue }
        $hit = $false
        foreach ($t in $x.r.tags) { if ((CleanTag $t) -eq $tag) { $hit = $true; break } }
        if ($hit) {
            [void]$edges.Add([ordered]@{ id="e-$ei"; fromNode=$x.r.id; fromSide='right'
                toNode="tag-$tag"; toSide='left'; color=$tagColor[$tag] })
            $ei++
        }
    }
    $ay += 100
}

$canvas = [ordered]@{ nodes = $nodes; edges = $edges }
$json = $canvas | ConvertTo-Json -Depth 8
$out = Join-Path $base '00_项目驾驶舱_可视化中心\知识库全景.canvas'
[IO.File]::WriteAllText($out, $json, $enc)

# ---------- 校验 ----------
$check = [IO.File]::ReadAllText($out, $enc) | ConvertFrom-Json
$fileNodes = @($check.nodes | Where-Object { $_.type -eq 'file' })
$missing = @()
foreach ($n in $fileNodes) {
    $abs = Join-Path $vault ($n.file -replace '/', '\')
    if (-not (Test-Path $abs)) { $missing += $n.file }
}
'生成完成: ' + $out
'节点总数: ' + $check.nodes.Count + '（file=' + $fileNodes.Count + '，group=7，text=' + (@($check.nodes | Where-Object { $_.type -eq 'text' })).Count + '）'
'连线数: ' + $check.edges.Count
'缺失文件路径: ' + $missing.Count
$missing | Select-Object -First 5 | ForEach-Object { '  MISSING: ' + $_ }
