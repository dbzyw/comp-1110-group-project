# 交接说明 (Handover Guide)

给接手代码的队友：拿到项目目录后，按下面顺序操作即可跑通全部脚本。项目本体是一份纯物理篮球投篮模拟，覆盖罚球主流程，并保留三分球扩展对比；输出结局统一为 `swish` / `rim-in` / `board-in` / `miss`。2D 交互器与 2D 速度窗口扫描用的是另一套冻结常数（见根目录 `README.md` §4），两套结果不可互相下结论。

## 第一步：装环境

```bash
cd <项目目录>
pip install -r requirements.txt
```

核心依赖只有 `numpy` 和 `matplotlib`，建议 Python 3.10+。生成交互式 HTML 才需额外 `pip install plotly`。

## Blender 3D 预测结果可视化（可选）

预测轨迹时，Python 3D 物理引擎也会根据轨迹推断最终结局：球心向下穿过 NBA 筐顶平面（`y = 3.048 m`）且水平距离开口中心不超过 `RIM_RADIUS - BALL_RADIUS ≈ 0.10935 m` 判为命中，否则判为未中；命中再按篮板/篮筐接触历史分为 `swish`、`rim-in` 或 `board-in`。Blender 负责把已计算的轨迹和结局呈现为 3D 场景，不负责物理积分或独立判定结局。

```powershell
python validation.py data_validation\valid_data_2D.csv
```

该命令通过验证 CSV 对模型预测与记录标签进行比较；输入须包含 `actual_outcome`，格式和限制见 `data_validation/DATA_SPECIFICATION.md`。对新的一组初始条件可直接使用 `simulation.simulate_shot()`取得预测轨迹和结局。要重建仓库中现有的三种演示结局及其 Blender 动画，从项目根目录运行：

```powershell
python blender_3d\find_shots.py
blender -b -noaudio --python blender_3d\build_blender.py
```

第一步使用 `simulate_shot()` 搜索并分类三发命中演示，导出 `blender_3d\traj_*.csv` 和 `shots.json`；第二步在 Blender 5.x 中读取这些文件、保存场景 `.blend` 并渲染静帧。若 `ffmpeg` 已加入 `PATH`，还会合成 `blender_3d\out\shot3d.mp4`。当前场景仅包含这三发预制命中示例，构景脚本尚未接通任意验证 CSV 或未中轨迹；不要将 Blender 渲染描述为模型预测的来源。

## 第二步：按顺序跑通自检

```bash
python physics.py        # 3D 积分自检（最高点、过筐时刻、落地时间）
                         # + 2D 常数对照 + 退化输入加固示例
python collision.py      # 4 组 3D 碰撞示例 + 5 组 2D 板面/筐沿示例（含归一化映射）
python simulation.py     # 单发 3D 罚球模拟 -> trajectory.csv
                         # + 6 个 2D 文档场景自检 -> trajectory_2d.csv
python experiment.py     # 默认跑全部四套扫描:
                         #   3D 罚球 -> data.csv, 3D 三分 -> data_three.csv
                         #   2D 速度窗口 -> data_2d.csv / data_2d_three.csv
python plotting.py       # 一次生成 7 张 dpi=300 PNG（含 outcome_breakdown.png）
python validation.py --make-dummy   # 生成占位数据 dummy_data.csv
python validation.py     # 跑一致性验证（一致率 + Wilson CI + kappa + 混淆矩阵）
```

## 第三步：可选的无头自检（改代码后必跑）

```bash
python basketball_shot_2d.py --check   # 6 个演示场景逐一复现，CI 友好
python experiment.py --selfcheck       # 小网格写临时目录，逐字节复现校验
python plotting.py selfcheck           # 7 张图重画到临时目录，验证产出
python validation.py selfcheck         # 自洽 dummy -> 断言一致率 100%
python test_core.py && python test_collision.py && python test_experiment.py
```

## 替换真实数据（验证阶段）

1. 数据格式（详见 `validation.py` 顶部 docstring）：

   ```
   shot_id, release_x, release_y, release_z, v0x, v0y, v0z, backspin, actual_outcome
   ```

2. 把真实数据文件放到项目目录，例如 `real_shots.csv`。`data_validation/` 现有内容、字段规范与验收步骤见 `data_validation/DATA_SPECIFICATION.md`。当前数据分为 `valid_data_2D.csv`（300 行直线近似，`release_z = v0z = 0`）和 `valid_data_3D.csv`（35 行暂定 3D 输入）。分别运行 `python validation.py data_validation/valid_data_2D.csv` 或 `python validation.py data_validation/valid_data_3D.csv`。3D 文件的坐标映射、单位、标签和后旋仍含假设，因此两份结果都**不是实测验证结论**。

3. 两种方式跑验证：

   - 命令行直接指定文件：
     ```bash
     python validation.py real_shots.csv
     ```
   - 或修改 `validation.py` 中 `run_validation()` 的默认参数：
     ```python
     run_validation("real_shots.csv")
     ```

   `actual_outcome` 取值（大小写均可）：
   - 命中，具体子类（推荐，参与 `swish` / `rim-in` / `board-in` / `miss` 多分类分析）：
     `swish` / `rim-in` / `board-in`
   - 命中，未细分子类的旧标签（仅参与 made/miss 二分类）：
     `bounce-in` / `made` / `in`
   - 未中：`miss` / `out` / `no`

## 重新生成最新图表

```bash
python experiment.py            # 四套扫描全跑（3D 两套 + 2D 两套）
python experiment.py three      # 只跑 3D 三分扫描 -> data_three.csv
python plotting.py              # 重新出全部 7 张图
python plotting.py breakdown    # 只画结局占比分解图
```

- 热力图输出：`make_probability.png`（罚球）、`make_probability_three.png`（三分球）、`make_probability_comparison.png`（并排对比）
- 结局分解：`outcome_breakdown.png`（swish / rim-in / board-in 占比随参数变化）
- 轨迹对比图：`trajectory_comparison.png`（罚球）、`trajectory_comparison_three.png`（三分球）、`free_vs_three_drag.png`（罚球 vs 三分球阻力偏差）
- 改扫描范围：编辑 `experiment.py` 里的 `ANGLES_DEG` / `BACKSPINS`（3D 罚球）、`THREE_ANGLES_DEG` / `THREE_BACKSPINS`（3D 三分）
  （后旋目前均设为 0–60 rad/s；2D 窗口扫描的网格是 `_2D_ANGLES` / `_2D_BACKSPINS` + `SPEED_LO_2D`/`SPEED_HI_2D`/`SPEED_SAMPLES_2D`）

## 常见问题

- 报错 `No module named numpy`：先执行 `pip install -r requirements.txt`
- `experiment.py` 太慢：直接 `python experiment.py free`（或 `three` / `2d`）只跑需要的那套；或把 `JITTER_SHOTS` 调小（如 20）、`DT` 改 `2e-3`；网格很大时用 `python experiment.py --mp`
- 热力图星星贴边：扩大 `BACKSPINS` 范围（已设为 0–60，正常情况下峰值在图内部）
- 想看"模型自洽"验证（预期 ≈100%）：`python validation.py --make-dummy --correlated` 后再 `python validation.py`（或一条命令直接 `python validation.py selfcheck`）
- 2D 交互器验证文档场景：`python basketball_shot_2d.py --check`，应 6/6 通过
- 需要重跑三分球扩展：使用 `python experiment.py three` 并配合 `python plotting.py` 生成对应图像

## 关键结论（当前版本，3D 主流程）

- 罚球峰值大致出现在 `55°`、`45 rad/s` 附近，最优命中率约 `0.77`。
- 当前三分扫描峰值为 `45°`、`37.5 rad/s`、`P ≈ 0.79`，该格全为 `board-in`；罚球峰值格为 `55°`、`45 rad/s`、`P ≈ 0.77`（swish 0.52、rim-in 0.15、board-in 0.10）。两套扫描名义速度不同（`7.5` vs `9.5 m/s`），峰值高低不代表真实难度差。
- 真空假设下瞄准筐心时，真实飞行到篮筐平面会偏低；罚球约 `40.2 cm`，三分球约 `117.4 cm`，说明阻力和马格努斯效应随距离增长而更明显。
- 本次 2D 窗口扫描（独立常数）最宽窗口：罚球 `0.3020 m/s`（`47.5°`、`35 rad/s`，中点 `BANK-IN`）；三分 `0.2416 m/s`（`52.5°`、`5 rad/s`，中点 `BANK-IN`）。这些不是 3D 命中概率。

以上数字均为 3D 主流程（`physics.py` / `collision.py` / `simulation.py` / `experiment.py`）的结果；2D 模拟器与 2D 扫描的常数、碰撞模型、判据、结局名都不同（`SWISH` / `BANK-IN` / `RATTLE-IN`），引用时务必注明出处。
