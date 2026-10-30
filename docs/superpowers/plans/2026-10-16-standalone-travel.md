# Standalone Travel Implementation Plan

**Goal:** 仅为 TRAVEL 增加跨流程独立调用，成功返回原台词等待，正常轮到 TRAVEL 时保持原流程。

**Architecture:** `line_match.py` 提供严格的独立入口匹配；`queen_state.py` 优先匹配当前节点，仅在未命中且允许等待指令时尝试 TRAVEL，复用其 steps 并保留原 state。`main_queen.py` 的成功后 ding 调度无需改变。

**Tech Stack:** Python、unittest、既有 QueenState/QueenActions。

- [x] 新增无硬件测试，覆盖明确台词、拒绝样本、返回原节点、正常推进、忙时/故障与提示轮次；运行并确认旧程序失败。
- [x] 实现严格匹配和独立步骤执行，复用既有串口与播放器，不新增动作队列。
- [x] 运行新增测试、全部回归、配置检查及完整五幕纯模拟。
- [x] 更新 README 与使用指南，说明触发范围、正常/跨流程差异及误触发限制；本地提交，不部署、不推送。
