# Case stampabile per il Presentator dongle (ESP32-S3 Supermini senza header).
#
# Generazione (FreeCAD 1.0, senza interfaccia):
#   "C:\Program Files\FreeCAD 1.0\bin\freecadcmd.exe" case_presentator.py
# Produce nella stessa cartella: base.stl, lid.stl (gia' orientati per la
# stampa), case.step (assemblato) e le anteprime PNG in preview/.
#
# Le quote x della scheda si inseriscono come si misurano tenendola in mano:
# lato componenti verso di se', USB in alto, x dal bordo sinistro (lato
# BOOT), y dal bordo USB verso l'antenna. Internamente il modello usa
# z verso l'alto, per cui quelle x vengono specchiate (vedi "quote derivate").
#
# Tutte le quote della scheda sono parametri: i Supermini sono cloni e
# variano. Misurare la propria scheda col calibro e correggere qui sotto.

import os
import sys

import FreeCAD
import Part
from FreeCAD import Vector as V

# --- scheda (misurare!) --------------------------------------------------------
PCB_W = 18.0          # larghezza (misurata)
PCB_L = 23.6          # lunghezza PCB, senza la sporgenza della USB (misurata)
PCB_T = 1.16          # spessore PCB (misurato)

USB_W = 8.94          # larghezza connettore USB-C
USB_H = 3.26          # altezza connettore sopra il PCB
USB_CX = 9.0          # centro connettore (x)
USB_OVERHANG = 1.6    # quanto il connettore sporge oltre il bordo del PCB (misurato)
USB_DEPTH = 6.3       # lunghezza totale del connettore (solo per i controlli)
# linguette THT del connettore che sporgono SOTTO la scheda (x, y del centro)
USB_LEGS = [(4.9, 0.95), (13.1, 0.95), (4.9, 5.1), (13.1, 5.1)]
USB_LEG_POCKET = (2.0, 2.6)   # fori passanti nel fondo (x, y): vanno bene per ogni sporgenza

BTN_Y = 8.7           # centro pulsanti dal bordo USB (da illustrazione in scala, non misurato)
BOOT_X = 4.75         # centro BOOT dal bordo sinistro (misurato)
RST_X = PCB_W - 4.75  # centro RESET: simmetrico a BOOT (non misurato)
BTN_BODY = (3.2, 2.5)  # corpo del pulsante SMD (x, y)
BTN_H = 1.5           # altezza della sommita' del pulsante sopra il PCB (misurata)

LED_X, LED_Y = 14.9, 18.0    # LED RGB WS2812 (stato: lampeggia = cerca, fisso = collegato)
LED_SIZE = 2.0
ANT_X, ANT_Y = (3.5, 10.0), (PCB_L - 2.3, PCB_L - 0.1)  # antenna ceramica
ANT_H = 1.3
COMP_H = 1.6          # inviluppo degli altri componenti (QFN, SOT-23, ecc.)

# --- case ------------------------------------------------------------------
CLR = 0.25            # gioco scheda-tasca per lato (lati e retro)
WALL = 1.6            # pareti laterali e posteriore (4 linee da 0.4)
FRONT_WALL = USB_OVERHANG   # parete lato USB: connettore a filo con l'esterno
FLOOR = 1.4
LID_T = 1.2           # spessore coperchio
TOP_GAP = 0.2         # aria tra connettore USB e coperchio
CORNER_R = 1.5        # raggio spigoli verticali esterni

LIP_T = 0.9           # labbri del coperchio che premono sui bordi del PCB
LIP_FIT = 0.15        # gioco labbro-parete (aumentare se il coperchio non entra)
LIP_PRESS = 0.0       # interferenza labbro-PCB (0.05-0.1 per serrare di piu')
LIP_END = 0.4         # distanza dei labbri dai bordi corti del PCB
SNAP = 0.3            # sporgenza dentini di aggancio (0 = solo attrito)
SNAP_LEN = 4.0

# tasti a linguetta flessibile ricavati nel coperchio
TONGUE_W = 3.6
TONGUE_TIP = 1.6      # quanto la linguetta va oltre il centro del pulsante (verso USB)
TONGUE_LEN = 7.0      # dal centro del pulsante all'attacco (verso l'antenna)
TONGUE_T = 0.8        # spessore linguetta (piu' sottile del coperchio = piu' morbida)
SLOT = 0.7            # fessura attorno alla linguetta (non scendere sotto 0.6)
NUB_D = 2.2           # diametro del perno che preme il pulsante
NUB_GAP = 0.35        # aria perno-pulsante a riposo: MAI zero (RST/BOOT premuti!)
DIMPLE_D, DIMPLE_DEPTH = 3.0, 0.3   # incavo per il dito sulla linguetta

LED_HOLE_D = 2.2
LABEL_SIZE = 2.6
LABEL_DEPTH = 0.4     # 0 = niente scritte (a 2.6 mm possono impastarsi sul primo layer)
LABEL_Y = 2.0
FONT = "C:/Windows/Fonts/arialbd.ttf"

# --- quote derivate ---------------------------------------------------------
# x misurate con la USB in alto -> x del modello (vista da +z, y verso l'alto)
def _mx(x):
    return PCB_W - x


USB_CX = _mx(USB_CX)
USB_LEGS = [(_mx(x), y) for (x, y) in USB_LEGS]
BOOT_X, RST_X = _mx(BOOT_X), _mx(RST_X)
LED_X = _mx(LED_X)
ANT_X = (_mx(ANT_X[1]), _mx(ANT_X[0]))

Z_PCB = FLOOR
Z_PCB_TOP = FLOOR + PCB_T
Z_IN = Z_PCB_TOP + USB_H + TOP_GAP     # faccia interna del coperchio = cima pareti
Z_TOP = Z_IN + LID_T
X0, X1 = -CLR - WALL, PCB_W + CLR + WALL
Y0, Y1 = -FRONT_WALL, PCB_L + CLR + WALL

OUT = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(x, y, d, z0, z1):
    return Part.makeCylinder(d / 2, z1 - z0, V(x, y, z0))


def rounded_block(z0, z1):
    b = box(X0, X1, Y0, Y1, z0, z1)
    edges = [e for e in b.Edges
             if abs(e.Vertexes[0].Point.z - e.Vertexes[1].Point.z) > 1e-6]
    return b.makeFillet(CORNER_R, edges)


def fuse_all(shapes):
    s = shapes[0]
    for t in shapes[1:]:
        s = s.fuse(t)
    return s.removeSplitter()


def text_solid(txt, cx, cy, size, z0, depth):
    chars = Part.makeWireString(txt, FONT, size, 0)
    faces = []
    for ch in chars:
        wires = [Part.Wire(Part.__sortEdges__(e.Edges)) if hasattr(e, "Edges") else Part.Wire(e)
                 for e in ch]
        if wires:
            faces.append(Part.Face(wires, "Part::FaceMakerBullseye"))
    sol = fuse_all([f.extrude(V(0, 0, depth)) for f in faces])
    # leggibile con la USB in alto, come la serigrafia della scheda
    sol.rotate(sol.BoundBox.Center, V(0, 0, 1), 180)
    bb = sol.BoundBox
    sol.translate(V(cx - (bb.XMin + bb.XMax) / 2, cy - (bb.YMin + bb.YMax) / 2, z0 - bb.ZMin))
    return sol


# --- fondo --------------------------------------------------------------------
def make_base():
    b = rounded_block(0, Z_IN)
    b = b.cut(box(-CLR, PCB_W + CLR, 0, PCB_L + CLR, FLOOR, Z_IN + 1))
    # finestra USB, aperta verso l'alto (il coperchio la chiude)
    b = b.cut(box(USB_CX - USB_W / 2 - CLR, USB_CX + USB_W / 2 + CLR,
                  Y0 - 1, 0.01, Z_PCB_TOP, Z_IN + 1))
    for (lx, ly) in USB_LEGS:
        px, py = USB_LEG_POCKET
        b = b.cut(box(lx - px / 2, lx + px / 2, ly - py / 2, ly + py / 2, -1, FLOOR + 0.01))
    # sedi per i dentini del coperchio
    if SNAP > 0:
        ymid = PCB_L / 2
        zc = Z_IN - 1.2
        for xw, sgn in ((-CLR, -1), (PCB_W + CLR, 1)):
            g = box(min(xw, xw + sgn * (SNAP + 0.1)), max(xw, xw + sgn * (SNAP + 0.1)),
                    ymid - SNAP_LEN / 2 - 0.3, ymid + SNAP_LEN / 2 + 0.3,
                    zc - 0.5, zc + 0.5)
            b = b.cut(g)
    # tacca sul retro per fare leva col cacciavite e aprire
    b = b.cut(box(PCB_W / 2 - 2, PCB_W / 2 + 2, Y1 - WALL - 0.1, Y1 + 0.1, Z_IN - 0.8, Z_IN + 1))
    return b.removeSplitter()


# --- coperchio (in posizione di montaggio) -----------------------------------
def tongue_box(bx, extra=0.0):
    return box(bx - TONGUE_W / 2 - extra, bx + TONGUE_W / 2 + extra,
               BTN_Y - TONGUE_TIP - extra, BTN_Y + TONGUE_LEN, Z_IN - 1, Z_TOP + 1)


def make_lid():
    lid = rounded_block(Z_IN, Z_TOP)
    parts = [lid]
    z_lip_bot = Z_PCB_TOP - LIP_PRESS
    for x_out, x_in in ((-CLR + LIP_FIT, -CLR + LIP_FIT + LIP_T),
                        (PCB_W + CLR - LIP_FIT - LIP_T, PCB_W + CLR - LIP_FIT)):
        parts.append(box(x_out, x_in, LIP_END, PCB_L - LIP_END, z_lip_bot, Z_IN + 0.01))
        if SNAP > 0:
            ymid = PCB_L / 2
            zc = Z_IN - 1.2
            if x_out < 0:
                bump = box(x_out - SNAP, x_out + 0.01, ymid - SNAP_LEN / 2, ymid + SNAP_LEN / 2,
                           zc - 0.4, zc + 0.4)
            else:
                bump = box(x_in - 0.01, x_in + SNAP, ymid - SNAP_LEN / 2, ymid + SNAP_LEN / 2,
                           zc - 0.4, zc + 0.4)
            parts.append(bump)
    # dente che chiude la finestra USB sopra il connettore
    if TOP_GAP > 0:
        parts.append(box(USB_CX - USB_W / 2 - CLR + LIP_FIT, USB_CX + USB_W / 2 + CLR - LIP_FIT,
                         Y0, -0.05, Z_PCB_TOP + USB_H + 0.05, Z_IN + 0.01))
    lid = fuse_all(parts)

    z_btn_top = Z_PCB_TOP + BTN_H
    for bx in (BOOT_X, RST_X):
        # fessura a U attorno alla linguetta (l'attacco resta verso l'antenna)
        slot = tongue_box(bx, SLOT).cut(tongue_box(bx))
        slot = slot.common(box(X0, X1, Y0, BTN_Y + TONGUE_LEN, Z_IN - 1, Z_TOP + 1))
        lid = lid.cut(slot)
        # assottiglia la linguetta dall'interno
        lid = lid.cut(box(bx - TONGUE_W / 2, bx + TONGUE_W / 2,
                          BTN_Y - TONGUE_TIP, BTN_Y + TONGUE_LEN,
                          Z_IN - 0.01, Z_TOP - TONGUE_T))
        # perno verso il pulsante
        lid = lid.fuse(cyl(bx, BTN_Y, NUB_D, z_btn_top + NUB_GAP, Z_TOP - TONGUE_T + 0.01))
        # incavo per il dito
        lid = lid.cut(cyl(bx, BTN_Y, DIMPLE_D, Z_TOP - DIMPLE_DEPTH, Z_TOP + 1))

    lid = lid.cut(cyl(LED_X, LED_Y, LED_HOLE_D, Z_IN - 1, Z_TOP + 1))
    for txt, bx in ((("BOOT", BOOT_X), ("RST", RST_X)) if LABEL_DEPTH > 0 else ()):
        lid = lid.cut(text_solid(txt, bx, LABEL_Y, LABEL_SIZE, Z_TOP - LABEL_DEPTH, LABEL_DEPTH + 0.5))
    return lid.removeSplitter()


# --- scheda fittizia per i controlli -----------------------------------------
def make_dummy():
    d = {}
    d["pcb"] = box(0, PCB_W, 0, PCB_L, Z_PCB, Z_PCB_TOP)
    d["usb"] = box(USB_CX - USB_W / 2, USB_CX + USB_W / 2, -USB_OVERHANG, USB_DEPTH - USB_OVERHANG,
                   Z_PCB_TOP, Z_PCB_TOP + USB_H)
    d["usb_legs"] = fuse_all([box(x - 0.4, x + 0.4, y - 0.8, y + 0.8, Z_PCB - 0.7, Z_PCB)
                              for (x, y) in USB_LEGS])
    for name, bx in (("boot", BOOT_X), ("rst", RST_X)):
        d[name] = box(bx - BTN_BODY[0] / 2, bx + BTN_BODY[0] / 2,
                      BTN_Y - BTN_BODY[1] / 2, BTN_Y + BTN_BODY[1] / 2,
                      Z_PCB_TOP, Z_PCB_TOP + BTN_H)
    d["led"] = box(LED_X - LED_SIZE / 2, LED_X + LED_SIZE / 2, LED_Y - LED_SIZE / 2, LED_Y + LED_SIZE / 2,
                   Z_PCB_TOP, Z_PCB_TOP + 0.8)
    d["antenna"] = box(ANT_X[0], ANT_X[1], ANT_Y[0], ANT_Y[1], Z_PCB_TOP, Z_PCB_TOP + ANT_H)
    # inviluppo componenti: tutto il PCB tranne la fascia dei pad sui lati lunghi
    d["components"] = box(1.9, PCB_W - 1.9, 0.3, PCB_L - 0.3, Z_PCB_TOP, Z_PCB_TOP + COMP_H)
    return d


def check(base, lid, dummy):
    ok = True
    print("--- controlli ---")
    for name, s in (("base", base), ("lid", lid)):
        print(f"{name}: valido={s.isValid()} solidi={len(s.Solids)} volume={s.Volume:.1f} mm3")
        ok &= s.isValid() and len(s.Solids) == 1
    v = base.common(lid).Volume
    print(f"interferenza base/coperchio: {v:.4f} mm3")
    ok &= v < 1e-3
    for name, s in dummy.items():
        for pname, p in (("base", base), ("lid", lid)):
            iv = p.common(s).Volume
            if iv > 1e-3:
                print(f"  COLLISIONE {pname} / {name}: {iv:.4f} mm3")
                ok = False
    for name, bx in (("BOOT", BOOT_X), ("RST", RST_X)):
        hit = lid.common(box(bx - 0.5, bx + 0.5, BTN_Y - 0.5, BTN_Y + 0.5, Z_PCB_TOP, Z_IN))
        gap = hit.BoundBox.ZMin - (Z_PCB_TOP + BTN_H)
        print(f"aria perno-pulsante {name}: {gap:.2f} mm (misurata sul solido)")
        ok &= gap > 0.2
    usb_front = -USB_OVERHANG
    print(f"faccia USB rispetto all'esterno: {usb_front - Y0:+.2f} mm (0 = a filo)")
    print(f"parete anteriore: {FRONT_WALL:.2f} mm")
    if FRONT_WALL < 0.8:
        print("  parete anteriore troppo sottile per la stampa: aumentare FRONT_WALL "
              "(il connettore restera' un po' rientrato)")
        ok = False
    lip_x = -CLR + LIP_FIT + LIP_T
    print(f"i labbri coprono il PCB per {lip_x:.2f} mm per lato (pad laterali)")
    print(f"ingombro esterno: {X1 - X0:.1f} x {Y1 - Y0:.1f} x {Z_TOP:.1f} mm")
    print("ESITO:", "OK" if ok else "PROBLEMI")
    return ok


def export_stl(shape, path):
    import Mesh
    import MeshPart
    m = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.01, AngularDeflection=0.2, Relative=False)
    print(f"{os.path.basename(path)}: {m.CountFacets} facce, solido={m.isSolid()}, "
          f"non-manifold={m.hasNonManifolds()}")
    m.write(path)
    return m


def previews(base, lid, dummy, outdir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    os.makedirs(outdir, exist_ok=True)
    board = fuse_all(list(dummy.values()))
    items = ((base, "#4c78a8", "fondo"), (lid, "#f58518", "coperchio"), (board, "#54a24b", "scheda"))

    def section(axis, value, title, fname):
        fig, ax = plt.subplots(figsize=(7, 3.4))
        n = V(1, 0, 0) if axis == "x" else V(0, 1, 0)
        for shp, col, lab in items:
            wires = shp.slice(n, value)
            first = True
            for w in wires:
                pts = w.discretize(Deflection=0.02)
                xy = [((p.y if axis == "x" else p.x), p.z) for p in pts]
                ax.add_patch(Polygon(xy, closed=True, facecolor=col, edgecolor="k", lw=0.4,
                                     alpha=0.55, label=lab if first else None))
                first = False
        ax.set_aspect("equal")
        ax.autoscale()
        ax.set_xlabel("y (mm, 0 = bordo USB)" if axis == "x" else "x (mm)")
        ax.set_ylabel("z (mm)")
        ax.set_title(title)
        ax.legend(loc="upper right", fontsize=7)
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(outdir, fname), dpi=160)
        plt.close(fig)

    section("x", BOOT_X, f"Sezione su BOOT (x = {BOOT_X} mm)", "sezione_boot.png")
    section("x", USB_CX, f"Sezione sull'asse USB (x = {USB_CX} mm)", "sezione_usb.png")
    section("y", BTN_Y, f"Sezione trasversale sui pulsanti (y = {BTN_Y} mm)", "sezione_pulsanti.png")

    # vista dall'alto del coperchio
    fig, ax = plt.subplots(figsize=(4.5, 5.2))
    top = lid.slice(V(0, 0, 1), Z_TOP - 0.05)
    for w in top:
        pts = w.discretize(Deflection=0.02)
        ax.add_patch(Polygon([(p.x, p.y) for p in pts], closed=True, facecolor="#f58518",
                             edgecolor="k", lw=0.4, alpha=0.6))
    for w in lid.slice(V(0, 0, 1), Z_TOP - LABEL_DEPTH / 2):
        pts = w.discretize(Deflection=0.02)
        ax.plot([p.x for p in pts] + [pts[0].x], [p.y for p in pts] + [pts[0].y], "k-", lw=0.4)
    ax.set_aspect("equal")
    ax.autoscale()
    # ruotata di 180 gradi (non specchiata): USB in alto come in mano
    ax.invert_xaxis()
    ax.invert_yaxis()
    ax.set_title("Coperchio visto dall'alto (USB in alto)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "coperchio_alto.png"), dpi=160)
    plt.close(fig)


def main():
    base = make_base()
    lid = make_lid()
    dummy = make_dummy()
    ok = check(base, lid, dummy)

    Part.makeCompound([base, lid]).exportStep(os.path.join(OUT, "case.step"))
    export_stl(base, os.path.join(OUT, "base.stl"))
    # coperchio capovolto: faccia esterna sul piatto, perni verso l'alto
    lid_print = lid.copy()
    lid_print.rotate(V(0, 0, 0), V(1, 0, 0), 180)
    bb = lid_print.BoundBox
    lid_print.translate(V(-bb.XMin, -bb.YMin, -bb.ZMin))
    export_stl(lid_print, os.path.join(OUT, "lid.stl"))
    previews(base, lid, dummy, os.path.join(OUT, "preview"))
    if not ok:
        sys.exit(1)


main()
