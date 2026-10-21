# 纯物理篮球投篮模拟

一个完全基于物理模型的篮球投篮仿真项目，不依赖机器学习或数据驱动训练。给定出手点、出手速度向量和后旋角速度，程序会使用四阶 Runge–Kutta（RK4）数值积分计算球的飞行轨迹，并在此过程中考虑：

- 重力
- 二次空气阻力
- 马格努斯升力（由后旋产生）
- 篮板与篮筐的刚性碰撞（含边缘/角落接触）

最终会判断这次投篮属于以下四种结果：

- `swish`：空心
- `rim-in`：碰筐后进
- `board-in`：打板后进
- `miss`：未进

这个项目同时包含交互式 2D 模拟器、参数扫描、可视化结果、单元测试和模型验证，适合用于研究不同出手角度和后旋对命中率的影响。

## 目录

1. [项目目标](#1-项目目标)
2. [快速开始（免安装版）](#2-快速开始免安装版)
3. [核心特性](#3-核心特性)
4. [两套模型常数不可混用](#4-两套模型常数不可混用)
5. [物理设定（3D 主流程）](#5-物理设定3d-主流程)
6. [文件结构](#6-文件结构)
7. [环境配置](#7-环境配置)
8. [推荐运行顺序](#8-推荐运行顺序)
9. [生成文件说明](#9-生成文件说明)
10. [团队协作建议](#10-团队协作建议)
11. [进一步说明](#11-进一步说明)

## 1. 项目目标

我们的目标不是训练一个预测模型，而是构建一个可解释、可重现、可验证的物理模拟框架，用来回答下面这个问题：

> 在给定出手几何、初速度和后旋的情况下，纯物理模型能否稳定复现真实投篮中出现的 swish / rim-in / board-in / miss 这四类结果？

项目的研究重点包括：

- 出手角度对飞行轨迹的影响
- 后旋对球的升力和落点的影响
- 空气阻力在罚球和三分球中的差异
- 篮板/篮筐碰撞对最终命中结果的影响
- 通过验证框架评估模拟与真实数据的偏差

## 2. 快速开始（免安装版）

不想装 Python 的同学，直接下载仓库根目录的 [`basketball_shot_2d.exe`](basketball_shot_2d.exe)（2D 交互式模拟器的 PyInstaller 打包版），双击即可运行，无需任何依赖。效果预览见 [SIMULATION_2D_DEMOS.md](SIMULATION_2D_DEMOS.md) 中的 6 个演示 GIF（空心、打板、弹筐、三分等典型场景）。

浏览器双击 [`basketball_interactive.html`](basketball_interactive.html) 可看 (角度 × 后旋) 扫描动画，无需 Python，但需要联网加载 plotly.js CDN。

## 3. 核心特性

- **交互式 2D 模拟器**（`basketball_shot_2d.py`）：滑块实时调节出手高度/角度/后旋/速度/距离，SHOOT 动画重放，SCAN WINDOW 一键搜索"必中速度区间"，内置罚球/三分预设——详见 [SIMULATION_2D_GUIDE.md](SIMULATION_2D_GUIDE.md)
- **三力模型**：重力 + 二次空气阻力（∝ |v|·v）+ 马格努斯升力（后旋，∝ ω × v）
- **RK4 数值积分**：支持单发模拟和批量向量化计算
- **碰撞检测**：篮板（平面-球碰撞）与篮筐（圆环-球碰撞），支持球心在矩形外时的篮板边缘/角落接触，支持批量检测与穿透位置校正——原理与改进方向见 [Collision.md](Collision.md)
- **恢复系数**：碰撞使用恢复系数反弹（法向 `e = 0.7`；3D 默认切向保留比例 1.0，2D 层切向乘 0.85）
- **命中结局细分**：3D 流程按碰撞历史输出 `swish` / `rim-in` / `board-in` / `miss`；2D 流程输出 `SWISH` / `BANK-IN` / `RATTLE-IN` 与各种 miss 描述，两套名称可通过 `collision.canonical_outcome_2d()` 归一化对接
- **交互式 HTML 轨迹浏览器**（`basketball_interactive.html`）：Plotly 生成的 (角度 × 后旋) 扫描动画（5 个角度 × 5 个后旋、固定 7.5 m/s 罚球出手），队友浏览器双击即可查看，无需 Python；`python make_interactive.py --offline` 可生成不依赖网络的完整内嵌版
- **命中概率热力图**：覆盖出手角度 × 后旋速率的参数扫描，输出命中概率面（3D 蒙特卡洛 + 2D "必中速度窗口"两套）
- **结局占比分解图**：`outcome_breakdown.png`，swish / rim-in / board-in 占比随参数的变化
- **轨迹对比**：比较真空瞄准 vs 真实飞行轨迹，并包含罚球与三分球对比
- **单元测试与自检**：`test_core.py` / `test_collision.py` / `test_experiment.py`，加上各脚本自带的无头自检（`--check`、`--selfcheck`、`python physics.py`、`python collision.py`）
- **模型验证**：报告一致率、Wilson 95% 置信区间、Cohen's kappa、MCC/precision/recall/F1 以及多分类混淆矩阵

## 4. ⚠️ 两套模型常数不可混用

仓库里存在**两套故意不同的物理常数**，结论不可互相搬运。合并后的 `physics.py` / `collision.py` 把两套常数并排放在同一文件里（3D 主名 / `*_2D` 后缀名），但**绝不要把一边的扫描结果直接拿到另一边下结论**：

| 常数 | 2D 模拟器 `basketball_shot_2d.py` | 3D 主流程 `physics.py` / `collision.py` |
|---|---|---|
| 球质量 | 0.60 kg | 0.624 kg |
| 空气密度 ρ | 1.204 | 1.225 |
| 阻力系数 C_D | 0.47 | 0.50 |
| 马格努斯 | 固定 `C_L = 0.20`（力 ∝ ω×v） | `C_L0 = 1.00`，等价升力系数形式 |
| 恢复系数 | 法向 0.70 + 切向 0.85 | e = 0.70（默认切向保留比例 1.0） |
| 筐口半径 | 0.2287 m（内径 45.7 cm） | 0.225 m |
| 篮板-筐关系 | 板面 = 筐后沿 + 0.15 m | 筐心距板面 0.375 m |

2D 模拟器常数冻结自课程 deck（详见 [SIMULATION_2D_PHYSICS.md](SIMULATION_2D_PHYSICS.md)），用于演示与交互；3D 主流程用于正式实验与验证。

## 5. 物理设定（3D 主流程）

### 5.1 坐标系

- 坐标系为右手系，单位为 SI
- `x` 方向从投手指向篮筐
- `y` 方向竖直向上
- `z` 方向为横向侧向

### 5.2 场地几何

- 篮板位于 `x = 0`（宽 1.8 m、高 1.05 m，下沿 y = 2.9 m）
- 投手位于 `-x` 侧
- 篮筐中心位于 `(-0.375, 3.05, 0)`
- 篮筐高度：`3.05 m`
- 篮筐直径：`0.45 m`（半径 `0.225 m`）
- 篮心到篮板距离：`0.375 m`
- 反弹恢复系数：`e = 0.7`（篮板与篮筐可分别配置：`BACKBOARD_RESTITUTION` / `RIM_RESTITUTION`，当前默认均为 0.7）

### 5.3 后旋方向

纯后旋定义为：

```python
omega = (0, 0, +omega)
```

这样会产生一个向上的 Magnus 升力，因此后旋越大，球越容易"托起来"。

## 6. 文件结构

| 文件 | 作用 |
|---|---|
| `basketball_shot_2d.py` | 交互式 2D 投篮模拟器（滑块 + 动画 + 速度窗口扫描）；`--check` 跑 6 个文档场景无头自检 |
| `basketball_shot_2d.exe` | 上者的 PyInstaller 打包版，双击即用，无需 Python |
| `physics.py` | 定义物理常数（含 `*_2D` 两套）、三力模型和 RK4 积分函数（3D 与 2D） |
| `collision.py` | 3D 篮板/篮筐碰撞检测（含边缘/角落、批量、多接触有限轮处理）与 2D 板面穿越/前后缘反弹几何，含归一化结局映射 |
| `simulation.py` | `simulate_shot`（3D 单发，碰撞循环 + CSV）、`simulate_2d`/`fit_segments_2d`/`readout_2d`（与交互器同源的库版 2D 引擎） |
| `experiment.py` | 参数扫描：`free` / `three` 生成 3D 数据、`2d` 生成 2D 必中速度窗口数据；直接运行默认四套全跑；`--selfcheck` 逐字节复现校验 |
| `plotting.py` | 生成 7 张 PNG（热力图、结局分解、轨迹对比、罚球 vs 三分阻力偏差）；`breakdown` / `selfcheck` 子命令 |
| `validation.py` | 验证流程、评估指标和占位数据生成；`--make-dummy [--correlated]`、`selfcheck` 模式 |
| `make_interactive.py` | 生成 Plotly 交互式轨迹浏览器 `basketball_interactive.html`；`--offline` / `--out` |
| `test_core.py` | 核心物理/碰撞/模拟的单元测试（无第三方依赖） |
| `test_collision.py` | 碰撞几何与速度响应的专项测试 |
| `test_experiment.py` | 扫描 CSV 输出与配置元数据的可复现性测试 |
| `data_validation/` | 第一阶段验证数据暂存区：`DATA_SPECIFICATION.md`（数据规范）、`extract.py`（SportVU 抽取脚本）、抽取的球轨迹 CSV 与占位模板 |
| `Specifications/` | 计划书、规格说明与进度汇报（`.md` + 原版 `.pdf` / `.pptx`） |
| `SIMULATION_2D_GUIDE.md` | 2D 模拟器使用指南（滑块/按钮/开关/读数） |
| `SIMULATION_2D_PHYSICS.md` | 2D 模拟器物理模型与常数（含与 3D 流程的差异说明） |
| `Collision.md` | 碰撞模型的计算方法、测试与改进方向 |
| `requirements.txt` | Python 依赖列表 |
| `HANDOVER_GUIDE.md` | 交接说明与运行顺序 |
| `PROJECT_CONTEXT.md` | 给协作者/AI 助手的背景说明 |

## 7. 环境配置

要求 Python 3.10+。依赖见 [requirements.txt](requirements.txt)：

```bash
pip install -r requirements.txt
```

核心依赖通常只有：

- `numpy`
- `matplotlib`

如果还要生成交互式 HTML，需要额外安装 `plotly`：

```bash
pip install plotly
```

## 8. 推荐运行顺序

建议按下面顺序执行，这样最容易确认每一部分是否正常工作：

```bash
# 1) 单元测试：核心物理 + 碰撞几何 + 扫描输出
python test_core.py
python test_collision.py
python test_experiment.py

# 2) 物理引擎自检（3D 积分 + 2D 常数/退化输入，打印自检通过项）
python physics.py

# 3) 碰撞自检（4 组 3D 示例 + 5 组 2D 示例）
python collision.py

# 4) 单发罚球模拟：输出结果并生成 trajectory.csv
#    （同时跑 6 个 2D 文档场景并生成 trajectory_2d.csv）
python simulation.py

# 5) 参数扫描：直接运行默认跑全部四套（3D 角度×后旋、3D 三分、
#    2D 必中速度窗口 × 罚球/三分），或按需选择子命令：
python experiment.py          # 全部
python experiment.py free     # 仅 3D 罚球 -> data.csv
python experiment.py three    # 仅 3D 三分 -> data_three.csv
python experiment.py 2d       # 仅 2D 窗口 -> data_2d.csv / data_2d_three.csv

# 6) 生成图表：7 张 PNG 一次出全（热力图 + 结局分解 + 轨迹对比）
python plotting.py

# 7) 验证：先生成示例数据，再跑一致性验证（含置信区间与 kappa）
python validation.py --make-dummy
python validation.py
```

其他常用入口：

```bash
# 交互式 2D 模拟器（弹出 TkAgg 窗口）
python basketball_shot_2d.py

# 2D 模拟器无头自检（CI 用，不开窗口）
python basketball_shot_2d.py --check

# 各脚本自带的可复现自检（写入临时目录，不污染仓库数据）
python experiment.py --selfcheck
python plotting.py selfcheck
python validation.py selfcheck

# 3D 罚球大网格多进程扫描（默认单进程已够快，网格很大时才需要）
python experiment.py --mp

# 生成交互式 HTML 轨迹浏览器（需 plotly；--offline 出内嵌 plotly.js 的完整版）
python make_interactive.py
python make_interactive.py --offline --out basketball_interactive_offline.html
```

## 9. 生成文件说明

| 文件 | 生成方式 | 内容 |
|---|---|---|
| `trajectory.csv` | `python simulation.py` | 单发 3D 罚球轨迹，列为 `time, x, y, z, vx, vy, vz` |
| `trajectory_2d.csv` | `python simulation.py` | 2D 罚球基准场景（2.00 m / 51° / 23 rad/s / 7.90 m/s / 4.60 m）的轨迹点 |
| `data.csv` | `python experiment.py`（或 `free`） | 3D 罚球扫描结果，列为 `angle, backspin, p_make, p_swish, p_rim_in, p_board_in` + 每行附带扫描配置元数据（距离、名义速度、随机种子、抖动 σ、网格范围等） |
| `data_three.csv` | `python experiment.py`（或 `three`） | 3D 三分球扫描结果，列结构同上 |
| `data_2d.csv` / `data_2d_three.csv` | `python experiment.py`（或 `2d`） | 2D 每格统计：`p_speed_made`、各结局占比、最宽"必中速度窗口" `band_lo/hi/width/mid`、中点精确结局 |
| `dummy_data.csv` | `python validation.py --make-dummy` | 验证用占位数据（`--correlated` 出自洽版，一致率应为 100%） |
| `make_probability.png` | `python plotting.py` | 罚球命中概率图 |
| `make_probability_three.png` | `python plotting.py` | 三分球命中概率图 |
| `make_probability_comparison.png` | `python plotting.py` | 罚球/三分球并排对比 |
| `outcome_breakdown.png` | `python plotting.py` | 进球子类（swish/rim-in/board-in）占比分解图 |
| `trajectory_comparison.png` | `python plotting.py` | 罚球轨迹比较 |
| `trajectory_comparison_three.png` | `python plotting.py` | 三分球轨迹比较 |
| `free_vs_three_drag.png` | `python plotting.py` | 罚球 vs 三分球空气阻力偏差图 |
| `basketball_interactive.html` | `python make_interactive.py` | 带滑块的交互式轨迹浏览器（CDN 版，需联网） |

`data_validation/` 目录下的 CSV（`extracted_ball_tracks.csv`、`selected_shot_initial_conditions.csv`、`basketball_shots_validation_template.csv`）是第一阶段真实数据导入的暂存件，尚未构成可运行的验证输入；字段约定与待办见 [data_validation/DATA_SPECIFICATION.md](data_validation/DATA_SPECIFICATION.md)。

## 10. 团队协作建议

这个 README 适合给团队成员快速了解项目，用作项目入口文档。建议团队成员在协作时遵循以下习惯：

- 先看 [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) 了解项目背景和接口说明
- 再从 [HANDOVER_GUIDE.md](HANDOVER_GUIDE.md) 按顺序执行脚本
- 想快速上手玩模拟器：直接双击 `basketball_shot_2d.exe`，或看 [SIMULATION_2D_GUIDE.md](SIMULATION_2D_GUIDE.md)
- 改碰撞相关代码前，先读 [Collision.md](Collision.md) 和 `test_collision.py`，改完跑一遍测试
- 改任何链路的代码后，跑对应脚本的 `--check` / `--selfcheck`，再跑 `test_*.py`，确认逐位一致再提交
- 修改代码时优先参考各个 Python 文件中的 docstring 和函数说明
- 若要增加新实验或新数据集，先更新说明，再补充图表/验证结果

## 11. 进一步说明

- 相关交接说明： [HANDOVER_GUIDE.md](HANDOVER_GUIDE.md)
- AI/协作者上下文说明： [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
- 详细项目计划与技术背景： [Specifications/](Specifications/)
- 2D 模拟器： [SIMULATION_2D_GUIDE.md](SIMULATION_2D_GUIDE.md) / [SIMULATION_2D_PHYSICS.md](SIMULATION_2D_PHYSICS.md)
- 碰撞模型细节： [Collision.md](Collision.md)
- 验证数据规范： [data_validation/DATA_SPECIFICATION.md](data_validation/DATA_SPECIFICATION.md)
- 报告草稿： [Report_Draft.md](Report_Draft.md)，汇报大纲： [Presentation_Outline.md](Presentation_Outline.md)

如果你和队友都在同一个项目里协作，这个 README 可以作为"项目总入口"，帮助快速定位脚本、数据和结果文件。
