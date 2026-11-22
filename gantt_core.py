"""Núcleo del editor de Gantt: validación, fechas/semanas y diseño del gráfico. Sin tkinter ni PIL, para que funcione en escritorio y en Pyodide."""
import math, random, re
from datetime import date, datetime, timedelta

HEX = re.compile(r"#[0-9a-fA-F]{6}\Z")
COLOR_NAMES = ("Azul", "Verde", "Amarillo", "Rojo", "Malva", "Turquesa")
MILE = "#d20f39"  # color por defecto de la línea de un hito
MILE_COLORS = [("Rojo", "#d20f39"), ("Naranja", "#fe640b"), ("Amarillo", "#df8e1d"), ("Verde", "#40a02b"),
               ("Turquesa", "#179299"), ("Azul", "#1e66f5"), ("Malva", "#8839ef"), ("Gris", "#4c4f69")]
PAPER, INK, SUB = "#ffffff", "#4c4f69", "#6c6f85"  # fondo y tinta del gráfico por defecto (el PNG sale igual en todos los temas)
PAPERS = [("Blanco", "#ffffff"), ("Crema", "#fdf6e3"), ("Latte", "#eff1f5"), ("Mocha", "#1e1e2e"), ("Medianoche", "#11111b")]
INKS = [("Gris azulado", "#4c4f69"), ("Negro", "#11111b"), ("Blanco", "#ffffff"), ("Azul", "#1e66f5"), ("Verde", "#40a02b"), ("Rojo", "#d20f39"), ("Malva", "#8839ef")]
STYLE0 = dict(paper=PAPER, ink=INK, bold=True, tscale=100, size=None)  # apariencia por defecto
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]  # %b depende del idioma del sistema
DAYS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
TINTAS = ["#89b4fa", "#a6e3a1", "#f9e2af", "#f38ba8", "#cba6f7", "#94e2d5"]  # azul, verde, amarillo, rojo, mauve, teal


def lum(h):
    f = lambda c: c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4
    r, g, b = (f(int(h[i:i + 2], 16) / 255) for i in (1, 3, 5))
    return .2126 * r + .7152 * g + .0722 * b


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + .05) / (lb + .05)


def mix(a, b, t):
    return "#%02x%02x%02x" % tuple(round(int(a[i:i + 2], 16) * (1 - t) + int(b[i:i + 2], 16) * t) for i in (1, 3, 5))


def jl(r, a, b, j=2.0):
    n = max(1, min(int(math.dist(a, b) / 40), 400))
    return [(a[0] + (b[0] - a[0]) * t / n + r.uniform(-j, j),
             a[1] + (b[1] - a[1]) * t / n + r.uniform(-j, j)) for t in range(n + 1)]


def pdate(v):
    if not isinstance(v, str): raise ValueError("fecha no válida")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try: d = datetime.strptime(v.strip(), fmt).date()
        except ValueError: continue
        if 1900 <= d.year <= 2200: return d
    raise ValueError(f"fecha no válida «{v}» (usa AAAA-MM-DD o DD/MM/AAAA)")


def pweek(v):
    m = re.fullmatch(r"(?:s(?:em(?:ana)?)?\s*)?(\d{1,3})", str(v).strip(), re.I | re.A)
    if not m or not 1 <= int(m[1]) <= 520: raise ValueError(f"semana no válida «{v}» (usa un número del 1 al 520)")
    return int(m[1])


def pwd(v):
    """Semana o semana-día. «3» = toda la semana 3; «3-2» = el martes de la semana 3 (1 = lunes … 7 = domingo). Devuelve int o «S-D»."""
    m = re.fullmatch(r"(?:s(?:em(?:ana)?)?\s*)?(\d{1,3})(?:\s*[-:]\s*([1-7]))?", str(v).strip(), re.I | re.A)
    if not m or not 1 <= int(m[1]) <= 520: raise ValueError(f"semana no válida «{v}» (usa 3 o 3-2: semana-día, del 1 lunes al 7 domingo)")
    return int(m[1]) if m[2] is None else f"{int(m[1])}-{m[2]}"


def wsplit(v): return (v, None) if type(v) is int else tuple(int(p) for p in v.split("-"))


def wdays(v, end):
    """Posición en días desde el inicio de la semana 1: comienzo de la semana/día (inicio) o final de la semana/día (fin)."""
    w, d = wsplit(v)
    return (w * 7 if end else (w - 1) * 7) if d is None else (w - 1) * 7 + (d if end else d - 1)


def wlabel(v):
    w, d = wsplit(v)
    return f"S{w}" if d is None else f"S{w} {DAYS[d - 1]}"


def wrange(a, b):
    if a == b: return wlabel(a)
    (wa, da), (wb, db) = wsplit(a), wsplit(b)
    if da is None and db is None: return f"S{wa}-S{wb}"
    if wa == wb and da and db: return f"S{wa} {DAYS[da - 1]}–{DAYS[db - 1]}"
    return f"{wlabel(a)} – {wlabel(b)}"


class GanttError(ValueError):
    def __init__(s, msg, where=None): super().__init__(msg); s.where = where  # where = campo culpable, para resaltarlo


def clean_style(d):
    """Apariencia del gráfico (fondo, color y grosor del texto, tamaño del texto y del diagrama); lo que falte toma el valor por defecto."""
    paper, ink = str(d.get("paper", PAPER)).lower(), str(d.get("ink", INK)).lower()
    ts, bold, size = d.get("tscale", 100), d.get("bold", True), d.get("size")
    if not (HEX.match(paper) and HEX.match(ink)): raise GanttError("Color de fondo o de texto no válido")
    if type(ts) is not int or not 60 <= ts <= 200: raise GanttError("Tamaño del texto no válido (60-200 %)")
    if type(bold) is not bool: raise GanttError("Grosor del texto no válido")
    if size is not None:
        if not (isinstance(size, (list, tuple)) and len(size) == 2 and all(type(v) is int and 400 <= v <= 6000 for v in size)):
            raise GanttError("Tamaño del diagrama no válido (de 400 a 6000 píxeles)", ("size",))
        size = [size[0], size[1]]
    return dict(paper=paper, ink=ink, bold=bold, tscale=ts, size=size)


def clean_gantt(title, rows, miles, scale, start="", live=False, keep=False):
    """Valida lo escrito en el formulario. Devuelve los datos limpios o lanza GanttError con el campo culpable."""
    clean = lambda t: " ".join(str(t).split())
    if len(clean(title)) > 200: raise GanttError("El título es demasiado largo (máximo 200 caracteres)", ("title",))
    wk = scale == "weeks"
    conv = pwd if wk else (lambda v: pdate(v).isoformat())
    out_r, out_m = [], []
    for i, r in enumerate(rows):
        name = clean(r["name"])
        if len(name) > 200: raise GanttError("El nombre es demasiado largo (máximo 200 caracteres)", ("r", i, "name"))
        if not name and not keep:
            if live: continue  # fila en blanco = marcador de posición, se ignora
            raise GanttError("Escribe un nombre para la etapa", ("r", i, "name"))
        v = {}
        for k in ("start", "end"):
            try: v[k] = conv(r[k])
            except ValueError as e: raise GanttError(f"Etapa «{name}»: {e}", ("r", i, k))
        if (wdays(v["end"], True) <= wdays(v["start"], False)) if wk else v["end"] < v["start"]:
            raise GanttError(f"Etapa «{name}»: el fin es anterior al inicio", ("r", i, "end"))
        if not HEX.match(str(r["color"]).lower()): raise GanttError(f"Etapa «{name}»: color no válido", ("r", i, "color"))
        out_r.append(dict(name=name, color=r["color"].lower(), **v))
    for i, m in enumerate(miles):
        name = clean(m["name"])
        if len(name) > 200: raise GanttError("El nombre es demasiado largo (máximo 200 caracteres)", ("m", i, "name"))
        if not name and not keep:
            if live: continue
            raise GanttError("Escribe un nombre para el hito", ("m", i, "name"))
        try: dt = conv(m["date"])
        except ValueError as e: raise GanttError(f"Hito «{name}»: {e}", ("m", i, "date"))
        mc = str(m.get("color", MILE)).lower()
        if not HEX.match(mc): raise GanttError(f"Hito «{name}»: color no válido", ("m", i, "color"))
        out_m.append(dict(name=name, date=dt, color=mc))
    if not out_r and not out_m and not live: raise GanttError("Añade al menos una etapa o un hito")
    if len(out_r) + len(out_m) > 200: raise GanttError("Demasiadas filas (máximo 200)")
    sw = None
    if wk and str(start).strip():
        try: sw = pweek(start)
        except ValueError as e: raise GanttError(f"Semana de inicio: {e}", ("start",))
        first = min([wsplit(x["start"])[0] for x in out_r] + [wsplit(x["date"])[0] for x in out_m] or [sw])
        if sw > first: raise GanttError(f"La semana de inicio ({sw}) es posterior a la primera etapa o hito (semana {first})", ("start",))
    return dict(title=clean(title), rows=out_r, miles=out_m, scale=scale, start_week=sw)


def convert_gantt(rows, miles, scale):
    """Cambia entre fechas y semanas (con día). Fechas→semanas: la semana 1 es la del lunes anterior a la fecha más temprana.
    Semanas→fechas: la semana 1 es la semana (lunes) actual."""
    if not rows and not miles: return [], []
    if scale == "weeks":  # destino: fechas
        a0 = date.today() - timedelta(days=date.today().weekday())
        d = lambda v, end: (a0 + timedelta(days=wdays(v, end) - (1 if end else 0))).isoformat()
        return ([dict(r, start=d(r["start"], False), end=d(r["end"], True)) for r in rows],
                [dict(m, date=d(m["date"], True)) for m in miles])
    days = [pdate(r[k]).toordinal() for r in rows for k in ("start", "end")] + [pdate(m["date"]).toordinal() for m in miles]
    b = min(days); b -= date.fromordinal(b).weekday()

    def wv(v, end):  # semana entera si coincide con lunes (inicio) o domingo (fin); si no, semana-día
        off = pdate(v).toordinal() - b
        w, d = off // 7 + 1, off % 7 + 1
        if w > 520: raise GanttError("El periodo es demasiado largo para semanas (máximo 520)")
        return w if (d == 7 if end else d == 1) else f"{w}-{d}"
    return ([dict(r, start=wv(r["start"], False), end=wv(r["end"], True)) for r in rows], [dict(m, date=wv(m["date"], True)) for m in miles])


def sample_gantt():
    ph = [("Planificación de pruebas", "2026-12-01", "2026-12-12"), ("Diseño de casos de prueba", "2026-12-08", "2026-12-23"),
          ("Preparación del entorno", "2026-12-15", "2027-01-09"), ("Ejecución de pruebas", "2027-01-12", "2027-02-13"),
          ("Análisis de defectos y re-test", "2027-02-02", "2027-02-27"), ("Informe y cierre de validación", "2027-02-23", "2027-03-12")]
    return dict(title="7. Planificación y Cronograma", scale="dates",
                rows=[dict(name=n, start=a, end=b, color=TINTAS[i]) for i, (n, a, b) in enumerate(ph)],
                miles=[dict(name=n, date=d, color=MILE) for n, d in (("Plan aprobado", "2026-12-12"), ("Entorno listo", "2027-01-09"),
                                                        ("Fin ejecución", "2027-02-13"), ("Firma de validación", "2027-03-12"))])

def parse_gantt(raw):
    """Datos de un .gantt/.json ya leído (formato propio o lista del editor anterior) -> datos limpios. Lanza GanttError/ValueError/KeyError/TypeError."""
    if isinstance(raw, list): raw = next((x for x in raw if isinstance(x, dict) and x.get("type") == "gantt"), None)
    if not isinstance(raw, dict) or raw.get("scale", "dates") not in ("dates", "weeks") or not isinstance(raw.get("title", ""), str):
        raise ValueError("formato")
    str_ = lambda v: v if isinstance(v, str) else str(v)
    nm = lambda v: v if isinstance(v, str) else (_ for _ in ()).throw(TypeError("nombre"))
    if not (isinstance(raw["rows"], list) and isinstance(raw["miles"], list)): raise ValueError("listas")
    d = clean_gantt(raw.get("title", ""),
                    [dict(name=nm(x["name"]), start=str_(x["start"]), end=str_(x["end"]), color=x["color"]) for x in raw["rows"]],
                    [dict(name=nm(m["name"]), date=str_(m["date"]), color=m.get("color", MILE)) for m in raw["miles"]],
                    raw.get("scale", "dates"), "" if raw.get("start_week") is None else str_(raw["start_week"]), live=True)
    d.update(clean_style(raw))
    return d


class Layout:
    """Diseño del Gantt. Quien lo use define tkf(size) -> objeto con measure(texto) (Tk en escritorio, canvas en la web)."""
    cur_bold = True

    def tkf(self, size): raise NotImplementedError

    def clip(self, text, size, w):
        f = self.tkf(size); cut = len(text) > 300; text = text[:300]  # más allá de 300 caracteres nada cabe en pantalla
        if not cut and f.measure(text) <= w: return text
        lo, hi = 0, len(text)
        while lo < hi:  # el prefijo más largo que cabe, con «…»
            mid = (lo + hi + 1) // 2
            if f.measure(text[:mid] + "…") <= w: lo = mid
            else: hi = mid - 1
        return text[:lo] + "…" if f.measure(text[:lo] + "…") <= w else ""

    def wrap(self, text, size, w, maxl=2):
        """Texto en hasta `maxl` líneas que caben en `w`; lo que sobre en la última línea se recorta con «…»."""
        f = self.tkf(size)
        if f.measure(text) <= w: return [text]
        words, lines, cur = text.split(" "), [], ""
        for i, wd in enumerate(words):
            t = (cur + " " + wd).strip()
            if f.measure(t) <= w or not cur: cur = t
            else:
                lines.append(cur); cur = wd
                if len(lines) == maxl - 1: cur = " ".join(words[i:]); break
        return [self.clip(l, size, w) for l in lines + [cur]][:maxl]

    def gantt_parts(self, it):
        """Layout del Gantt -> (rellenos, líneas, macizos, textos) en coordenadas lógicas. Lo usan pantalla y PNG."""
        r, col = random.Random(it["seed"]), it["stroke"]
        sub, gridc = it.get("sub", SUB), it.get("grid", "#ccd0da")
        ts = it.get("tscale", 100) / 100; self.cur_bold = it.get("bold", True)
        T = lambda n: max(7, round(n * ts))  # tamaños y separaciones escalan con «Tamaño del texto»
        x1, x2 = sorted((it["x1"], it["x2"])); y1, y2 = sorted((it["y1"], it["y2"]))
        W = x2 - x1
        fills, lines, solids, texts = [], [], [], []
        frame = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        if it["fill"]: fills.append((frame, it["fill"]))
        lines += [(jl(r, frame[i], frame[(i + 1) % 4], 1.5), col) for i in range(4)]
        wk = it.get("scale", "dates") == "weeks"
        if wk:  # semana N = días [(N-1)*7, N*7); «S-D» fija el día; el hito cae al final de su semana/día
            rows = [(x["name"], wdays(x["start"], False), wdays(x["end"], True), x["color"], wrange(x["start"], x["end"])) for x in it["rows"]]
            miles = [(m["name"], wdays(m["date"], True), m.get("color", MILE),
                      f"Semana {wsplit(m['date'])[0]}" + ("" if wsplit(m["date"])[1] is None else f" · {DAYS[wsplit(m['date'])[1] - 1]}")) for m in it["miles"]]
        else:
            rows = [(x["name"], pdate(x["start"]).toordinal(), pdate(x["end"]).toordinal(), x["color"],
                     f"{pdate(x['start']):%d/%m} - {pdate(x['end']):%d/%m}") for x in it["rows"]]
            miles = [(m["name"], pdate(m["date"]).toordinal(), m.get("color", MILE), f"{pdate(m['date']):%d/%m/%Y}") for m in it["miles"]]
        pad, top = T(16), y1 + T(16)
        tl = self.wrap(it["title"], T(22), W - 2 * pad) if it["title"] else []
        for k, line in enumerate(tl): texts.append(((x1 + x2) / 2, top + k * T(26), line, T(22), "n", col))
        if tl: top += T(38) + (T(26) if len(tl) > 1 else 0)
        n = len(rows)
        fs = T(16 if n <= 8 else max(9, int(16 * 8 / n))); ds = max(7, fs - round(4 * ts))  # más filas -> letra más pequeña
        labw = min(max([self.tkf(fs).measure(nm) for nm, *_ in rows] + [0]) + 10, W * .30)
        cx0, cx1 = x1 + pad + labw + 10, x2 - pad - (T(110) if W > 520 else 10)
        days = [d for _, a, b, *_ in rows for d in (a, b)] + [m[1] for m in miles]
        if not days or cx1 - cx0 < 40: return fills, lines, solids, texts  # no cabe: solo marco y título
        d0, d1 = (min(min(days), (it.get("start_week") or 1 << 30) * 7 - 7), max(days)) if wk else (min(days) - 1, max(days) + 1)
        if wk and d1 - d0 < 7: d1 = d0 + 7
        span = max(d1 - d0, 1)
        X = lambda d: cx0 + (d - d0) / span * (cx1 - cx0)
        # hitos: etiquetas centradas; si chocan, a la derecha; si tampoco cabe, en un nivel superior (hasta 4). Nombres largos en 2 líneas.
        LH = T(17)
        place, edge = [], [-1e9] * 4
        for nm, d, mc, lab in sorted(miles, key=lambda m: m[1]):
            x = X(d)

            def fit(anc, nm=nm, lab=lab, x=x):  # texto ajustado al hueco disponible dentro del marco
                cap = max(0, 2 * min(x - x1, x2 - x) - 8) if anc == "s" else max(0, x2 - x - 8)
                a, b = self.wrap(nm, T(13), cap), self.clip(lab, T(12), cap)
                return a, b, max([self.tkf(T(13)).measure(l) for l in a] + [self.tkf(T(12)).measure(b)])
            nat = self.wrap(nm, T(13), W * .4)  # el nombre como se vería con sitio de sobra
            found = None
            for strict in (True, False):  # 1.º sin recortar texto; 2.º recortando si hace falta
                for lv, anc in [(l, a) for l in range(4) for a in ("s", "sw")]:
                    a, b, w = fit(anc)
                    left = x - w / 2 if anc == "s" else x + 4
                    if all(a) and left >= edge[lv] + 6 and left >= x1 + 4 and left + w <= x2 - 4 and not (strict and (a != nat or b != lab)):
                        found = (a, b, w, left, lv, anc); break
                if found: break
            if not found:
                place.append((x, [], "", 0, "s", mc)); continue  # no cabe ninguna etiqueta sin pisar otra o salirse del marco
            a, b, w, left, lv, anc = found
            edge[lv] = left + w; place.append((x, a, b, lv, anc, mc))
        step = LH * (max([len(p[1]) for p in place] + [1]) + 1)  # alto de un nivel: líneas del nombre + la fecha
        base0 = max(T(27), 24)  # la fecha del hito nunca baja hasta el rombo (que mide ±9 px)
        ry1 = y2 - pad - T(30)
        used = lambda: max([p[3] for p in place if p[1]] + [0])  # nivel más alto con etiqueta
        head = lambda: T(6) if not miles else base0 + 1 + step * (used() + 1)
        while used() > 0 and ry1 - (top + head()) < max(20, n * T(14)):  # si las etiquetas dejan sin sitio a las filas, se quitan las de los niveles altos
            mx = used(); place = [(p[0], [], "", 0, "s", p[5]) if p[3] == mx and p[1] else p for p in place]
        ry0 = top + head()
        if ry1 - ry0 < 20: return fills, lines, solids, texts
        rh = (ry1 - ry0) / max(n, 1)
        fs = max(7, min(fs, int(rh / 1.2))); ds = max(7, min(ds, fs - 2))  # filas muy bajas: letra más pequeña
        for i, (name, a, b, colr, lab) in enumerate(rows):
            yc, bh = ry0 + rh * (i + .5), min(rh * .55, T(30))
            xa, xb = X(a), max(X(b), X(a) + 4)
            poly = [(xa, yc - bh / 2), (xb, yc - bh / 2), (xb, yc + bh / 2), (xa, yc + bh / 2)]
            fills.append((poly, colr))
            lines += [(jl(r, poly[k], poly[(k + 1) % 4]), col) for _ in range(2) for k in range(4)]
            nl = self.wrap(name, fs, labw - 10) if rh >= fs * 2.4 else [self.clip(name, fs, labw - 10)]  # 2 líneas si la fila lo permite
            for k, line in enumerate(nl): texts.append((cx0 - 10, yc + (k - (len(nl) - 1) / 2) * fs * 1.15, line, fs, "e", col))
            if xb + 8 + self.tkf(ds).measure(lab) <= x2 - 4: texts.append((xb + 8, yc, lab, ds, "w", sub))
        for x, nl, lab, lv, anc, mc in place:
            for yy in range(int(ry0 - 6), int(ry1), 14): lines.append((jl(r, (x, yy), (x, min(yy + 8, ry1)), 1.2), mc))
            solids.append(([(x, ry0 - 21), (x + 9, ry0 - 12), (x, ry0 - 3), (x - 9, ry0 - 12)], mc))
            if nl:
                xt = x if anc == "s" else x + 4
                for k, line in enumerate(nl): texts.append((xt, ry0 - base0 - LH - step * lv - (len(nl) - 1 - k) * LH, line, T(13), anc, col))
                texts.append((xt, ry0 - base0 - step * lv, lab, T(12), anc, sub))
        lines.append((jl(r, (cx0 - 8, ry1), (cx1 + 8, ry1), 1.5), col))
        grid = []
        if wk:
            ppw = (cx1 - cx0) * 7 / span  # píxeles por semana
            step = 1 if ppw >= T(34) else math.ceil(T(34) / ppw)  # etiquetas más espaciadas si no caben
            for day in range(math.ceil(d0 / 7) * 7, d1 + 1, 7):
                if ppw >= 4: lines.append(([(X(day), ry1), (X(day), ry1 + 8)], col))
                if ppw >= 14: grid.append(([(X(day) - 1, ry0 - 6), (X(day) + 1, ry0 - 6), (X(day) + 1, ry1), (X(day) - 1, ry1)], gridc))
            for k in range(d0 // 7 + 1, math.ceil(d1 / 7) + 1):
                if (k - 1) % step == 0:
                    texts.append((X(min(max((k - .5) * 7, d0), d1)), ry1 + T(10), f"Semana {k}" if ppw >= T(70) else f"S{k}", T(12), "n", col))
        else:
            dd0, dd1 = date.fromordinal(d0), date.fromordinal(d1)
            ppm = (cx1 - cx0) * 30.4 / span  # píxeles por mes
            step = max(1, math.ceil(T(76) / ppm))  # una etiqueta cada `step` meses para que no se pisen
            d, k, ticks = date(dd0.year, dd0.month, 1), 0, 0
            while d <= dd1:
                if d >= dd0:
                    if k % step == 0 or ppm >= 6: lines.append(([(X(d.toordinal()), ry1), (X(d.toordinal()), ry1 + 8)], col))
                    if k % step == 0:
                        texts.append((X(d.toordinal()), ry1 + T(10), f"{MESES[d.month - 1]} {d.year}", T(12), "n", col)); ticks += 1
                    k += 1
                d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
            if not ticks: texts.append((cx0, ry1 + T(10), f"{MESES[dd0.month - 1]} {dd0.year}", T(12), "nw", col))
        fills[1 if it["fill"] else 0:1 if it["fill"] else 0] = grid  # justo tras el fondo, debajo de barras e hitos
        return fills, lines, solids, texts
