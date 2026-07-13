# Jetson Bootstrap 手测记录

> 对照 [validation_phases.md §1.3](../validation_phases.md)。复制本模板为 `jetson_bootstrap_YYYYMMDD.md` 填写。

| 字段 | 值 |
|------|-----|
| 日期 | |
| Jetson / JetPack | |
| engine | `models/stock/yolov8s.engine` |
| 输入 | `data/sample_videos/demo.mp4` / USB |
| config | |
| 测试人 | |

## §1.3 清单

| # | 能力 | 结果 (✅/❌) | 备注 |
|---|------|-------------|------|
| 1 | 监视预览（≥1 路，~15FPS） | | |
| 2 | slow/stop 划区编辑 + 保存 config | | |
| 3 | 运行 / 停止 | | |
| 4 | 信号显示 `-1/0/1/2` | | |
| 5 | 报警指示（人进 STOP → signal/拟写入） | | |
| 6 | 视频文件源 | | |
| 7 | STOCK · 集成测试 标识 | | |
| 8 | USB（建议） | | 无设备可跳过 |
| 9 | PLC 仿真拟写入 | | 与 SignalAdapter 一致 |
| 10 | PLC 真机 | | Bootstrap 后期 |
| 11 | 报警录像（建议） | | #21 API 已有，接线属 Wave2 |

## 操作步骤摘要

1. `DISPLAY=:0` 启动：`python3 app/main.py --config configs/config.jetson.json --engine models/stock/yolov8s.engine`
2. 监控 Tab → 编辑 SLOW/STOP → 保存当前工位划区
3. 全部开始 → 观察预览、状态栏 signal / PLC 拟写入
4. 人进 STOP 区时期望 signal→2、拟写入→2

## 性能与问题

| 项 | 记录 |
|----|------|
| 预览 FPS | |
| infer_ms | |
| 问题列表 | |

## 结论

- [ ] **M-Bootstrap 达成**（视频→划区→运行→报警/信号正确；config 可保存）
- [ ] 未达成（原因：）
