# 交接说明 (Handover Guide)

给接手代码的队友：拿到项目目录后，按下面顺序操作即可跑通全部脚本。项目本体是一份纯物理篮球投篮模拟，覆盖罚球主流程，并保留三分球扩展对比；输出结局统一为 `swish` / `rim-in` / `board-in` / `miss`。

## 第一步：装环境

```bash
cd <项目目录>
pip install -r requirements.txt
```

核心依赖只有 `numpy` 和 `matplotlib`，建议 Python 3.10+。

## 第二步：按顺序跑通自检

```bash
python physics.py        # 物理引擎自检（打印最高点、落地时间等）
python collision.py      # 碰撞自检（打印 5 组碰撞前后速度）
python simulation.py     # 单发投篮模拟，生成 trajectory.csv
python experiment.py     # 角度×后旋扫描，默认同时跑罚球+三分，生成 data.csv + data_three.csv
python plotting.py       # 生成 dpi=300 的 PNG 图表
python validation.py --make-dummy   # 生成占位数据 dummy_data.csv
python validation.py     # 跑一致性验证
```

## 替换真实数据（验证阶段）

1. 数据格式（详见 `validation.py` 顶部 docstring）：

   ```
   shot_id, release_x, release_y, release_z, v0x, v0y, v0z, backspin, actual_outcome
   ```

2. 把真实数据文件放到项目目录，例如 `real_shots.csv`。

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
python experiment.py            # 罚球 + 三分球两个扫描（并生成 2D 窗口 data_2d.csv / data_2d_three.csv）
python experiment.py three      # 只跑三分球扫描 -> data_three.csv
python plotting.py              # 重新出图
```

- 热力图输出：`make_probability.png`（罚球）、`make_probability_three.png`（三分球）、`make_probability_comparison.png`（并排对比）
- 轨迹对比图：`trajectory_comparison.png`（罚球）、`trajectory_comparison_three.png`（三分球）、`free_vs_three_drag.png`（罚球 vs 三分球阻力偏差）
- 改扫描范围：编辑 `experiment.py` 里的 `ANGLES_DEG` / `BACKSPINS`（罚球）、`THREE_ANGLES_DEG` / `THREE_BACKSPINS`（三分球）
  （后旋目前均设为 0–60 rad/s）

## 常见问题

- 报错 `No module named numpy`：先执行 `pip install -r requirements.txt`
- `experiment.py` 太慢：把 `JITTER_SHOTS` 调小（如 20），或把 `DT` 改 `2e-3`
- 热力图星星贴边：扩大 `BACKSPINS` 范围（已设为 0–60，正常情况下峰值在图内部）
- 想看「模型自洽」验证（预期 ≈100%）：`python -c "import validation; validation.make_dummy_data(correlated=True)"` 后再 `python validation.py`
- 需要重跑三分球扩展：使用 `python experiment.py three` 并配合 `python plotting.py` 生成对应图像

## 关键结论（当前版本）

- 罚球峰值大致出现在 `55°`、`45 rad/s` 附近，最优命中率约 `0.77`。
- 三分球扩展峰值大致在 `48°`、`49 rad/s` 附近，最优命中率约 `0.80`。
- 真空假设下瞄准筐心时，真实飞行到篮筐平面会偏低；罚球约 `40.2 cm`，三分球约 `117 cm`，说明阻力和马格努斯效应随距离增长而更明显。
