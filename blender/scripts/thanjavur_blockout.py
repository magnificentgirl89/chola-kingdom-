"""
Hobby Project 1 - Chola Kingdom
Site 01: Brihadeeswarar Temple, Thanjavur (c. 1010 CE, Rajaraja Chola I)

Procedural BLOCKOUT of the temple complex: correct proportions and massing,
golden-hour lighting and two cameras. This is stage 1 of the pipeline
(blockout -> detail kitbash -> materials -> set dressing -> lighting/FX).

Run inside Blender (5.x):
    blender -b -P blender/scripts/thanjavur_blockout.py -- --render renders/thanjavur
or interactively: open Blender > Scripting tab > open this file > Run Script.

Options after "--":
    --render <prefix>   render every camera to <prefix>_<camera>.png
    --save <file.blend> save the generated scene
    --samples N         Cycles samples (default 48)
    --res WxH           resolution (default 1600x900)

All sizes are metres and approximate (from published plans/surveys);
the X axis points east, the temple faces east.
"""

import math
import sys

import bpy  # noqa: F401  (must load before bmesh when used as a module)
import bmesh
import bpy
from mathutils import Matrix, Vector

# --------------------------------------------------------------------------
# Scene helpers
# --------------------------------------------------------------------------


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.unit_settings.system = "METRIC"
    return scn


_mesh_cache = {}


def _mesh(kind):
    """Unit meshes shared by every object (keeps the file light)."""
    if kind in _mesh_cache:
        return _mesh_cache[kind]
    me = bpy.data.meshes.new(kind)
    bm = bmesh.new()
    if kind == "cube":  # 1x1x1, origin at bottom centre
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, 0.5))
    elif kind == "dome":  # hemisphere, radius 0.5, origin at base
        bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=0.5)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -1e-4], context="VERTS")
    elif kind == "octadome":  # octagonal stupi (Chola shikhara)
        bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=8, radius=0.5)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -1e-4], context="VERTS")
    elif kind == "barrel":  # shala vault, length along X
        bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.5, radius2=0.5, depth=1.0)
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0),
                         matrix=Matrix.Rotation(math.pi / 2, 3, "Y"))
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -1e-4], context="VERTS")
    elif kind == "cyl":  # pillar, radius 0.5, height 1
        bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.5, radius2=0.5, depth=1.0)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, 0.5))
    elif kind == "kalasha":  # finial pot
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.5)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, 0.5))
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = kind in ("dome", "barrel", "kalasha")
    _mesh_cache[kind] = me
    return me


_collections = {}


def coll(name):
    if name not in _collections:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
        _collections[name] = c
    return _collections[name]


def part(kind, name, loc, size, mat, collection="Temple", rot_z=0.0):
    ob = bpy.data.objects.new(name, _mesh(kind))
    ob.location = loc
    ob.scale = size
    ob.rotation_euler[2] = rot_z
    coll(collection).objects.link(ob)
    if mat:
        if not ob.data.materials:
            ob.data.materials.append(None)
        # per-object material so shared unit meshes can differ
        ob.material_slots[0].link = "OBJECT"
        ob.material_slots[0].material = mat
    return ob


def box(name, center_xy, z0, w, d, h, mat, collection="Temple"):
    return part("cube", name, (center_xy[0], center_xy[1], z0), (w, d, h), mat, collection)


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------


def stone_material(name, col_a, col_b, rough=0.85, scale=0.35, bump=0.35):
    """Weathered granite: two-tone noise + dirt streaks + bump. World-space."""
    m = bpy.data.materials.new(name)
    nt = m.node_tree if m.node_tree else None
    if nt is None:
        m.use_nodes = True
        nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    geo = nodes.new("ShaderNodeNewGeometry")

    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 8
    noise.inputs["Roughness"].default_value = 0.65
    links.new(geo.outputs["Position"], noise.inputs["Vector"])

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*col_a, 1)
    ramp.color_ramp.elements[1].color = (*col_b, 1)
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])

    # vertical rain streaks (stretched noise)
    streak_map = nodes.new("ShaderNodeMapping")
    streak_map.inputs["Scale"].default_value = (2.5, 2.5, 0.08)
    links.new(geo.outputs["Position"], streak_map.inputs["Vector"])
    streak = nodes.new("ShaderNodeTexNoise")
    streak.inputs["Scale"].default_value = 3.0
    links.new(streak_map.outputs["Vector"], streak.inputs["Vector"])
    dark = nodes.new("ShaderNodeMix")
    dark.data_type = "RGBA"
    dark.blend_type = "MULTIPLY"
    dark.inputs[0].default_value = 0.35
    links.new(ramp.outputs["Color"], dark.inputs[6])
    links.new(streak.outputs["Color"], dark.inputs[7])
    links.new(dark.outputs[2], bsdf.inputs["Base Color"])

    bsdf.inputs["Roughness"].default_value = rough

    bump_n = nodes.new("ShaderNodeBump")
    bump_n.inputs["Strength"].default_value = bump
    fine = nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 6.0
    fine.inputs["Detail"].default_value = 10
    links.new(geo.outputs["Position"], fine.inputs["Vector"])
    links.new(fine.outputs["Fac"], bump_n.inputs["Height"])
    links.new(bump_n.outputs["Normal"], bsdf.inputs["Normal"])

    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def flat_material(name, col, rough=0.9, metallic=0.0):
    m = bpy.data.materials.new(name)
    if not m.node_tree:
        m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*col, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    return m


def build_materials():
    return {
        # Thanjavur granite reads warm ochre at golden hour
        "granite": stone_material("Granite_Ochre", (0.30, 0.13, 0.05), (0.52, 0.27, 0.11)),
        "granite_dark": stone_material("Granite_Weathered", (0.20, 0.14, 0.10), (0.40, 0.28, 0.18)),
        "brick": stone_material("Brick_Prakara", (0.36, 0.14, 0.08), (0.50, 0.22, 0.12), scale=1.2),
        "paving": stone_material("Paving", (0.30, 0.27, 0.24), (0.45, 0.41, 0.36), scale=0.8, bump=0.2),
        "grass": stone_material("Lawn", (0.05, 0.16, 0.03), (0.12, 0.30, 0.05), rough=0.95, scale=0.5, bump=0.1),
        "gold": flat_material("Gilded_Kalasha", (0.9, 0.62, 0.22), rough=0.3, metallic=1.0),
        "nandi": stone_material("Nandi_Basalt", (0.06, 0.05, 0.05), (0.14, 0.12, 0.11), rough=0.45, scale=2.0),
    }


# --------------------------------------------------------------------------
# Architectural kit
# --------------------------------------------------------------------------


def kuta(name, x, y, z, s, M, collection="Temple"):
    """Miniature square shrine with domed roof (corner unit of a tala)."""
    box(name + "_body", (x, y), z, s, s, s * 0.9, M["granite"], collection)
    box(name + "_eave", (x, y), z + s * 0.9, s * 1.2, s * 1.2, s * 0.15, M["granite"], collection)
    part("dome", name + "_roof", (x, y, z + s * 1.05), (s, s, s * 1.0), M["granite"], collection)


def shala(name, x, y, z, length, s, along_x, M, collection="Temple"):
    """Oblong pavilion with barrel-vault roof (middle unit of a tala)."""
    w, d = (length, s) if along_x else (s, length)
    box(name + "_body", (x, y), z, w, d, s * 0.9, M["granite"], collection)
    box(name + "_eave", (x, y), z + s * 0.9, w * 1.08, d * 1.2, s * 0.15, M["granite"], collection)
    rot = 0.0 if along_x else math.pi / 2
    part("barrel", name + "_roof", (x, y, z + s * 1.05), (length, s, s * 1.1), M["granite"], collection, rot)


def tala_ring(prefix, half, z, unit, M):
    """Ring of kutas (corners) and shalas (middles) on the edge of a tier."""
    edge = half - unit * 0.55
    for sx in (-1, 1):
        for sy in (-1, 1):
            kuta(f"{prefix}_kuta{sx}{sy}", sx * edge, sy * edge, z, unit, M)
    span = 2 * edge - unit * 1.4
    if span > unit * 1.5:
        L = min(span * 0.55, unit * 2.6)
        for s in (-1, 1):
            shala(f"{prefix}_shalaX{s}", 0, s * edge, z, L, unit, True, M)
            shala(f"{prefix}_shalaY{s}", s * edge, 0, z, L, unit, False, M)


def moldings(prefix, cx, cy, z0, w, d, bands, M, mat_key="granite"):
    """Stacked adhishthana mouldings: list of (height, inset)."""
    z = z0
    for i, (h, inset) in enumerate(bands):
        box(f"{prefix}_mould{i}", (cx, cy), z, w - 2 * inset, d - 2 * inset, h, M[mat_key])
        z += h
    return z


def pilastered_wall(prefix, cx, cy, z0, w, d, h, M, bay=3.2):
    """Wall block with pilaster rhythm and a cornice (kapota)."""
    box(prefix + "_core", (cx, cy), z0, w - 0.6, d - 0.6, h, M["granite"])
    # pilasters
    for side in ("N", "S", "E", "W"):
        length = w if side in "NS" else d
        n = max(2, int(length / bay))
        for i in range(n + 1):
            t = -length / 2 + i * length / n
            if side == "N":
                pos = (cx + t, cy + d / 2 - 0.3)
            elif side == "S":
                pos = (cx + t, cy - d / 2 + 0.3)
            elif side == "E":
                pos = (cx + w / 2 - 0.3, cy + t)
            else:
                pos = (cx - w / 2 + 0.3, cy + t)
            box(f"{prefix}_pil{side}{i}", pos, z0, 0.9, 0.9, h * 0.92, M["granite"])
    # cornice + parapet line
    box(prefix + "_kapota", (cx, cy), z0 + h * 0.92, w + 0.8, d + 0.8, h * 0.08, M["granite"])
    return z0 + h


# --------------------------------------------------------------------------
# Brihadeeswarar complex
# --------------------------------------------------------------------------


def build_vimana(M):
    base = 30.0  # garbhagriha outer square
    # Upapitha + adhishthana (raised base)
    z = moldings("vim_base", 0, 0, 0, base + 6, base + 6,
                 [(0.8, 0), (0.6, 0.6), (0.9, 0.9), (0.5, 0.5), (0.7, 1.1)], M)
    # Two-storey sanctum wall (the famous double-storeyed prakara of the vimana)
    z = pilastered_wall("vim_wall1", 0, 0, z, base, base, 7.5, M)
    z = pilastered_wall("vim_wall2", 0, 0, z, base - 0.4, base - 0.4, 7.0, M)
    tala_ring("vim_lower", base / 2, z, 2.4, M)

    # 13 receding talas up to ~ 58 m
    n_tiers = 13
    top_half = 4.4
    half0 = base / 2 - 1.2
    tier_h = 2.95
    for i in range(n_tiers):
        t = i / (n_tiers - 1)
        half = half0 + (top_half - half0) * (t ** 0.92)
        box(f"vim_tala{i:02d}", (0, 0), z, 2 * half, 2 * half, tier_h * 0.55, M["granite"])
        unit = max(1.1, 2.3 - 1.1 * t)
        tala_ring(f"vim_t{i:02d}", half, z + tier_h * 0.55, unit, M)
        z += tier_h

    # Griva (neck) + octagonal shikhara (the 80-ton capstone) + kalasha
    box("vim_griva", (0, 0), z, 7.0, 7.0, 1.8, M["granite"])
    part("cyl", "vim_griva_oct", (0, 0, z + 1.8), (6.4, 6.4, 1.2), M["granite"])
    z += 3.0
    part("octadome", "vim_shikhara", (0, 0, z), (8.8, 8.8, 7.0), M["granite"])
    # nandis on the corners of the griva platform
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(f"vim_griva_nandi{sx}{sy}", (sx * 3.3, sy * 3.3), z - 1.2, 1.0, 1.4, 1.0, M["granite"])
    z += 3.4
    part("kalasha", "vim_kalasha", (0, 0, z), (1.5, 1.5, 2.6), M["gold"])
    part("cyl", "vim_kalasha_tip", (0, 0, z + 2.5), (0.25, 0.25, 1.4), M["gold"])
    return z + 3.9


def build_mandapas(M):
    # Ardha + maha + mukha mandapa running east from the sanctum
    x0 = 15.0
    z = moldings("mand_base", x0 + 21, 0, 0, 42, 24,
                 [(0.8, 0), (0.7, 0.5), (0.8, 0.8), (0.6, 0.6)], M)
    pilastered_wall("mand_wall", x0 + 21, 0, z, 40, 22, 9.0, M)
    # parapet of small kutas/shalas on the flat roof
    tala_ring("mand_parapet_a", 11, z + 9.0, 1.4, M)
    for i, x in enumerate((x0 + 8, x0 + 21, x0 + 34)):
        for s in (-1, 1):
            shala(f"mand_par{i}{s}", x, s * 10.2, z + 9.0, 5.0, 1.3, True, M)
    # Entrance steps on the east, flanked by dvarapala blocks
    xe = x0 + 42
    for i in range(6):
        box(f"mand_step{i}", (xe + 1.2 + i * 0.55, 0), 0, 1.2, 8 - i * 0.2, 3.4 - i * 0.55, M["granite"])
    for s in (-1, 1):
        box(f"mand_dvarapala{s}", (xe - 0.2, s * 5.5), z, 2.0, 2.0, 5.5, M["granite_dark"])


def build_nandi_mandapa(M):
    cx = 98.0
    z = moldings("nandi_base", cx, 0, 0, 18, 14, [(0.8, 0), (0.8, 0.5), (0.6, 0.8)], M)
    # pillars (nayak-era pavilion, 16 columns)
    for ix in range(4):
        for iy in range(4):
            x = cx - 7 + ix * (14 / 3)
            y = -5 + iy * (10 / 3)
            part("cyl", f"nandi_pillar{ix}{iy}", (x, y, z), (0.9, 0.9, 7.0), M["granite"])
    box("nandi_roof", (cx, 0), z + 7.0, 18.5, 14.5, 1.0, M["granite"])
    box("nandi_roof2", (cx, 0), z + 8.0, 16, 12, 0.6, M["granite"])
    # Nandi: monolithic black bull, facing west toward the sanctum
    box("nandi_plinth", (cx, 0), z, 7.0, 4.0, 0.8, M["granite"])
    part("dome", "nandi_body", (cx, 0, z + 0.8), (6.0, 3.0, 4.6), M["nandi"])
    part("dome", "nandi_head", (cx - 3.0, 0, z + 2.6), (1.8, 1.6, 2.6), M["nandi"])
    part("kalasha", "nandi_hump", (cx - 1.4, 0, z + 2.5), (1.4, 1.6, 1.3), M["nandi"])


def gopuram(prefix, cx, w, d, base_h, tiers, M):
    """Chola gopuram: stone base + receding tiers + barrel-vault crown with kalashas."""
    z = moldings(prefix + "_base", cx, 0, 0, w + 2, d + 2, [(0.8, 0), (0.7, 0.6), (0.6, 0.9)], M)
    # gateway opening is suggested by two flanking wall blocks
    gate = w * 0.22
    for s in (-1, 1):
        box(f"{prefix}_jamb{s}", (cx, s * (gate / 2 + (w - gate) / 4)), z, d, (w - gate) / 2, base_h, M["granite"])
    box(prefix + "_lintel", (cx, 0), z + base_h * 0.62, d, gate + 0.4, base_h * 0.38, M["granite"])
    z += base_h
    tw, td = w, d
    for i in range(tiers):
        box(f"{prefix}_tier{i}", (cx, 0), z, td, tw, 3.2, M["granite"])
        for sy in (-1, 1):
            kuta(f"{prefix}_t{i}k{sy}", cx + td / 2 - 0.8, sy * (tw / 2 - 0.8), z + 3.2, 1.3, M)
            kuta(f"{prefix}_t{i}kw{sy}", cx - td / 2 + 0.8, sy * (tw / 2 - 0.8), z + 3.2, 1.3, M)
        z += 3.6
        tw *= 0.86
        td *= 0.88
    # crowning shala vault, long axis N-S
    part("barrel", prefix + "_crown", (cx, 0, z), (tw * 1.1, td * 0.9, td * 0.9), M["granite"], rot_z=math.pi / 2)
    n = 7
    for i in range(n):
        y = -tw * 0.45 + i * (tw * 0.9) / (n - 1)
        part("kalasha", f"{prefix}_kalasha{i}", (cx, y, z + td * 0.42), (0.7, 0.7, 1.4), M["gold"])


def build_enclosure(M):
    x_min, x_max, y_half = -70.0, 125.0, 62.0
    h = 6.0
    t = 7.0  # cloister depth
    # long cloister (tiruchurru maligai) with brick parapet
    for s in (-1, 1):
        box(f"wall_long{s}", ((x_min + x_max) / 2, s * (y_half - t / 2)), 0, x_max - x_min, t, h, M["brick"])
        box(f"wall_long_par{s}", ((x_min + x_max) / 2, s * (y_half - t / 2)), h, x_max - x_min + 1, t + 1, 0.6, M["granite"])
    box("wall_west", (x_min + t / 2, 0), 0, t, 2 * y_half, h, M["brick"])
    for s in (-1, 1):
        box(f"wall_east{s}", (x_max - t / 2, s * (y_half / 2 + 9)), 0, t, y_half - 18, h, M["brick"])
    # ground: lawn inside, paved processional path on the east-west axis
    box("ground", (20, 0), -1.0, 900, 900, 1.0, M["grass"], "Ground")
    box("path_axis", (60, 0), 0, 140, 10, 0.08, M["paving"], "Ground")
    box("path_ring", (10, 0), 0, 70, 70, 0.04, M["paving"], "Ground")
    # inner (Rajarajan) gopuram on the east cloister, outer (Keralantakan) further east
    gopuram("gop_rajarajan", x_max - 3.5, 22, 14, 9.0, 5, M)
    gopuram("gop_keralantakan", x_max + 75, 28, 18, 11.0, 5, M)
    box("path_outer", (x_max + 38, 0), 0, 80, 10, 0.08, M["paving"], "Ground")
    # simple palm/tree proxies around the lawn
    import random
    rnd = random.Random(7)
    for i in range(36):
        x = rnd.uniform(x_min + 12, x_max - 12)
        y = rnd.choice((-1, 1)) * rnd.uniform(32, y_half - 10)
        hgt = rnd.uniform(9, 15)
        part("cyl", f"palm_trunk{i}", (x, y, 0), (0.45, 0.45, hgt), M["granite_dark"], "Vegetation")
        part("dome", f"palm_crown{i}", (x, y, hgt - 0.6), (6.5, 6.5, 2.4), M["grass"], "Vegetation")


# --------------------------------------------------------------------------
# Lighting, cameras, render
# --------------------------------------------------------------------------


def setup_world(scn, sun_elev_deg=11.0, sun_rot_deg=-62.0):
    """Physical sky at golden hour + matching sun lamp for crisp shadows."""
    world = bpy.data.worlds.new("Sky")
    scn.world = world
    if not world.node_tree:
        world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_elevation = math.radians(sun_elev_deg)
    sky.sun_rotation = math.radians(sun_rot_deg)
    sky.sun_disc = False  # the lamp below provides the sun
    sky.aerosol_density = 2.0
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 0.22
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])

    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = 6.0
    sun.color = (1.0, 0.58, 0.30)
    sun.angle = math.radians(1.2)
    sun_ob = bpy.data.objects.new("Sun", sun)
    # point the lamp along the sky's sun direction
    el, rot = math.radians(sun_elev_deg), math.radians(sun_rot_deg)
    d = Vector((math.cos(el) * math.sin(rot), math.cos(el) * math.cos(rot), math.sin(el)))
    sun_ob.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    coll("Lighting").objects.link(sun_ob)


def add_camera(name, loc, target, lens):
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    cam.clip_end = 3000
    ob = bpy.data.objects.new(name, cam)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    coll("Cameras").objects.link(ob)
    return ob


def setup_cameras(top_z):
    return [
        # matches reference photo 4: low, from the north-east courtyard, looking up
        add_camera("CAM_hero_low", (88, 52, 1.7), (0, 0, top_z * 0.55), 28),
        # matches reference photo 2: drone shot from the east over the gopurams
        add_camera("CAM_aerial", (330, -150, 150), (60, 0, 5), 32),
    ]


def setup_render(scn, samples, res):
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = samples
    scn.cycles.use_denoising = True
    scn.cycles.max_bounces = 6
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.film_transparent = False
    scn.view_settings.view_transform = "AgX"
    scn.view_settings.look = "AgX - Medium High Contrast"
    scn.view_settings.exposure = 0.1
    scn.render.image_settings.file_format = "PNG"


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opts = {"render": None, "save": None, "samples": 48, "res": (1600, 900)}
    i = 0
    while i < len(argv):
        k = argv[i]
        if k == "--render":
            opts["render"] = argv[i + 1]; i += 1
        elif k == "--save":
            opts["save"] = argv[i + 1]; i += 1
        elif k == "--samples":
            opts["samples"] = int(argv[i + 1]); i += 1
        elif k == "--res":
            w, h = argv[i + 1].lower().split("x"); opts["res"] = (int(w), int(h)); i += 1
        i += 1
    return opts


def main():
    opts = parse_args()
    scn = reset_scene()
    M = build_materials()
    top = build_vimana(M)
    build_mandapas(M)
    build_nandi_mandapa(M)
    build_enclosure(M)
    setup_world(scn)
    cams = setup_cameras(top)
    setup_render(scn, opts["samples"], opts["res"])
    scn.camera = cams[0]
    print(f"[chola] vimana height ~ {top:.1f} m, objects: {len(bpy.data.objects)}")

    if opts["save"]:
        bpy.ops.wm.save_as_mainfile(filepath=bpy.path.abspath(opts["save"]))
    if opts["render"]:
        for cam in cams:
            scn.camera = cam
            scn.render.filepath = f"{opts['render']}_{cam.name}.png"
            bpy.ops.render.render(write_still=True)
            print("[chola] wrote", scn.render.filepath)


if __name__ == "__main__":
    main()
