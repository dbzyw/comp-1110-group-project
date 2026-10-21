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

## 3. 核心特性

- **交互式 2D 模拟器**（`basketball_shot_2d.py`）：滑块实时调节出手高度/角度/后旋/速度/距离，SHOOT 动画重放，SCAN WINDOW 一键搜索"必中速度区间"，内置罚球/三分预设——详见 [SIMULATION_2D_GUIDE.md](SIMULATION_2D_GUIDE.md)
- **三力模型**：重力 + 二次空气阻力（∝ |v|·v）+ 马格努斯升力（后旋，∝ ω × v）
- **RK4 数值积分**：支持单发模拟和批量向量化计算
- **碰撞检测**：篮板（平面-球碰撞）与篮筐（圆环-球碰撞），支持球心在矩形外时的篮板边缘/角落接触，支持批量检测与穿透位置校正——原理与改进方向见 [碰撞.md](碰撞.md)
- **恢复系数**：碰撞使用恢复系数反弹（法向 `e = 0.7`）
- **交互式 HTML 轨迹浏览器**（`basketball_interactive.html`）：Plotly 生成的 (角度 × 后旋) 扫描动画，队友浏览器双击即可查看，无需 Python
- **命中概率热力图**：覆盖出手角度 × 后旋速率的参数扫描，输出命中概率面
- **轨迹对比**：比较真空瞄准 vs 真实飞行轨迹，并包含罚球与三分球对比
- **单元测试**：核心物理与碰撞几何各有专门测试文件
- **模型验证**：报告一致率、Wilson 95% 置信区间、Cohen's kappa 以及多分类混淆矩阵

## 4. ⚠️ 两套模型常数不可混用

仓库里存在**两套故意不同的物理常数**，结论不可互相搬运：

| 常数 | 2D 模拟器 `basketball_shot_2d.py` | 3D 主流程 `physics.py` / `collision.py` |
|---|---|---|
| 球质量 | 0.60 kg | 0.624 kg |
| 空气密度 ρ | 1.204 | 1.225 |
| 阻力系数 C_D | 0.47 | 0.50 |
| 恢复系数 | 法向 0.70 + 切向 0.85 | e = 0.70 |

2D 模拟器常数冻结自课程 deck（详见 [SIMULATION_2D_PHYSICS.md](SIMULATION_2D_PHYSICS.md)），用于演示与交互；3D 主流程用于正式实验与验证。**不要把一边的扫描结果直接拿到另一边下结论。**

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
- 反弹恢复系数：`e = 0.7`

### 5.3 后旋方向

纯后旋定义为：

```python
omega = (0, 0, +omega)
```

这样会产生一个向上的 Magnus 升力，因此后旋越大，球越容易"托起来"。

## 6. 文件结构

| 文件 | 作用 |
|---|---|
| `basketball_shot_2d.py` | 交互式 2D 投篮模拟器（滑块 + 动画 + 速度窗口扫描） |
| `basketball_shot_2d.exe` | 上者的 PyInstaller 打包版，双击即用，无需 Python |
| `physics.py` | 定义物理常数、三力模型和 RK4 积分函数 |
| `collision.py` | 篮板/篮筐几何与碰撞检测（含边缘/角落）、恢复系数反弹、位置校正 |
| `simulation.py` | 单发投篮模拟、碰撞循环、出手判定与轨迹保存 |
| `experiment.py` | 角度和后旋的参数扫描，生成 `data.csv` / `data_three.csv` |
| `plotting.py` | 生成命中概率热力图与轨迹对比图 |
| `validation.py` | 验证流程、评估指标和占位数据生成 |
| `make_interactive.py` | 生成 Plotly 交互式轨迹浏览器 `basketball_interactive.html` |
| `test_core.py` | 核心物理/碰撞/模拟的单元测试（无第三方依赖） |
| `test_collision.py` | 碰撞几何与速度响应的专项测试（PR #1 引入） |
| `SIMULATION_2D_GUIDE.md` | 2D 模拟器使用指南（滑块/按钮/开关/读数） |
| `SIMULATION_2D_PHYSICS.md` | 2D 模拟器物理模型与常数（含与 3D 流程的差异说明） |
| `SIMULATION_2D_DEMOS.md` | 6 个典型场景的演示 GIF 解说（`demo_gifs/`） |
| `碰撞.md` | 碰撞模型的计算方法、测试与改进方向 |
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
# 1) 单元测试：核心物理 + 碰撞几何
python test_core.py
python test_collision.py

# 2) 物理引擎自检
python physics.py

# 3) 碰撞自检
python collision.py

# 4) 单发罚球模拟：输出结果并生成 trajectory.csv
python simulation.py

# 5) 参数扫描：角度 × 后旋，生成罚球/三分球数据
python experiment.py

# 6) 生成图表：热力图 + 轨迹对比
python plotting.py

# 7) 验证：先生成示例数据，再跑一致性验证
python validation.py --make-dummy
python validation.py
```

其他常用入口：

```bash
# 交互式 2D 模拟器（弹出 TkAgg 窗口）
python basketball_shot_2d.py

# 只跑三分球扩展扫描
python experiment.py three

# 生成交互式 HTML 轨迹浏览器（需 plotly）
python make_interactive.py
```

## 9. 生成文件说明

| 文件 | 生成方式 | 内容 |
|---|---|---|
| `trajectory.csv` | `python simulation.py` | 单发投篮轨迹，列为 `time, x, y, z, vx, vy, vz` |
| `data.csv` | `python experiment.py` | 罚球扫描结果 |
| `data_three.csv` | `python experiment.py three` | 三分球扫描结果 |
| `dummy_data.csv` | `python validation.py --make-dummy` | 验证用占位数据 |
| `make_probability.png` | `python plotting.py` | 罚球命中概率图 |
| `make_probability_three.png` | `python plotting.py` | 三分球命中概率图 |
| `make_probability_comparison.png` | `python plotting.py` | 罚球/三分球并排对比 |
| `trajectory_comparison.png` | `python plotting.py` | 罚球轨迹比较 |
| `trajectory_comparison_three.png` | `python plotting.py` | 三分球轨迹比较 |
| `free_vs_three_drag.png` | `python plotting.py` | 罚球 vs 三分球空气阻力偏差图 |
| `basketball_interactive.html` | `python make_interactive.py` | 带滑块的交互式轨迹浏览器 |

## 10. 团队协作建议

这个 README 适合给团队成员快速了解项目，用作项目入口文档。建议团队成员在协作时遵循以下习惯：

- 先看 [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) 了解项目背景和接口说明
- 再从 [HANDOVER_GUIDE.md](HANDOVER_GUIDE.md) 按顺序执行脚本
- 想快速上手玩模拟器：直接双击 `basketball_shot_2d.exe`，或看 [SIMULATION_2D_GUIDE.md](SIMULATION_2D_GUIDE.md)
- 改碰撞相关代码前，先读 [碰撞.md](碰撞.md) 和 `test_collision.py`，改完跑一遍测试
- 修改代码时优先参考各个 Python 文件中的 docstring 和函数说明
- 若要增加新实验或新数据集，先更新说明，再补充图表/验证结果

## 11. 进一步说明

- 相关交接说明： [HANDOVER_GUIDE.md](HANDOVER_GUIDE.md)
- AI/协作者上下文说明： [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
- 详细项目计划与技术背景： [Specifications/](Specifications/)
- 2D 模拟器： [SIMULATION_2D_GUIDE.md](SIMULATION_2D_GUIDE.md) / [SIMULATION_2D_PHYSICS.md](SIMULATION_2D_PHYSICS.md) / 演示 GIF 见 [SIMULATION_2D_DEMOS.md](SIMULATION_2D_DEMOS.md)
- 碰撞模型细节： [碰撞.md](碰撞.md)

如果你和队友都在同一个项目里协作，这个 README 可以作为"项目总入口"，帮助快速定位脚本、数据和结果文件。
