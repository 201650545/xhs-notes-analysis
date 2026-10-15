#!/usr/bin/env node
/*
 * quark_upload_worker.js —— 夸克上传的 detached 执行体（2026-10-03 新增）
 *
 * 为什么存在：backup_quark.ps1 原先用 Start-Process -Wait 直接跑上传，
 * 父脚本被系统打断时上传同步被杀，连续 4 天镜像停在 "upload start"。
 * 本 worker 以独立进程启动，生命周期不受父脚本影响；跑完把结果写成
 * result_<tag>.json，由 upload_watchdog.ps1 读取判定成败。
 *
 * 幂等：夸克按内容哈希秒传，未变文件不消耗流量，中断后下次自动续传。
 */
'use strict';
const fs = require('fs');
const { spawnSync } = require('child_process');

// 2026-10-08 修复：payload 改从 pending 文件读取。
// 根因：原实现把含大量双引号的 JSON 作为命令行参数传入，
// PowerShell 5.1 Start-Process 的参数重引用会把 JSON 打碎，
// JSON.parse 在第一行就抛异常 → worker 秒崩且来不及写 result，
// 连续 4 天（10/4-10/7）镜像静默断链。
// 现约定：argv[2] 是 pending_<tag>.json 文件路径（无引号风险）；
// 兼容兜底：若以 { 开头则仍按内联 JSON 解析。
let payload;
const argIn = process.argv[2] || '';
try {
  // 剥离 BOM：PS5.1 Set-Content -Encoding UTF8 会写 \uFEFF 头，JSON.parse 不认
  const raw = argIn.startsWith('{') ? argIn : fs.readFileSync(argIn, 'utf8').replace(/^\uFEFF/, '');
  payload = JSON.parse(raw);
} catch (e) {
  // 读不到/解析不了也要留痕，否则又是无声死亡
  try {
    fs.writeFileSync(process.argv[3] || 'worker_boot_error.json', JSON.stringify({ ok: false, exitCode: -1, failedItems: 0, finishedAt: new Date().toISOString(), tail: ['payload load failed: ' + (e && e.message), 'argv[2]=' + argIn] }, null, 2), 'utf8');
  } catch (_) {}
  process.exit(1);
}
const { cli, node, path, fid, sid, resultFile, tag } = payload;

function done(exitCode, lines) {
  const res = (lines || []).find((l) => l.includes('"type":"result"')) || '';
  const failN = (lines || []).filter(
    (l) => l.includes('"type":"list"') && !l.includes('"code":0')
  ).length;
  let ok = false;
  try {
    const j = JSON.parse(res);
    ok = exitCode === 0 && j.code === 0;
  } catch (_) {
    ok = false;
  }
  fs.writeFileSync(
    resultFile,
    JSON.stringify(
      { tag, ok, exitCode, failedItems: failN, finishedAt: new Date().toISOString(), tail: (lines || []).slice(-5) },
      null,
      2
    ),
    'utf8'
  );
  process.exit(ok ? 0 : 1);
}

let r;
try {
  r = spawnSync(node, [cli, 'upload', path, '--parent-fid', fid, '--session-id', sid], {
    stdio: ['ignore', 'pipe', 'pipe'],
    maxBuffer: 64 * 1024 * 1024,
  });
} catch (e) {
  done(1, ['spawn failed: ' + (e && e.message)]);
}

const out = (r.stdout || '').toString();
const err = (r.stderr || '').toString();
const lines = (out + (err ? '\n' + err : ''))
  .split('\n')
  .map((l) => l.trim())
  .filter(Boolean);

done(r.status === null ? 1 : r.status, lines);