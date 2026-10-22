import json, math, os, sys
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from physics import integrate, release_velocity, BALL_RADIUS
from simulation import simulate_shot

FPS = 60.0
HERE = os.path.dirname(os.path.abspath(__file__))
DT_S = 1e-3      # 正式轨迹
DT_Q = 2e-3      # 快速粗扫用

def try_shot(dist, angle, speed, spin=23.0, dt=DT_Q):
    r = simulate_shot(np.array([-dist, 2.0, 0.0]), release_velocity(speed, angle),
                      spin, dt=dt)
    return r

def coarse_sweep(kind, dists, angles, speeds, spin=23.0):
    hits = []
    for dist in dists:
        for a in angles:
            for v in speeds:
                r = try_shot(dist, a, v, spin)
                o = r["outcome"]
                if kind == "swish" and o == "swish":
                    return dict(dist=dist, angle=a, speed=v, spin=spin, r=r)
                if kind == "rim-in" and o == "rim-in":
                    return dict(dist=dist, angle=a, speed=v, spin=spin, r=r)
                if kind == "board-in" and o == "board-in":
                    return dict(dist=dist, angle=a, speed=v, spin=spin, r=r)
                hits.append((dist, a, v, o))
    return None

def refine(s):
    # 在粗扫点附近用更细的速度网格找到同类且碰撞最少的干净样本
    best = None
    for da in np.arange(-1.0, 1.01, 0.5):
        for dv in np.arange(-0.15, 0.151, 0.05):
            r = try_shot(s["dist"], s["angle"]+da, s["speed"]+dv, s["spin"])
            if r["outcome"] == s["r"]["outcome"]:
                nc = len(r["contacts"])
                if best is None or nc < best[0]:
                    best = (nc, s["angle"]+da, s["speed"]+dv, r)
    nc, a, v, r = best
    return dict(dist=s["dist"], angle=float(a), speed=float(v), spin=s["spin"], r=r)

def full_shot(dist, angle, speed, spin=23.0):
    v0 = release_velocity(speed, angle)
    res = simulate_shot(np.array([-dist, 2.0, 0.0]), v0, spin, dt=DT_S)
    t, st = res["times"], res["states"]
    made = res["outcome"] in ("swish", "rim-in", "board-in")
    if made:
        last = st[-1]
        t2, s2 = integrate(last[0:3].copy(), last[3:6].copy(), spin, dt=DT_S,
                           t_max=3.0, stop=lambda s: s[1] < BALL_RADIUS)
        t = np.concatenate([t, t[-1] + t2[1:]])
        st = np.concatenate([st, s2[1:]])
        # 补: 球心贴地停止后, 视觉落地帧用 t 末尾
    return res, t, st, made

def dump_csv(path, t, st):
    data = np.column_stack((t * FPS + 1.0, st))
    np.savetxt(path, data, delimiter=",", comments="", fmt="%.6f",
               header="frame,x,y,z,vx,vy,vz")

print("default repo test:", end=" ")
r0 = try_shot(4.57, 51.0, 7.5, dt=DT_S)
print(r0["outcome"], "|", r0["reason"], "|", r0["contacts"])

plan = {}
c = coarse_sweep("swish", [4.57, 4.21, 4.975],
                 np.arange(48.0, 56.01, 1.0), np.arange(7.0, 9.01, 0.2))
if c: plan["swish"] = c
c = coarse_sweep("rim-in", [4.57, 4.21, 4.975, 5.4],
                 np.arange(43.0, 56.01, 1.0), np.arange(7.0, 9.21, 0.2))
if c: plan["rim-in"] = c
c = coarse_sweep("board-in", [3.4, 3.8, 4.2, 4.57],
                 np.arange(30.0, 46.01, 2.0), np.arange(6.5, 10.01, 0.2))
if c: plan["board-in"] = c

out = {}
for kind, s in plan.items():
    try:
        rs = refine(s)
    except Exception:
        rs = s
    res, t, st, made = full_shot(rs["dist"], rs["angle"], rs["speed"], rs["spin"])
    print(f"== {kind} == dist={rs['dist']:.2f} angle={rs['angle']:.2f} speed={rs['speed']:.2f} "
          f"-> {res['outcome']} contacts={res['contacts']} reason={res['reason']}")
    dump_csv(os.path.join(HERE, f"traj_{kind}.csv"), t, st)
    out[kind] = dict(dist_to_board=rs["dist"], angle=rs["angle"], speed=rs["speed"],
                     spin=rs["spin"], outcome=res["outcome"],
                     contacts=[str(x) for x in res["contacts"]],
                     reason=res["reason"], made=bool(made),
                     t_end=float(t[-1]), points=int(len(t)),
                     score_frame=None)
    # 进球时刻帧 (相对本段 0-based, 用正式 dt 的 times 里首次穿筐)
    if made:
        sm = np.where((st[1:,1] <= 3.05) & (st[:-1,1] > 3.05))[0]
        if len(sm): out[kind]["score_frame"] = float(t[sm[0]] * FPS + 1.0)

with open(os.path.join(HERE, "shots.json"), "w", encoding="utf-8") as fo:
    json.dump(out, fo, indent=2, ensure_ascii=False)
print("saved shots.json +", list(out.keys()))
