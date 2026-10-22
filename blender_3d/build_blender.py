import bpy, math, json, os
import numpy as np
from mathutils import Vector, Matrix

D   = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(D, "out")
os.makedirs(OUT, exist_ok=True)
FPS = 60.0
BALL_R, RIM_R, RIM_H, RIM_CX, BOARD_T = 0.12, 0.225, 3.05, -0.375, 0.03
BB_W, BB_H, BB_BOT = 1.8, 1.05, 2.9
BB_CY = BB_BOT + BB_H/2
PARK = -40.0

shots = json.load(open(os.path.join(D, "shots.json"), encoding="utf-8"))
order = ["swish", "board-in", "rim-in"]
caps = {"swish":    "SHOT 1 / SWISH - no contact, clean through",
        "board-in": "SHOT 2 / BOARD-IN - hits backboard, then rim (e = 0.70)",
        "rim-in":   "SHOT 3 / RIM-IN - bounced off the rim, still drops in"}

def P(x, y, z): return Vector((x, -z, y))

def mk_mat(name, color, rough=0.5, metal=0.0, alpha=1.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, alpha)
        bsdf.inputs["Roughness"].default_value = rough
        try: bsdf.inputs["Metallic"].default_value = metal
        except Exception: pass
    try: m.blend_method = 'BLEND'
    except Exception:
        try: m.blend_mode = 'BLEND'
        except Exception: pass
    return m

mat_skin  = mk_mat("skin",  (0.60, 0.35, 0.20))
mat_ball  = mk_mat("ball",  (0.72, 0.25, 0.04), rough=0.55)
mat_seam  = mk_mat("seam",  (0.02, 0.02, 0.02))
mat_rim   = mk_mat("rim",   (0.85, 0.15, 0.10), rough=0.35, metal=0.6)
mat_net   = mk_mat("net",   (0.90, 0.90, 0.90), rough=0.6)
mat_board = mk_mat("board", (0.90, 0.95, 1.00), rough=0.05, alpha=0.30)
mat_frame = mk_mat("frame", (0.05, 0.05, 0.05))
mat_white = mk_mat("white", (0.90, 0.90, 0.90))
mat_floor = mk_mat("floor", (0.55, 0.33, 0.14), rough=0.45)
mat_metal = mk_mat("metal", (0.35, 0.35, 0.38), rough=0.4, metal=0.8)
tr_colors = {"swish": (0.1, 0.6, 0.9), "board-in": (0.9, 0.5, 0.05), "rim-in": (0.2, 0.8, 0.3)}
jersey_col = {"swish": (0.10, 0.12, 0.55), "board-in": (0.60, 0.06, 0.10), "rim-in": (0.05, 0.42, 0.12)}

# ------------------------- scene reset -------------------------
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
sc = bpy.context.scene
sc.frame_start = 1
sc.render.fps = 60
sc.unit_settings.system = 'METRIC'

def bar(name, loc, size, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=tuple(loc))
    o = bpy.context.object; o.name = name
    o.scale = (size[0], size[1], size[2])
    o.data.materials.append(mat); return o

def act_fcurves(obj):
    a = obj.animation_data.action
    return [f for L in a.layers for s in L.strips for cb in s.channelbags for f in cb.fcurves]

def insert_key(obj, path, frame, value):
    """value: tuple for 3-prop or float for collection bools via setattr fallback"""
    try:
        if isinstance(value, tuple):
            setattr(obj, path, value)
        else:
            getattr(obj, path).__class__  # noop
            setattr(obj, path, value)
    except TypeError:
        pass
    try:
        obj.keyframe_insert(path, frame=frame)
    except Exception:
        obj.keyframe_insert(data_path=path, frame=frame)

def fix_interp(obj, path, const_frames):
    for fc in act_fcurves(obj):
        if fc.data_path != path:
            continue
        for kp in fc.keyframe_points:
            fr = int(round(kp.co[0] + 1e-4))
            kp.interpolation = 'CONSTANT' if fr in const_frames else 'LINEAR'
        fc.keyframe_points.update()

PARK_Z = lambda: PARK

def win_obj(obj, s0, s1):
    """park below floor outside [s0,s1]; visible inside"""
    x, y, z = tuple(obj.location)
    insert_key(obj, "location", s0-1, (x, y, PARK))
    insert_key(obj, "location", s0,   (x, y, z))
    insert_key(obj, "location", s1,   (x, y, z))
    insert_key(obj, "location", s1+1, (x, y, PARK))
    fix_interp(obj, "location", {s0-1, s1})

# ------------------------- environment -------------------------
bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
fl = bpy.context.object; fl.name = "Floor"; fl.data.materials.append(mat_floor)

# backboard (thin box at repo x=0 => blender X=0), glass
bpy.ops.mesh.primitive_cube_add(size=1, location=(BOARD_T/2, 0, BB_CY))
bb = bpy.context.object; bb.name = "Backboard"
bb.scale = (BOARD_T, BB_W, BB_H); bb.data.materials.append(mat_board)

BX = -BOARD_T - 0.004
# outer frame + inner rectangle painted on shooter side. size = (X depth, Y width, Z height)
for nm, yo, zo, wy, hz in [
    ("BB_Top",    0,        BB_CY+BB_H/2-0.01, BB_W,   0.02),
    ("BB_Bot",    0,        BB_CY-BB_H/2+0.01, BB_W,   0.02),
    ("BB_L",     -BB_W/2+0.01, BB_CY,         0.02,   BB_H),
    ("BB_R",      BB_W/2-0.01, BB_CY,         0.02,   BB_H)]:
    bar(nm, (BX, yo, zo), (0.008, wy, hz), mat_frame)
iw, ih = 0.593, 0.457
ib = 3.05 + 0.15
for nm, yo, zo, wy, hz in [
    ("IN_Bot", 0, ib+0.01,  iw, 0.02), ("IN_Top", 0, ib+ih-0.01, iw, 0.02),
    ("IN_L",  -iw/2+0.01, (ib+ih)/2, 0.02, ih), ("IN_R", iw/2-0.01, (ib+ih)/2, 0.02, ih)]:
    bar(nm, (BX, yo, zo), (0.008, wy, hz), mat_white)

# rim + net + support
bpy.ops.mesh.primitive_torus_add(major_radius=RIM_R, minor_radius=0.011,
                                 location=tuple(P(RIM_CX, RIM_H, 0)),
                                 rotation=(math.pi/2, 0, 0))
rim = bpy.context.object; rim.name = "Rim"; rim.data.materials.append(mat_rim)

cu = bpy.data.curves.new("Net", 'CURVE'); cu.dimensions = '3D'
cu.bevel_depth = 0.0018; cu.bevel_resolution = 1
nR, depth, r_top, r_bot, rings = 24, 0.42, RIM_R, 0.14, 4
def add_spline(points):
    s = cu.splines.new('POLY'); s.points.add(len(points)-1)
    for k, p in enumerate(points): s.points[k].co = (*p, 1.0)
def rr(j): return r_top + (r_bot - r_top)*j/rings
for j in range(rings+1):
    r = rr(j)
    add_spline([(RIM_CX + r*math.cos(2*math.pi*i/nR), r*math.sin(2*math.pi*i/nR),
                 RIM_H - depth*j/rings) for i in range(nR+1)])
for i in range(nR):
    a = 2*math.pi*i/nR
    add_spline([(RIM_CX + rr(j)*math.cos(a), rr(j)*math.sin(a), RIM_H - depth*j/rings)
                for j in range(rings+1)])
neto = bpy.data.objects.new("Net", cu); bpy.context.collection.objects.link(neto)
neto.data.materials.append(mat_net)

bpy.ops.mesh.primitive_cylinder_add(radius=0.08, depth=4.20, location=(1.45, 0, 2.10))
post = bpy.context.object; post.name = "Post"; post.data.materials.append(mat_metal)
bar("Arm", (0.74, 0, 3.98), (1.34, 0.10, 0.10), mat_metal)
bar("ArmD", (0.06, 0, 3.90), (0.09, 0.08, 0.25), mat_metal)

# ------------------------- loads & segments -------------------------
GAP = 45
data, segs, info = {}, {}, []
tg = 1
for kind in order:
    csv = np.genfromtxt(os.path.join(D, f"traj_{kind}.csv"), delimiter=",", skip_header=1)
    data[kind] = csv
    s1 = int(round(float(csv[-1, 0]))) + (tg - 1)
    segs[kind] = (tg, s1); info.append(dict(kind=kind, s0=tg, s1=s1, off=tg-1,
                                             dist=shots[kind]["dist_to_board"],
                                             angle=shots[kind]["angle"],
                                             speed=shots[kind]["speed"],
                                             spin=shots[kind]["spin"]))
    tg = s1 + GAP
TOTAL = tg - GAP + 30
sc.frame_end = TOTAL

# ------------------------- balls / players / labels -------------------------
def build_ball(kind, off):
    csv = data[kind]; spin = shots[kind]["spin"]
    first = P(*tuple(csv[0, 1:4]))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=BALL_R, segments=48, ring_count=32,
                                         location=tuple(first))
    b = bpy.context.object; b.name = "Ball_" + kind
    b.data.materials.append(mat_ball)
    for p in b.data.polygons: p.use_smooth = True
    def ring(major, rot, offset=(0, 0, 0)):
        bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=0.0025,
                                         location=(0, 0, 0), rotation=rot)
        t = bpy.context.object; t.data.materials.append(mat_seam)
        t.location = offset; t.parent = b
        t.matrix_parent_inverse = Matrix.Translation(-first)
    ring(BALL_R, (0, 0, 0))
    ring(BALL_R, (0, math.pi/2, 0))
    d = 0.055; rr2 = math.sqrt(BALL_R**2 - d**2)
    ring(rr2, (math.pi/2, 0, 0), offset=(0, -d, 0))
    ring(rr2, (math.pi/2, 0, 0), offset=(0, d, 0))
    frames = np.round(csv[:, 0]).astype(int) + off
    uniq, idx = np.unique(frames, return_index=True)
    rows = csv[idx]; t_arr = (rows[:, 0] - off - 1)/FPS
    bx, by, bz = rows[:, 1], -rows[:, 3], rows[:, 2]
    f0, f1 = int(uniq[0]), int(uniq[-1])
    insert_key(b, "location", off, (bx[0], by[0], PARK))
    insert_key(b, "rotation_euler", off, (0.0, -spin*t_arr[0], 0.0))
    for i, f in enumerate(uniq):
        fr = int(f)
        zz = PARK if fr == off else bz[i]
        insert_key(b, "location", fr, (bx[i], by[i], zz))
        rot3 = (0.0, -spin*t_arr[i], 0.0)
        insert_key(b, "rotation_euler", fr, rot3)
    insert_key(b, "location", f1+1, (bx[-1], by[-1], PARK))
    insert_key(b, "rotation_euler", f1+1, (0.0, -spin*t_arr[-1], 0.0))
    fix_interp(b, "location", {off, f1})
    fix_interp(b, "rotation_euler", {off, f1+1})
    return f0, f1

def build_player(kind, dist):
    xc = -dist - 0.40
    xh, zh = -dist + 0.02, 1.98
    parts = []
    def cyl(nm, p1, p2, r, mat):
        v1, v2 = Vector(p1), Vector(p2); dv = v2 - v1; L = dv.length
        bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=L, location=tuple((v1+v2)/2))
        o = bpy.context.object; o.name = nm
        o.rotation_mode = 'QUATERNION'; o.rotation_quaternion = dv.to_track_quat('Z', 'Y')
        for p in o.data.polygons: p.use_smooth = True
        o.data.materials.append(mat); parts.append(o)
    hipL, hipR = (xc-0.02, -0.11, 0.95), (xc-0.02, 0.11, 0.95)
    shoL, shoR = (xc+0.04, -0.24, 1.58), (xc+0.04, 0.24, 1.58)
    elbL, elbR = (xc+0.34, -0.22, 1.30), (xc+0.30, 0.28, 1.42)
    wrL, wrR = (xh, -0.10, zh), (xh+0.02, 0.12, 1.86)
    for nm, p1, p2, r in [("LegL", hipL, (xc-0.06, -0.12, 0.05), 0.07),
                          ("LegR", hipR, (xc-0.06, 0.12, 0.05), 0.07),
                          ("ArmL", shoL, elbL, 0.055), ("ArmR", shoR, elbR, 0.055),
                          ("ForeL", elbL, wrL, 0.045), ("ForeR", elbR, wrR, 0.045)]:
        cyl(nm, p1, p2, r, mat_skin)
    cyl("Torso", (xc, 0, 0.95), (xc, 0, 1.62), 0.17,
        mk_mat(f"j_{kind}", jersey_col[kind], 0.5))
    for nm, p in [("HandL", wrL), ("HandR", wrR)]:
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.055, location=p)
        h = bpy.context.object; h.name = nm + "_" + kind
        h.data.materials.append(mat_skin)
        for pl in h.data.polygons: pl.use_smooth = True
        parts.append(h)
    for nm, xx in [("FootL", -0.12), ("FootR", 0.12)]:
        bar(nm + "_" + kind, (xc-0.10, xx, 0.03), (0.24, 0.09, 0.06), mat_frame)
        parts.append(bpy.context.object)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.13, location=(xc-0.01, 0, 1.87))
    head = bpy.context.object; head.name = "Head_" + kind
    head.data.materials.append(mat_skin)
    for p in head.data.polygons: p.use_smooth = True
    parts.append(head)
    coll = bpy.data.collections.new("Player_" + kind)
    sc.collection.children.link(coll)
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
    root = bpy.context.object; root.name = "PlayerRoot_" + kind
    for o in parts:
        for c in o.users_collection: c.objects.unlink(o)
        coll.objects.link(o)
        if o.parent is None:
            o.parent = root
            o.matrix_parent_inverse = root.matrix_world.inverted()
    root.name = "PlayerRoot_" + kind
    return coll, root

def add_text(name, body, loc, size, mat):
    c = bpy.data.curves.new(name, 'FONT'); c.body = body; c.size = size; c.align_x = 'CENTER'
    o = bpy.data.objects.new(name, c); bpy.context.collection.objects.link(o)
    o.location = loc; o.rotation_euler = (math.pi/2, 0, 0); o.data.materials.append(mat)
    return o

for it in info:
    kind = it["kind"]; off = it["off"]; sh = shots[kind]
    l0, l1 = build_ball(kind, off)
    it["l0"], it["l1"] = l0, l1
    csv = data[kind]
    msk = np.zeros(len(csv), bool); msk[::4] = True; msk[-1] = True
    rows = csv[msk]
    c = bpy.data.curves.new("Traj_"+kind, 'CURVE'); c.dimensions = '3D'; c.bevel_depth = 0.006
    spn = c.splines.new('POLY'); spn.points.add(len(rows)-1)
    for k, r in enumerate(rows): spn.points[k].co = (r[1], -r[3], r[2], 1.0)
    traj = bpy.data.objects.new("Traj_"+kind, c)
    bpy.context.collection.objects.link(traj)
    traj.data.materials.append(mk_mat(f"tr_{kind}", tr_colors[kind], 0.4))
    win_obj(traj, it["s0"], it["s1"])
    pc, root = build_player(kind, it["dist"])
    win_obj(root, it["s0"], it["s1"])
    cap = add_text("Cap_"+kind, caps[kind], (-3.0, -1.1, 4.02), 0.085, mat_white)
    par = add_text("Par_"+kind,
        f"v0={sh['speed']:.2f} m/s   theta={sh['angle']:.1f} deg   backspin w={sh['spin']:.0f} rad/s   "
        f"to-board={sh['dist_to_board']:.2f} m   release 2.00 m   CD=0.50 rho=1.225   e=0.70",
        (-3.0, -1.1, 3.78), 0.062, mat_white)
    for tt in (cap, par): win_obj(tt, it["s0"], it["s1"])

add_text("Lbl_hoop", "RIM 3.05 m", (-0.375, -0.45, 2.28), 0.08, mat_white)
add_text("Lbl_bb", "BACKBOARD e=0.70", (0.0, -1.20, 2.72), 0.09, mat_white)
add_text("Lbl_src",
         "Physics: github.com/dbzyw/comp-1110-group-project - RK4, air drag CD=0.50, Magnus backspin, collisions e=0.70",
         (-4.3, -0.5, 0.42), 0.045, mat_white)

# ------------------------- camera & lights -------------------------
cam_data = bpy.data.cameras.new("Cam"); cam_data.lens = 32
cam = bpy.data.objects.new("Camera", cam_data); bpy.context.collection.objects.link(cam)
cam.location = (-3.4, -7.4, 2.05)
d = Vector((-1.8, 0.0, 2.30)) - Vector(cam.location)
cam.rotation_mode = 'QUATERNION'; cam.rotation_quaternion = d.to_track_quat('-Z', 'Y')
sc.camera = cam

bpy.ops.object.light_add(type='SUN', location=(0, 0, 8))
sun = bpy.context.object; sun.data.energy = 3.2
sun.rotation_euler = (math.radians(40), math.radians(12), math.radians(140))
fill_data = bpy.data.lights.new("Fill", 'AREA')
try: fill_data.size = 4.0
except Exception:
    try: fill_data.size_x = fill_data.size_y = 4.0
    except Exception: pass
fill_data.energy = 320
fill = bpy.data.objects.new("Fill", fill_data)
bpy.context.collection.objects.link(fill)
fill.location = (-2.5, -5.0, 3.2)
fd = Vector((-0.8, 0, 2.4)) - Vector(fill.location)
fill.rotation_mode = 'QUATERNION'; fill.rotation_quaternion = fd.to_track_quat('-Z', 'Y')

w = sc.world
try:
    bg = w.node_background
    bg.inputs[0].default_value = (0.35, 0.45, 0.60, 1); bg.inputs[1].default_value = 0.5
except Exception:
    pass

# ------------------------- render -------------------------
r = sc.render
r.resolution_x, r.resolution_y, r.resolution_percentage = 1280, 720, 100
r.fps = 60
for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
    try:
        r.engine = engine; break
    except Exception:
        continue
try:
    e = sc.eevee
    try: e.taa_render_samples = 32
    except Exception: pass
    try: e.ray_tracing_enabled = True
    except Exception: pass
except Exception:
    pass
r.use_motion_blur = True; r.motion_blur_shutter = 0.45
r.image_settings.file_format = 'PNG'

def contact_frames(kind, off):
    csv = data[kind]; x, y, z = csv[:, 1], csv[:, 2], csv[:, 3]
    out = {}
    if kind == "board-in":
        d1 = np.where(x < -BALL_R+0.001, np.abs(x + BALL_R), 999)
        i = int(np.argmin(d1)); out["board"] = int(round(csv[i, 0])) + off
    hz = np.hypot(x - RIM_CX, z)
    d2 = np.abs(hz - RIM_R) + 2*np.abs(y - RIM_H)
    i = int(np.argmin(d2)); out["rim"] = int(round(csv[i, 0])) + off
    return out

qc = []
for it in info:
    kind = it["kind"]; sh = shots[kind]
    cf = contact_frames(kind, it["off"])
    scf = int(round(sh["score_frame"])) + it["off"] if sh.get("score_frame") else None
    qc.append((f"qc_{kind}_launch", it["s0"] + 2))
    qc.append((f"qc_{kind}_mid", it["s0"] + (it["s1"] - it["s0"])//2))
    for nm, ff in cf.items():
        qc.append((f"qc_{kind}_contact_{nm}", max(it["s0"]+2, ff)))
    if scf: qc.append((f"qc_{kind}_score", scf))
    qc.append((f"qc_{kind}_end", it["s1"]))

for nm, ff in qc:
    sc.frame_current = ff
    r.filepath = os.path.join(OUT, nm + ".png")
    r.image_settings.file_format = 'PNG'
    bpy.ops.render.render(write_still=True)
    print("still:", nm, ff, flush=True)

r.ffmpeg.format = 'MPEG4'; r.ffmpeg.codec = 'H264'
r.ffmpeg.constant_rate_factor = 'HIGH'
try: r.ffmpeg.use_lossless_compress = False
except Exception: pass
if os.environ.get("BB_SKIP_VIDEO"):
    print("video skipped (BB_SKIP_VIDEO)", flush=True)
else:
    r.image_settings.file_format = 'PNG'
    FRD = os.path.join(OUT, "frames")
    os.makedirs(FRD, exist_ok=True)
    r.filepath = os.path.join(FRD, "frame_")
    bpy.ops.render.render(animation=True)
    import subprocess
    dst = os.path.join(OUT, "shot3d.mp4")
    cmd = ["ffmpeg", "-y", "-framerate", "60", "-start_number", str(sc.frame_start),
           "-i", os.path.join(FRD, "frame_%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-crf", "18", dst]
    p = subprocess.run(cmd, capture_output=True)
    print("ffmpeg rc:", p.returncode, p.stderr[-200:] if p.returncode else "", flush=True)
    if os.path.exists(dst):
        print("video:", dst, os.path.getsize(dst), flush=True)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(D, "basketball_shot3d.blend"))
print("DONE frames:", TOTAL, "segs:", [(i["kind"], i["s0"], i["s1"]) for i in info], flush=True)
