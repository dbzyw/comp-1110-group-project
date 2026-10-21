"""extract.py — 把 SportVU/NBA 逐帧 tracking 的原始 JSON 抽成"球"的轨迹 CSV。

用法
----
    python extract.py                      # 读默认 sample.json -> extracted_ball_tracks.csv
    python extract.py --json game.json     # 指定输入
    python extract.py --out tracks.csv     # 指定输出
    python extract.py --events -1          # 抽全部回合（默认只抽前 50 个）
    python extract.py --ball-entity -1     # 篮球在 moment[5] 里的 entity_id（默认 -1）
    python extract.py --selfcheck          # 内置一段假 JSON，端到端验证抽取逻辑，不依赖外部数据

输入 JSON 结构假定与 SportVU（`moments` 文件）一致::

    {
      "events": [
        {
          "eventId": <int>,
          "moments": [
            [ quarter, game_clock, shot_clock, ..., [ [entity_id, x, y, ...] , ... ] ],
            ...
          ]
        },
        ...
      ]
    }

其中 `moment[1]` 为逐帧时间戳(ms)、`moment[3]` 为 shot clock，
`moment[5]` 是该帧所有被追踪实体列表；每个 `entity` 形如
`[entity_id, ..., x_feet, y_feet, z_feet, vx, vy, ...]`（`FEET_TO_METERS` 处按官方约定取
`entity[2/3/4]` 为英尺坐标）。`entity_id == -1` 即代表篮球。

⚠️ 数据可得性与坐标约定（务必读）
-----------------------------------
- 仓库里没有 `sample.json`：需要先自行拿到某一场的 moments JSON（例如把 `--events`
  指向解压后的真实文件）。本脚本不联网、不猜文件名，缺文件时给出明确报错。
- 抽出的 `x_m / y_m / z_m` 沿用该数据源原始坐标系（英尺→米），原点、轴向、
  是否含 off-court 帧都与本项目的 3D 模型坐标（x 指向篮筐、y 向上、篮板在 x=0）**不一致**，
  不能直接喂给 `simulation.py`。把它交给 `data_prep.py` 之前，请先到
  `DATA_SPECIFICATION.md` 记录字段来源、轴约定与时间戳精度，否则验证指标度量的是"坐标猜测"。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

# SportVU/NBA tracking 官方以英尺记录，转 SI 米。
FEET_TO_METERS = 0.3048

DEFAULT_JSON = "sample.json"
DEFAULT_OUT = "extracted_ball_tracks.csv"

# 在 moment 列表里固定下标（见模块 docstring）。
IDX_TIMESTAMP_MS = 1
IDX_SHOT_CLOCK = 3
IDX_ENTITIES = 5

COLUMNS = ["event_id", "timestamp_ms", "shot_clock", "x_m", "y_m", "z_m"]


def extract_ball_rows(data: dict, events_limit: int, ball_entity_id: int) -> list[dict]:
    """从 SportVU `data` 里逐 event 逐 frame 抽出篮球坐标行。

    Args:
        data: 已 json.load 的顶层 dict，应含 `events` 列表。
        events_limit: 只处理前 N 个 event；<=0 表示全部。
        ball_entity_id: 代表篮球的 entity_id（默认 -1）。

    Returns:
        行字典列表，键见 `COLUMNS`。缺 `events` 时抛 ValueError，便于 --selfcheck 与调用方定位问题。
    """
    events = data.get("events")
    if events is None:
        raise ValueError("输入 JSON 缺少 'events' 键：确认这是 moments 文件而非别的结构。")

    rows: list[dict] = []
    selected = events if events_limit <= 0 else events[:events_limit]
    for event in selected:
        event_id = event.get("eventId")
        for moment in event.get("moments", []):
            if len(moment) <= IDX_ENTITIES:
                continue  # 结构异常帧，跳过而不是崩溃
            timestamp = moment[IDX_TIMESTAMP_MS]
            shot_clock = moment[IDX_SHOT_CLOCK]
            for entity in moment[IDX_ENTITIES]:
                if entity[0] != ball_entity_id:
                    continue
                rows.append(
                    {
                        "event_id": event_id,
                        "timestamp_ms": timestamp,
                        "shot_clock": shot_clock,
                        "x_m": round(entity[2] * FEET_TO_METERS, 3),
                        "y_m": round(entity[3] * FEET_TO_METERS, 3),
                        "z_m": round(entity[4] * FEET_TO_METERS, 3),
                    }
                )
    return rows


def synthetic_moments() -> dict:
    """构造一段最小假 moments JSON（2 帧、含篮球与一名球员），供 --selfcheck 端到端验证。"""
    # 下标按模块 docstring：moment[1]=timestamp_ms、moment[3]=shot_clock、moment[5]=实体列表；
    # entity[0]=id、entity[2/3/4]=x/y/z(英尺)。前 5 项 moment 用占位值，实体列表在 index 5。
    frame1 = [1, 1000, 0, 24.0, 0, [[-1, 90, 0.0, 0.0, 0.0, 9.0, 3.0], [3, 0, 10.0, 5.0, 0.0, 2.0, 1.0]]]
    frame2 = [1, 1040, 0, 23.6, 0, [[-1, 90, 12.0, 8.0, 0.0, 10.5, 5.5]]]
    return {"events": [{"eventId": 123, "moments": [frame1, frame2]}]}


def selfcheck() -> int:
    """用内置假 JSON 跑抽取逻辑，断言行数/列名/单位换算，返回 0=通过 1=失败。"""
    rows = extract_ball_rows(synthetic_moments(), events_limit=50, ball_entity_id=-1)
    df = pd.DataFrame(rows, columns=COLUMNS)
    expected = [
        {"event_id": 123, "timestamp_ms": 1000, "shot_clock": 24.0, "x_m": 0.0, "y_m": 0.0, "z_m": 0.0},
        {"event_id": 123, "timestamp_ms": 1040, "shot_clock": 23.6, "x_m": 3.658, "y_m": 2.438, "z_m": 0.0},
    ]
    problems: list[str] = []
    if len(df) != 2:
        problems.append(f"行数 {len(df)} != 2")
    if list(df.columns) != COLUMNS:
        problems.append(f"列名 {list(df.columns)} 与预期 {COLUMNS} 不符")
    for want, got in zip(expected, df.to_dict("records")):
        for key, val in want.items():
            if abs(float(got[key]) - float(val)) > 1e-3:
                problems.append(f"字段 {key}: 得到 {got[key]} 期望 {val}")
    # 12.0 ft * 0.3048 = 3.6576 -> round 3.658；8.0*0.3048=2.4384 -> 2.438
    if problems:
        print("[selfcheck] 失败:")
        for p in problems:
            print("  -", p)
        return 1
    print("[selfcheck] 通过：2 帧篮球坐标抽取与单位换算全部符合预期（sample.json 缺失也可验证）。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="把 SportVU 逐帧 JSON 里的篮球轨迹抽成 CSV（见模块 docstring 的结构与坐标警告）。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--json", default=DEFAULT_JSON, help=f"输入 moments JSON（默认 {DEFAULT_JSON}）")
    p.add_argument("--out", default=DEFAULT_OUT, help=f"输出 CSV（默认 {DEFAULT_OUT}）")
    p.add_argument("--events", type=int, default=50, help="只抽前 N 个 event；<=0 表示全部（默认 50）")
    p.add_argument("--ball-entity", type=int, default=-1, help="篮球的 entity_id（默认 -1）")
    p.add_argument("--selfcheck", action="store_true", help="用内置假 JSON 验证抽取逻辑，不读写外部文件")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.selfcheck:
        return selfcheck()

    in_path = Path(args.json)
    if not in_path.exists():
        print(f"错误：找不到输入文件 {in_path.resolve()}。", file=sys.stderr)
        print("   先拿到该场的 moments JSON，再 `python extract.py --json <文件>`；或跑 `python extract.py --selfcheck` 验证逻辑。", file=sys.stderr)
        return 2

    try:
        with in_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"错误：{in_path} 不是合法 JSON（{exc}）。请确认解压后的真实文件名与内容。", file=sys.stderr)
        return 2

    rows = extract_ball_rows(data, events_limit=args.events, ball_entity_id=args.ball_entity)
    if not rows:
        print(
            f"警告：在 {in_path.name} 的前 {args.events if args.events > 0 else '所有'} event 里，"
            f"没找到 entity_id={args.ball_entity} 的篮球帧——可能 entity_id 不对，或该 JSON 不含球。",
            file=sys.stderr,
        )

    df = pd.DataFrame(rows, columns=COLUMNS)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(
        f"提取完成：{len(df)} 行帧写入 {out_path.name}"
        f"（处理 {args.events if args.events > 0 else len(data.get('events', []))} event，"
        f"篮球 entity_id={args.ball_entity}）。"
    )
    print(
        "提醒：x_m/y_m/z_m 是数据源原始坐标系(英尺→米)，与项目 3D 模型坐标不同，"
        "接 data_prep.py 前请先按 DATA_SPECIFICATION.md 记录轴约定与时间戳精度。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
