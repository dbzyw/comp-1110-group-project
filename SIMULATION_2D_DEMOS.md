# 2D 模拟器演示 GIF（demo_gifs/）

以下 GIF 由 `basketball_shot_2d.py` 的同一套渲染管线 headless 导出（`simulate` → `init_scene` → `update_scene` 逐帧渲染，20 fps），展示几种典型参数与结局。画面元素说明见 [SIMULATION_2D_GUIDE.md](SIMULATION_2D_GUIDE.md)，物理模型见 [SIMULATION_2D_PHYSICS.md](SIMULATION_2D_PHYSICS.md)。

| GIF | 参数（高度 m / 角度° / 后旋 rad/s / 速度 m/s / 距离 m） | 结局 | 看点 |
|---|---|---|---|
| `01_free_throw_swish.gif` | 2.00 / 51 / 23 / 7.90 / 4.60 | **SWISH** | 罚球基准情形：真实弧线（青）比真空抛物线（紫）平缓，空心入筐 |
| `02_bank_shot.gif` | 2.00 / 36 / 23 / 9.10 / 4.60 | **BANK-IN** | 低平打板：球撞板反弹后落进筐，青色弧线在碰撞点分出第二段 |
| `03_rattle_in.gif` | 2.00 / 36 / 23 / 8.70 / 4.60 | **RATTLE-IN** | 弹筐：球先后磕筐沿反弹（白方框标记）最终滚进 |
| `04_short_miss.gif` | 2.00 / 51 / 23 / 6.00 / 4.60 | miss（well short） | 力量太小：到筐面时低于筐沿，未碰任何东西直接落地 |
| `05_air_off.gif` | 2.00 / 51 / 23 / 7.90 / 4.60（AIR OFF） | **BANK-IN** | 同 01 的参数但关掉空气：没有阻力/升力时同样的出手变成打板进——直观展示空气对命中与否的影响 |
| `06_three_pointer.gif` | 2.00 / 45 / 23 / 9.46 / 6.75 | **SWISH** | 三分线（6.75 m）：需要明显更高的弧线和更大的出手速度 |

复现方法：运行 `python basketball_shot_2d.py`，把上表参数拖进滑块（或按 FREE THROW / THREE POINT 预设）即可在交互界面看到同样的轨迹。
