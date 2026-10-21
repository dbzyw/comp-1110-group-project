# 纯物理篮球投篮模拟 (Pure-Physics Basketball Shot Simulation)

一个**不依赖机器学习**的篮球投篮仿真。给定出手点、出手速度向量、后旋角速度，用四阶 Runge-Kutta（RK4）数值积分求解球的飞行，受力包括**重力、二次空气阻力、马格努斯升力**，并与**篮板（竖直平面）**、**篮筐（圆环）**做恢复系数 `e = 0.7` 的碰撞，最终判定 **空心（swish）/ 弹框进（rim-in）/ 打板进（board-in）/ 未进（miss）** 四种结局。

## 核心特性

- **三力模型**：重力 + 二次空气阻力（∝ |v|·v）+ 马格努斯升力（后旋，∝ ω×v）
- **RK4 积分**：单发（`rk4_step`）与批量向量化（`rk4_step_batch`）两种
- **碰撞检测**：篮板（平面-球）与篮筐（圆环-球），恢复系数反弹 + 位置修正
- **命中概率热力图**：出手角度 × 后旋速率 → P(make)，含 50% 等值线与峰值标记
- **轨迹对比**：真空瞄准 vs 真实（阻力 + 后旋）飞行，含罚球 vs 三分球对比
- **模型验证**：一致率 + Wilson 置信区间 + Cohen's kappa + 分结局（swish/rim-in/board-in/miss）混淆矩阵

## 坐标系与关键常数

- 坐标系（右手系，SI 单位）：`x` 从投手指向篮筐，`y` 竖直向上，`z` 侧向
- 篮板位于 `x = 0`，投手在 `-x` 一侧；筐心 `(-0.375, 3.05, 0)`
- 纯后旋：自旋向量 `ω = (0, 0, +ω)`，对向前飞行的球产生向上升力
- NBA 场地：筐高 3.05 m、筐直径 0.45 m、筐心距篮板 0.375 m、恢复系数 e = 0.7

## 文件结构

| 文件 | 用途 |
|---|---|
| `physics.py` | 物理常数、三力、导数函数、RK4 积分（单发 + 批量向量化） |
| `collision.py` | NBA 场地几何、篮板/篮筐碰撞检测、恢复系数反弹（单发 + 批量） |
| `simulation.py` | 完整投篮循环（RK4 + 碰撞 + 得分判定）、轨迹 CSV 导出 |
| `experiment.py` | 出手角度 × 后旋速率 参数扫描（向量化），输出 `data.csv`（罚球）/ `data_three.csv`（三分球） |
| `plotting.py` | 命中概率热力图 + 轨迹对比（罚球/三分球）（dpi=300 PNG） |
| `validation.py` | 模型验证框架 + 占位数据生成 |

## 环境配置

要求 Python 3.10+，依赖见 [requirements.txt](requirements.txt)：

```bash
pip install -r requirements.txt
```

核心依赖只有 `numpy` 和 `matplotlib`。

## 运行指南（推荐顺序）

```bash
# 1) 物理引擎自检（打印最高点、落地时间等）
python physics.py

# 2) 碰撞自检（打印 5 组碰撞前后的速度向量）
python collision.py

# 3) 单发罚球模拟（打印结局，生成 trajectory.csv）
python simulation.py

# 4) 角度 × 后旋扫描（打印进度条，生成 data.csv 罚球 + data_three.csv 三分球）
python experiment.py

# 5) 画图（生成命中概率热力图 + 轨迹对比图，含三分球）
python plotting.py

# 6) 验证（先造占位数据，再跑一致性）
python validation.py --make-dummy
python validation.py
```

## 数据文件说明

| 文件 | 来源 | 内容 |
|---|---|---|
| `data.csv` | `experiment.py` 生成 | 罚球扫描结果（列 `angle,backspin,p_make`） |
| `data_three.csv` | `experiment.py three` 生成 | 三分球扫描结果（列 `angle,backspin,p_make`） |
| `trajectory.csv` | `simulation.py` 生成 | 单发轨迹（列 `time,x,y,z,vx,vy,vz`） |
| `dummy_data.csv` | `validation.py --make-dummy` 生成 | 验证占位数据 |
| `make_probability.png` / `make_probability_three.png` / `make_probability_comparison.png` / `trajectory_comparison.png` / `trajectory_comparison_three.png` / `free_vs_three_drag.png` | `plotting.py` 生成 | 结果图 |

## 更多说明

- 交接步骤见 [HANDOVER_GUIDE.md](HANDOVER_GUIDE.md)
- 供 AI 助手 / 协作者快速上手的上下文见 [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
