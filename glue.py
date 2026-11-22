"""Puente JS <-> núcleo (gantt_core.py) para Pyodide. Todo entra y sale como JSON."""
import json, js
from gantt_core import *


class _F:
    def __init__(s, size, bold): s.size, s.bold = size, bold
    def measure(s, t): return js.measureText(t, s.size, s.bold)


class Web(Layout):
    def tkf(self, size): return _F(int(size), self.cur_bold)


def _err(e):
    w = getattr(e, "where", None)
    return json.dumps(dict(error=str(e), where=list(w) if w else None))


def compute(req):
    """Formulario -> piezas del gráfico (o error con el campo culpable)."""
    r = json.loads(req)
    try:
        d = {**clean_gantt(r["title"], r["rows"], r["miles"], r["scale"], r["start"], live=True), **clean_style(r["style"])}
        W, H = r["w"], r["h"]
        it = dict(d, x1=0, y1=0, x2=W, y2=H, seed=1, stroke=d["ink"], fill=d["paper"], sub=mix(d["ink"], d["paper"], .45), grid=mix(d["paper"], d["ink"], .18))
        return json.dumps(dict(parts=Web().gantt_parts(it), data=d, empty=not d["rows"] and not d["miles"]))
    except GanttError as e: return _err(e)


def switch(req):
    r = json.loads(req)
    try:
        d = clean_gantt(r["title"], r["rows"], r["miles"], r["scale"], "", live=True, keep=True)
        rows, miles = convert_gantt(d["rows"], d["miles"], r["scale"])
        return json.dumps(dict(rows=rows, miles=miles))
    except GanttError as e: return _err(e)


def parse(text):
    try: return json.dumps(dict(data=parse_gantt(json.loads(text.lstrip("﻿")))))
    except GanttError as e: return json.dumps(dict(error=f"Archivo de Gantt no válido: {e}"))
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError): return json.dumps(dict(error="Archivo de Gantt no válido"))


def sample(): return json.dumps({**sample_gantt(), "start_week": None, **STYLE0})
