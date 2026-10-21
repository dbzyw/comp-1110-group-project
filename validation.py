"""
validation.py — 投篮模型验证与统计指标

使用二分类 made/miss + Wilson CI + kappa + 4x4 多分类混淆矩阵，并包含：

    * load_shots: 缺列时给出“缺哪一列、期望格式”的友好报错 (原版直接 KeyError);
      跳过空行; shot_id 重复时警告; 每行数值要求有限
    * run_validation: 单条出手参数非法 (simulate_shot 会拒绝 y<0 等) 不再
      让整场验证崩溃 —— 该条记为 error、参与二分类计为“不一致”、不进多分类
      矩阵, 最后统一汇报; z (CI 分位数) 校验
    * make_dummy_data: 输出目录不存在时给出清晰报错; n>0 校验;
      correlated=True 时使用固定随机流生成可复现数据
    * CLI 新增: --correlated 生成自洽占位数据; selfcheck 模式在临时目录里
      生成 correlated dummy -> 跑全套指标 -> 断言一致率=100% (链路自检)

用法:
    python validation.py --make-dummy            # 生成 dummy_data.csv
    python validation.py --make-dummy --correlated
                                                          # 自洽占位 (应 100% 一致)
    python validation.py [数据.csv]              # 默认 dummy_data.csv
    python validation.py selfcheck               # 临时目录链路自检

数据格式与标签集合见 validation.py 的模块文档 (完全相同)。
"""

import csv
import math
import sys
from pathlib import Path

import numpy as np

from simulation import simulate_shot

# 结局标签 -> made / miss 归一化
_MADE_LABELS = {"swish", "bounce-in", "rim-in", "board-in", "made", "in"}
_MISS_LABELS = {"miss", "out", "no"}

# 多分类分析使用的"具体结局"子类; 旧标签 bounce-in/made/in 只能做二分类
_CANONICAL_MADE = {"swish": "swish", "rim-in": "rim-in", "board-in": "board-in"}
_CLASS_ORDER = ["swish", "rim-in", "board-in", "miss"]

# load_shots 期望的列 (缺任何一列都会给出明确报错)
REQUIRED_FIELDS = ("shot_id", "release_x", "release_y", "release_z",
                   "v0x", "v0y", "v0z", "backspin", "actual_outcome")


def _to_binary(label):
    """把任意结局标签归一化为 "made" 或 "miss"。"""
    lab = str(label).strip().lower()
    if lab in _MADE_LABELS:
        return "made"
    if lab in _MISS_LABELS:
        return "miss"
    raise ValueError(f"未知的结局标签: {label!r}")


def _canonical(label):
    """
    把结局标签规范化为 4 类之一 (swish/rim-in/board-in/miss)。
    若标签是"命中但未细分子类"的旧标签 (bounce-in/made/in), 返回 None
    (这些样本只参与二分类, 不参与多分类混淆矩阵)。
    """
    lab = str(label).strip().lower()
    if lab in _CANONICAL_MADE:
        return _CANONICAL_MADE[lab]
    if lab in _MISS_LABELS:
        return "miss"
    return None


def wilson_ci(k, n, z=1.96):
    """
    Wilson 二项比例置信区间 (k 次成功 / n 次试验)。

    相比朴素 p ± z·sqrt(p(1-p)/n), Wilson 区间在小样本或比例接近 0/1 时
    不会越出 [0,1], 更适合 20–30 发这种小样本的误差量化。
    返回 (lower, upper); n<=0 时返回 (nan, nan)。
    """
    if n <= 0:
        return (float("nan"), float("nan"))
    if not (0.0 <= k <= n):
        raise ValueError(f"k must be within [0, n], got k={k!r}, n={n!r}")
    if not math.isfinite(z) or z <= 0.0:
        raise ValueError(f"z must be a positive finite number, got {z!r}")
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n)) / denom
    return (centre - half, centre + half)


def load_shots(csv_path):
    """
    读取验证 CSV, 返回 shot 字典列表。

    改进版: 缺列 / 非数值 / 非有限 / 空行 / 未知标签 都会带着行号报错
    (原版: 缺列抛裸 KeyError, 坏行抛到 run_validation 的中途)。
    """
    shots = []
    seen_ids = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_FIELDS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(
                f"{csv_path} 缺少列 {missing}; 期望列 {list(REQUIRED_FIELDS)} "
                f"(见 validation.py 的‘数据格式标准’)")
        for lineno, row in enumerate(reader, start=2):
            if not any(v not in (None, "", " ") for v in row.values()):
                continue          # 跳过纯空行 (原版会把空行也算一条)
            try:
                sid = int(row["shot_id"])
                vals = [float(row[k]) for k in
                        ("release_x", "release_y", "release_z",
                         "v0x", "v0y", "v0z", "backspin")]
            except (TypeError, ValueError) as e:
                raise ValueError(
                    f"{csv_path} 第 {lineno} 行无法解析为数值: {e}") from e
            if not all(map(math.isfinite, vals)):
                raise ValueError(
                    f"{csv_path} 第 {lineno} 行含非有限数值 (NaN/inf): {vals}")
            outcome = str(row["actual_outcome"]).strip().lower()
            try:
                _to_binary(outcome)                     # 校验标签合法
            except ValueError as e:
                raise ValueError(f"{csv_path} 第 {lineno} 行: {e}") from e
            if sid in seen_ids:
                print(f"  警告: {csv_path} 第 {lineno} 行 shot_id={sid} 与第 "
                      f"{seen_ids[sid]} 行重复 (两条都会参与统计)")
            seen_ids[sid] = lineno
            shots.append({
                "shot_id": sid,
                "release_pos": vals[0:3],
                "release_vel": vals[3:6],
                "backspin": vals[6],
                "actual_outcome": outcome,
            })
    return shots


def predict(shot):
    """
    用物理引擎预测一条出手。

    返回 (predicted_outcome, predicted_binary):
        predicted_outcome : "swish" | "rim-in" | "board-in" | "miss"
        predicted_binary  : "made" | "miss"
    """
    res = simulate_shot(shot["release_pos"], shot["release_vel"], shot["backspin"])
    outcome = res["outcome"]
    return outcome, _to_binary(outcome)


def _per_class_metrics(cm):
    """
    由多分类混淆矩阵 cm (dict[actual][predicted]) 计算每类 precision/recall/F1。
    """
    metrics = {}
    for c in _CLASS_ORDER:
        tp = cm[c][c]
        fp = sum(cm[a][c] for a in _CLASS_ORDER if a != c)
        fn = sum(cm[c][p] for p in _CLASS_ORDER if p != c)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2.0 * precision * recall / (precision + recall)
              if (precision + recall) else 0.0)
        metrics[c] = {"tp": tp, "fp": fp, "fn": fn,
                      "precision": precision, "recall": recall, "f1": f1}
    return metrics


def run_validation(csv_path="dummy_data.csv", z=1.96):
    """
    读取 -> 预测 -> 对比, 输出严谨的误差量化指标。

    改进版: 单条出手参数非法不再让整场验证崩溃 —— 该条记 "error"、二分类计
    为不一致、不进多分类矩阵, 结尾统一汇报 (原版直接让异常冒出)。
    """
    if not Path(csv_path).is_file():
        raise FileNotFoundError(
            f"找不到验证数据 {csv_path}。用 `python validation.py "
            f"--make-dummy` 先生成一份占位数据。")
    shots = load_shots(csv_path)
    n = len(shots)
    if n == 0:
        print(f"错误: {csv_path} 为空 (0 条数据), 无法验证。")
        return None

    agree = 0
    tp = fp = fn = tn = 0
    rows = []
    errors = []            # (shot_id, 异常信息)

    # 多分类混淆矩阵 (swish / rim-in / board-in / miss)
    cm = {a: {p: 0 for p in _CLASS_ORDER} for a in _CLASS_ORDER}
    mc_used = 0

    for s in shots:
        try:
            pred_outcome, pred_bin = predict(s)
        except ValueError as e:
            # 参数非法 (如出手点 y<0、dt 越界): 记为 error, 二分类算不一致
            pred_outcome, pred_bin = "error", "miss"
            errors.append((s["shot_id"], str(e)))
        actual_outcome = s["actual_outcome"]
        actual_bin = _to_binary(actual_outcome)

        match = (pred_bin == actual_bin)
        agree += 1 if match else 0
        rows.append((s["shot_id"], actual_outcome, pred_outcome, match))

        if actual_bin == "made" and pred_bin == "made":
            tp += 1
        elif actual_bin == "made" and pred_bin == "miss":
            fn += 1
        elif actual_bin == "miss" and pred_bin == "made":
            fp += 1
        else:
            tn += 1

        a_c = _canonical(actual_outcome)
        p_c = _canonical(pred_outcome)
        if a_c is not None and p_c is not None:
            cm[a_c][p_c] += 1
            mc_used += 1

    accuracy = agree / n
    disagreement = 1.0 - accuracy

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0          # 灵敏度
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    f1 = (2.0 * precision * recall / (precision + recall)
          if (precision + recall) else 0.0)

    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    mcc = ((tp * tn - fp * fn) / denom) if denom > 0.0 else 0.0

    # 基线: 无信息率 (多数类) + 偶然一致 + Cohen's kappa
    p_actual_made = (tp + fn) / n
    p_pred_made = (tp + fp) / n
    p_chance = p_actual_made * p_pred_made + (1.0 - p_actual_made) * (1.0 - p_pred_made)
    kappa = (accuracy - p_chance) / (1.0 - p_chance) if p_chance < 1.0 else 0.0
    no_info_rate = max(p_actual_made, 1.0 - p_actual_made)

    ci_lo, ci_hi = wilson_ci(agree, n, z)

    # ---- 输出 ----
    print(f"读取 {n} 条投篮数据  ({csv_path})")
    print("=" * 70)
    print(f"{'shot':>4} | {'actual':>11} | {'predicted':>11} | 一致")
    for sid, a, p, m in rows:
        print(f"{sid:>4} | {a:>11} | {p:>11} | {'对' if m else '错'}")
    print("=" * 70)

    print("【二分类混淆矩阵】(阳性 = made):")
    print(f"                    预测 made   预测 miss")
    print(f"  实际 made          {tp:>6}      {fn:>6}")
    print(f"  实际 miss          {fp:>6}      {tn:>6}")
    print("-" * 70)
    print(f"一致率  Agreement Rate    = {agree}/{n} = {accuracy:.1%}")
    print(f"        Wilson 95% CI     = [{ci_lo:.1%}, {ci_hi:.1%}]")
    print(f"错误率  Disagreement Rate = {n - agree}/{n} = {disagreement:.1%}")
    print(f"精确率  Precision (made)  = {precision:.1%}")
    print(f"召回率  Recall (made)     = {recall:.1%}")
    print(f"特异度  Specificity       = {specificity:.1%}")
    print(f"F1 得分                    = {f1:.2f}")
    print(f"MCC (Matthews)            = {mcc:+.3f}")
    print("-" * 70)
    print(f"基线对照  无信息率(多数类) = {no_info_rate:.1%}")
    print(f"          偶然一致(期望)   = {p_chance:.1%}")
    print(f"          Cohen's kappa    = {kappa:+.3f}  (0=纯偶然, 1=完全一致)")

    if errors:
        print("-" * 70)
        print(f"[参数非法 {len(errors)} 条] 已按“不一致”计入二分类、未进多分类矩阵:")
        for sid, msg in errors[:10]:
            print(f"  shot {sid}: {msg}")
        if len(errors) > 10:
            print(f"  ... 另有 {len(errors) - 10} 条")

    if mc_used > 0:
        print("-" * 70)
        print(f"【多分类混淆矩阵】(swish/rim-in/board-in/miss, 参与样本 {mc_used}/{n}):")
        header = "实际\\预测 " + "".join(f"{c:>12}" for c in _CLASS_ORDER)
        print(header)
        for a in _CLASS_ORDER:
            print(f"{a:>9} " + "".join(f"{cm[a][p]:>12}" for p in _CLASS_ORDER))
        print("-" * 70)
        print("每类指标 (precision / recall / F1):")
        for c, m in _per_class_metrics(cm).items():
            if m["tp"] + m["fn"] == 0 and m["tp"] + m["fp"] == 0:
                print(f"  {c:>9}: 无样本 (n/a)")
            else:
                print(f"  {c:>9}: P={m['precision']:.1%}  R={m['recall']:.1%}  "
                      f"F1={m['f1']:.2f}  (tp={m['tp']}, fp={m['fp']}, fn={m['fn']})")
    else:
        print("-" * 70)
        print("(提示: 无具体子类标签, 跳过 swish/rim-in/board-in 多分类分析; "
              "请把 actual_outcome 标注为 swish/rim-in/board-in 以启用。)")

    return {
        "n": n,
        "agreement_rate": accuracy,
        "disagreement_rate": disagreement,
        "ci_low": ci_lo, "ci_high": ci_hi,
        "precision": precision, "recall": recall, "specificity": specificity,
        "f1": f1, "mcc": mcc, "kappa": kappa,
        "chance_agreement": p_chance, "no_information_rate": no_info_rate,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "multiclass_cm": cm,
        "multiclass_used": mc_used,
        "per_class": _per_class_metrics(cm) if mc_used else None,
        # 新增 (不影响上面任何指标): 逐行明细与非法参数条目
        "rows": rows,
        "errors": errors,
    }


def make_dummy_data(csv_path="dummy_data.csv", n=20, seed=0, correlated=False):
    """
    生成 n 条占位数据, 写入 CSV。 (随机流与 validation.py 逐位一致)

    参数
    ----
    correlated : bool
        False (默认): actual_outcome 为【随机占位结果】, 与出手参数无关。
            仅用于跑通流程; 此时 Agreement Rate ≈ 随机猜测基线 (约 30-50%),
            不代表模型真实水平。
        True: actual_outcome 直接取【模型预测结果】(自洽测试), 预期
            Agreement Rate ≈ 100%, 用于检查“读数据 -> 预测 -> 对比”链路无误。

    正式验证请把真实拍摄的出手参数 + 真实结果填进同一格式的 CSV。
    改进版: 输出目录不存在时给出清晰报错; n 校验。
    """
    n = int(n)
    if n <= 0:
        raise ValueError(f"n must be positive, got {n!r}")
    out_path = Path(csv_path)
    if str(out_path.parent) not in ("", ".") and not out_path.parent.is_dir():
        raise FileNotFoundError(f"输出目录不存在: {out_path.parent}")

    rng = np.random.default_rng(seed)

    header = ["shot_id", "release_x", "release_y", "release_z",
              "v0x", "v0y", "v0z", "backspin", "actual_outcome"]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for i in range(n):
            # 随机但真实的出手参数 (标准罚球附近)
            release_x = -4.57 + rng.normal(0.0, 0.03)
            release_y = 2.0 + rng.normal(0.0, 0.05)
            release_z = rng.normal(0.0, 0.05)

            speed = 7.5 + rng.normal(0.0, 0.10)
            angle = np.deg2rad(51.0 + rng.normal(0.0, 1.5))
            v0x = speed * np.cos(angle)
            v0y = speed * np.sin(angle)
            v0z = rng.normal(0.0, 0.05)

            backspin = 23.0 + rng.normal(0.0, 3.0)

            if correlated:
                # 自洽: 用模型结果当"真实结果"
                outcome = simulate_shot([release_x, release_y, release_z],
                                        [v0x, v0y, v0z], backspin)["outcome"]
            else:
                # 随机占位结果 (具体子类, 便于演示多分类分析)
                outcome = rng.choice(["swish", "rim-in", "board-in", "miss"],
                                     p=[0.45, 0.15, 0.10, 0.30])

            w.writerow([i + 1,
                        f"{release_x:.4f}", f"{release_y:.4f}", f"{release_z:.4f}",
                        f"{v0x:.4f}", f"{v0y:.4f}", f"{v0z:.4f}",
                        f"{backspin:.4f}", outcome])

    print(f"已生成 {csv_path}: {n} 条占位数据"
          + (" (correlated: 真实结果=模型预测)" if correlated else ""))
    return csv_path


if __name__ == "__main__":
    args = [a.lower() for a in sys.argv[1:]]

    if "selfcheck" in args:
        # Generate correlated dummy data and check the validation pipeline.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "dummy.csv"
            make_dummy_data(str(path), n=20, seed=7, correlated=True)
            metrics = run_validation(str(path))
            assert metrics is not None, "dummy should produce validation metrics"
            ok = (metrics["agreement_rate"] == 1.0
                  and not metrics["errors"] and metrics["kappa"] > 0.99)
            print(f"[{'OK' if ok else 'XX'}] correlated dummy: agreement "
                  f"{metrics['agreement_rate']:.1%}, kappa "
                  f"{metrics['kappa']:+.3f}, errors={len(metrics['errors'])}")
            sys.exit(0 if ok else 1)

    if "--make-dummy" in args or "--dummy" in args:
        make_dummy_data(correlated="--correlated" in args)
    else:
        rest = [a for a in sys.argv[1:] if not a.startswith("-")]
        path = rest[0] if rest else "dummy_data.csv"
        run_validation(path)
