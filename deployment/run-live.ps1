# 本机可视化联调入口。Ctrl+C 中断远程演出调度；已下发动作需由下位机停止。
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$Host.UI.RawUI.WindowTitle = '蜂后机器人 · 树莓派实时运行'
Write-Host '源码：F:\agent ws\dancing_robot\pi\queen_robot\main_queen.py' -ForegroundColor Cyan
Write-Host '剧本：F:\agent ws\dancing_robot\pi\queen_robot\queen_dialog.json' -ForegroundColor Cyan
Write-Host '真实演出：C270 麦克风；按剧本台词触发配音和动作。' -ForegroundColor Yellow
Write-Host '下方为树莓派程序的实际输出；说“蜂后”唤醒。' -ForegroundColor Green
& ssh -tt -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 pi@10.181.140.207 'cd /home/pi/queen_robot && mkdir -p deployment_logs/2026-10-02 && set -o pipefail && bash scripts/pi_run.sh 2>&1 | tee -a deployment_logs/2026-10-02/live.log'
Write-Host "远程程序已退出，SSH 退出码：$LASTEXITCODE" -ForegroundColor Yellow
