# 场内冻结测试集（`jetson_update/testset`）

> **纪律（设计方案 §8.4）**：自建立第一天起锁死，**永不进训练集**。混入则验收闸失效。  
> Commit **#46**：目录约定 + `MANIFEST.json` + overlap 工具。空集即可校验格式；**M8** 需现场填满并 `locked=true`。

## 目录布局

```text
jetson_update/testset/
├── README.md          # 本说明
├── MANIFEST.json      # 索引（权威清单）
├── images/            # 原图（jpg/png/…）
└── labels/            # YOLO txt（与 images 同 stem）
```

仓库可提交空 `images/`、`labels/` 与未锁 `MANIFEST.json`（`frames: []`）。现场数据默认**不**进 git（大文件 / 隐私）；板上路径按部署约定放置。

## `MANIFEST.json` 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `schema_version` | int | 当前为 `1` |
| `locked` | bool | 现场标注完成后设 `true`；锁定后禁止增删帧 |
| `never_train` | bool | **必须为 `true`** |
| `class_names` | string[] | 须含 `"person"` |
| `description` | string | 可选说明 |
| `created_at` | string | 可选 ISO 日期 |
| `frames` | object[] | 可空（工具冒烟）；每项见下表 |

### `frames[]` 项

| 字段 | 说明 |
|------|------|
| `id` | 稳定帧 ID（唯一） |
| `image` | 相对 testset 根的路径，如 `images/001.jpg` |
| `label` | 相对路径，如 `labels/001.txt`（YOLO） |
| `notes` | 可选 |

示例（空集模板，仓库默认）：

```json
{
  "schema_version": 1,
  "locked": false,
  "never_train": true,
  "class_names": ["person"],
  "description": "Field frozen testset for Jetson FP16 recall acceptance",
  "created_at": "",
  "frames": []
}
```

## Overlap 校验

训练前 / studio 分集后，禁止训练集与冻结集共享同一图像内容：

```bash
python tools/check_testset_overlap.py \
  --testset jetson_update/testset \
  --train /path/to/train/images
```

仅校验 MANIFEST 格式（空集 OK）：

```bash
python tools/check_testset_overlap.py --testset jetson_update/testset --manifest-only
```

要求磁盘上帧文件存在：

```bash
python tools/check_testset_overlap.py --testset jetson_update/testset --manifest-only --require-files
```

退出码：`0` 通过；`1` 格式/重叠失败；`2` 用法错误。

## 与后续 commit

| # | 用途 |
|---|------|
| #49 | `acceptance` 按本 MANIFEST 跑 FP16 召回闸（阈值 D5） |
| #42 | Win studio train/test 隔离；与本工具概念对齐，路径独立 |

## 现场填满（M8）

1. 选 ≥100–200 张 person 帧（宁可多标、勿漏标）。
2. 写入 `images/` + `labels/`，更新 `frames`。
3. 设 `locked: true`。
4. 与任意训练集跑 overlap，须通过。
