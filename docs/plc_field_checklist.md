# PLC 真机联调 Checklist（#33）

> **原则：现场尽量只改 JSON / 勾选 UI 配置，少改代码。**  
> 开发默认 `plc.simulate=true`；真机联调才切到 `enabled=true` + `simulate=false`。  
> INT16 映射以 `SignalAdapter`（D-008）为准，禁止自造写值表。

示例配置：[`configs/config.plc.example.json`](../configs/config.plc.example.json)  
UI：菜单 **PLC → PLC 配置…**（#32）亦可改同一套字段并 `save_config`。

---

## 0. 联调前准备

| # | 检查项 | 期望 / 备注 | ☐ |
|---|--------|-------------|---|
| 0.1 | Jetson 与 PLC 同网段可 ping | `ping <plc.ip>` 通 | ☐ |
| 0.2 | 已安装 `python-snap7`（≥3.0） | `python -c "import snap7; print(snap7.__version__)"` | ☐ |
| 0.3 | 复制示例配置到现场路径 | `cp configs/config.plc.example.json configs/config.json`（或现场命名）后**只改 JSON** | ☐ |
| 0.4 | 产线 PLC 程序已分配结果 INT16 地址 | 记下 DB 号、字节偏移；与 `db_number` / `result_offset` 一致 | ☐ |
| 0.5 | 确认信号语义（本系统） | 写 PLC INT16：`0` 安全 / `1` SLOW / `2` STOP / `-1` 故障；**勿**把旧版 `result_code` 直写 | ☐ |

---

## 1. 配置开关（必须）

在 `config.json` 的 `"plc"` 段（或 UI 对话框）设置：

```json
"enabled": true,
"simulate": false
```

| 组合 | 行为 |
|------|------|
| `simulate=true`（任意 `enabled`） | **不连** snap7，仅仿真 / 拟写入展示 |
| `enabled=false` | **不连** snap7 |
| `enabled=true` **且** `simulate=false` | 走真机 `Snap7Backend` |

现场联调失败时：先改回 `simulate=true` 确认检测/UI 正常，再单独排查 PLC。

---

## 2. 连接参数（按现场填）

| 字段 | 含义 | 常见默认 | 现场填写 |
|------|------|----------|----------|
| `ip` | PLC IP | `192.168.0.10` | _______________ |
| `rack` | 机架 | `0`（S7-1200/1500 多为 0） | _______________ |
| `slot` | 槽位 | `1`（S7-1200/1500 多为 1） | _______________ |
| `db_number` | 结果所在 DB 号 | `1` | _______________ |
| `result_offset` | INT16 起始**字节**偏移 | `0` | _______________ |
| `mode` | `command` / `block` | `command` | _______________ |
| `watchdog_ms` | 看门狗超时（ms） | `3000` | _______________ |
| `offline_hold` | 断线是否保持末值语义 | `true` | _______________ |
| `verify_readback` | 写后读回校验 | `true`（联调建议开） | _______________ |

> 字节序：本系统写 **大端 INT16**（`>h`）。与 PLC 侧 BOOL/WORD 布局对齐时注意偏移为偶数字节。

---

## 3. S7 PUT/GET（TIA 侧）

S7-1200/1500 默认可能关闭外部 PUT/GET，snap7 直读写 DB 会失败。

| # | 检查项 | 操作 | ☐ |
|---|--------|------|---|
| 3.1 | 允许来自远程对象的 PUT/GET | TIA → PLC 属性 → 保护与安全 → **允许来自远程伙伴的 PUT/GET 通信访问**（或等价选项） | ☐ |
| 3.2 | 下载并重启 PLC | 改完保护设置后编译下载 | ☐ |
| 3.3 | 防火墙 / ACL | 工控网允许 Jetson ↔ PLC TCP **102** | ☐ |

若现场策略禁止 PUT/GET，需另开 S7CommPlus / OPC 等路径——**超出本 Bootstrap 示例**，先记录并升级决策，勿在现场硬改 gateway。

---

## 4. 联调步骤（少改代码）

1. **仿真冒烟**：`simulate=true`，启动 UI，确认状态栏「拟写入」随 signal 变化（与 SignalAdapter 一致）。
2. **改 JSON / UI**：填好 §2 字段，设 `enabled=true`、`simulate=false`，保存。
3. **启动检测**：全部开始；观察状态栏通讯从「仿真」切到「真机」。
4. **写后读回**：`verify_readback=true` 时，Gateway 写 INT16 后读同一偏移比对；日志无连续读回失败。
5. **人为触发**：无人 → 期望写 `0`；SLOW 确认 → `1`；STOP 确认 → `2`；相机/模型故障 → `-1`。
6. **PLC 侧监视**：用 TIA 在线监控表看对应 DB.DBW（或 DBB 对）是否与 Jetson 一致。
7. **断线恢复**：拔网线 → 看门狗 / OFFLINE 行为；恢复后自动重连（独立进程 Gateway）。
8. **回退**：联调结束若暂不投产，改回 `simulate=true` 或 `enabled=false`，避免误写产线。

---

## 5. 看门狗与断线

| 项 | 说明 |
|----|------|
| `watchdog_ms` | 轮询 / 连续失败超时阈值；现场可先 3000，抖动大再放宽 |
| `offline_hold` | `true`：断线保持已激活语义（UI 标 OFFLINE·HOLD）；`false`：按产品约定降级 |
| 进程隔离 | 真机写经 `PlcProcessGateway` 子进程，**勿**在 UI 线程直接 `snap7.connect` |

---

## 6. 常见失败对照

| 现象 | 优先检查 |
|------|----------|
| 一直仿真、不连 PLC | `simulate` 仍为 `true` 或 `enabled=false` |
| `connect` 超时 / 拒绝 | IP、机架/槽、网线、TCP 102、防火墙 |
| 连接成功但读写失败 | PUT/GET 未开、DB 号/偏移错误、DB 未下载到 PLC |
| 读回值与写入不一致 | 偏移冲突（其它程序在写）、字节序/长度、`verify_readback` 日志 |
| 数值「像旧版」 | 是否绕过 SignalAdapter；旧 `result_code` 禁止直写 |
| ImportError snap7 | 现场环境未装 `python-snap7` |

---

## 7. 验收签字（现场）

| 项 | 结果 | 签字 / 日期 |
|----|------|-------------|
| 仅改 JSON/UI 即可连上 | ☐ 通过 ☐ 失败 | |
| STOP/SLOW/安全/故障 INT16 与监控表一致 | ☐ 通过 ☐ 失败 | |
| 写后读回无持续失败 | ☐ 通过 ☐ 失败 | |
| 断线与恢复可接受 | ☐ 通过 ☐ 失败 | |

**M5 说明**：PLC 真机验收 = #26（snap7）+ #32（配置窗）+ 本清单（#33）；开发 CI 只验仿真 + mock。
