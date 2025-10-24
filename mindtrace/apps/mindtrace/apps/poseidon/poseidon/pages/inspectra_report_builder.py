# pages/inspectra_report_builder.py
import io
import json
import random
from typing import Dict, List, Tuple

import reflex as rx


# ────────────────────────── Styles ──────────────────────────
def _css() -> rx.Component:
    return rx.html(
        """
        <style>
          .rb-shell { display:flex; justify-content:center; padding:24px; background:#f5f7fb; }
          .rb-page  { width:min(1100px, 100%); display:flex; flex-direction:column; gap:16px; }

          .rb-card {
            background:#fff; border:1px solid rgba(17,24,39,.08);
            border-radius:12px; box-shadow:0 1px 2px rgba(2,6,23,.05);
          }
          .rb-card-pad { padding:16px; }
          .rb-title { font-size:1.15rem; font-weight:800; color:#111827; }
          .rb-sub   { color:#6b7280; }

          .rb-row { display:flex; justify-content:space-between; align-items:center; gap:10px; }
          .rb-actions { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }

          .rb-select, .rb-chip, .rb-btn, .rb-ghost {
            border:1px solid rgba(17,24,39,.12);
            background:#fff; color:#111827;
            border-radius:10px; padding:8px 12px; font-weight:600;
          }
          .rb-select { min-width:180px; }
          .rb-ghost { background:#fff; }
          .rb-ghost:hover { background:#f3f4f6; }
          .rb-btn.primary {
            background:#7c3aed; color:#fff; border-color:#7c3aed;
          }
          .rb-btn.primary:hover { filter:brightness(0.98); }

          .rb-grid { display:grid; gap:12px; }
          .rb-grid.three { grid-template-columns: 1fr 1fr 1fr; }
          @media (max-width: 860px) { .rb-grid.three { grid-template-columns: 1fr; } }

          .rb-section-title { display:flex; align-items:center; gap:8px; font-weight:800; color:#111827; }
          .rb-muted { color:#6b7280; }

          .rb-ol { display:flex; flex-direction:column; gap:6px; margin-top:8px; }
          .rb-li { display:flex; gap:10px; align-items:flex-start; }
          .rb-li-num {
            width:22px; height:22px; border-radius:999px; background:#eef2ff; color:#3730a3;
            font-weight:800; font-size:.85rem; display:flex; align-items:center; justify-content:center; flex:0 0 22px;
            border:1px solid rgba(17,24,39,.08);
          }

          .rb-footer-actions { display:flex; gap:14px; }
          .rb-export { flex:1; text-align:center; padding:10px 12px; border-radius:10px; border:1px solid rgba(17,24,39,.12); }
          .rb-export:hover { background:#f9fafb; cursor:pointer; }

          .rb-config {
            background:#fafafa; border:1px dashed rgba(17,24,39,.2);
            border-radius:10px; padding:10px; font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
            color:#374151; font-size:.9rem; white-space:pre-wrap;
          }
        </style>
        """
    )


# ────────────────────────── Choices ──────────────────────────
REGIONS: List[str] = ["Globe", "North America", "Europe", "APAC", "LATAM", "MEA"]
METRICS: List[str] = ["Yield Rate", "Defect Rate", "Uptime", "Throughput", "Scrap %"]
DATE_PRESETS: List[str] = ["Today", "Yesterday", "Last 7 Days", "Last 30 Days", "This Quarter", "This Year"]


# ────────────────────────── State ──────────────────────────
class ReportBuilderState(rx.State):
    # Filters
    region: str = "Globe"
    metric: str = "Yield Rate"
    date_preset: str = "Last 7 Days"

    # UI
    show_config: bool = False
    is_generating: bool = False
    last_report_id: str = ""

    # Dummy report data (reseeded on generate)
    kpis: Dict[str, str] = {}
    site_yield: List[Tuple[str, float]] = []     # for bar chart
    defect_series: List[Tuple[str, float]] = []  # for line chart

    # Events
    @rx.event
    def set_region(self, v: str): self.region = v

    @rx.event
    def set_metric(self, v: str): self.metric = v

    @rx.event
    def set_preset(self, v: str): self.date_preset = v

    @rx.event
    def toggle_config(self): self.show_config = not self.show_config

    @rx.var
    def config_json(self) -> str:
        cfg = {
            "region": self.region,
            "metric": self.metric,
            "date": self.date_preset,
            "report_id": self.last_report_id or "(generate first)",
        }
        return json.dumps(cfg, indent=2)

    # ── Generate report (populate dummy data) ───────────────
    @rx.event
    def generate_report(self):
        self.is_generating = True
        self.last_report_id = f"RPT-{random.randint(10000, 99999)}"

        rnd = random.Random()  # new seed each run
        # KPIs
        yield_rate = round(rnd.uniform(88, 97), 2)
        defect_rate = round(rnd.uniform(2.5, 7.5), 2)
        uptime = round(rnd.uniform(92, 99), 2)
        throughput = rnd.randint(120_000, 180_000)
        scrap = round(rnd.uniform(0.7, 2.2), 2)

        self.kpis = {
            "Report ID": self.last_report_id,
            "Region": self.region,
            "Date Range": self.date_preset,
            "Selected Metric": self.metric,
            "Yield Rate": f"{yield_rate} %",
            "Defect Rate": f"{defect_rate} %",
            "Uptime": f"{uptime} %",
            "Throughput": f"{throughput:,}",
            "Scrap %": f"{scrap} %",
        }

        # Site yields for bar chart
        sites = ["Lakewood", "Ramos", "Clanton", "Memphis", "Austin", "Detroit"]
        self.site_yield = [(s, round(rnd.uniform(70, 97), 2)) for s in sites]

        # Defect rate trend (line)
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        base = defect_rate
        self.defect_series = [(d, max(0.5, round(base + rnd.uniform(-1.2, 1.4), 2))) for d in days]

        self.is_generating = False

    # ───────────────────── CONFIG (PDF LOOK & FEEL) ─────────────────────
    _PDF = {
        "page_w": 612, "page_h": 792,                 # US Letter points
        "margin": 40,
        "band_h": 62,
        "colors": {
            "band": (0.95, 0.96, 1.00),
            "grid": (0.82, 0.86, 0.95),
            "axis": (0.20, 0.22, 0.30),
            "text": (0.05, 0.06, 0.08),
            "kpi_label": (0.36, 0.40, 0.52),
            "bar": (0.15, 0.43, 0.96),
            "line": (0.96, 0.33, 0.27),
        },
        "font": {"title": 18, "sub": 11, "body": 11, "small": 8},
    }

    # ── Export helpers ──────────────────────────────────────
    def _try_logo_jpeg(self) -> Tuple[bytes, int, int] | Tuple[None, None, None]:
        """Try to load assets/mindtrace-logo.png and convert to JPEG in-memory."""
        try:
            from PIL import Image  # type: ignore
            import os
            path = os.path.join("assets", "mindtrace-logo.png")
            with Image.open(path) as im:
                im = im.convert("RGB")
                max_w = 160
                if im.width > max_w:
                    ratio = max_w / im.width
                    im = im.resize((int(im.width * ratio), int(im.height * ratio)))
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=90)
                data = buf.getvalue()
                return data, im.width, im.height
        except Exception:
            return (None, None, None)
        return (None, None, None)

    def _pdf_text_escape(self, s: str) -> str:
        """Normalize to latin-1 friendly text and escape PDF parens/backslashes."""
        s = str(s)
        # Normalize common Unicode punctuation to latin-1 equivalents
        replacements = {
            "\u2022": "\u00B7",  # bullet • -> middle dot · (latin-1)
            "\u2013": "-",       # en dash
            "\u2014": "-",       # em dash
            "\u2018": "'",       # left single quote
            "\u2019": "'",       # right single quote / apostrophe
            "\u201C": '"',       # left double quote
            "\u201D": '"',       # right double quote
            "\u00A0": " ",       # non-breaking space
            "\u2212": "-",       # minus sign
        }
        for k, v in replacements.items():
            s = s.replace(k, v)
        # Replace any remaining non-latin-1 chars with '?'
        s = "".join(ch if ord(ch) < 256 else "?" for ch in s)
        # Escape PDF special characters
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


    def _rgb(self, r: float, g: float, b: float, stroke=False) -> str:
        return f"{r:.3f} {g:.3f} {b:.3f} {'RG' if stroke else 'rg'}"

    def _ticks(self, vmin: float, vmax: float, n: int = 5) -> List[float]:
        if vmax <= vmin:
            return [vmin] * n
        step = (vmax - vmin) / (n - 1)
        return [round(vmin + i * step, 1) for i in range(n)]

    def _build_pdf(self) -> bytes:
        """
        One-page branded PDF with logo, title, meta, KPI grid,
        and TWO VERTICAL charts (more whitespace from grid).
        Helvetica only; latin-1 safe text via _pdf_text_escape.
        """
        # -------- tiny pdf object helpers ----------
        objects: List[bytes] = []
        offsets: List[int] = []

        def w(b: bytes):
            offsets.append(sum(len(o) for o in objects))
            objects.append(b)

        # Try to prep a JPEG logo XObject
        logo_jpeg, logo_w, logo_h = self._try_logo_jpeg()
        resources_extras = b""
        image_obj_num = None

        if logo_jpeg:
            image_obj_num = 6
            w(
                f"{image_obj_num} 0 obj << /Type /XObject /Subtype /Image /Width {logo_w} /Height {logo_h} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(logo_jpeg)} >> stream\n".encode(
                    "latin-1"
                )
                + logo_jpeg
                + b"\nendstream endobj\n"
            )
            resources_extras = b"/XObject << /Im1 6 0 R >>"

        # ----- page drawing helpers (content stream parts) -----
        stream_parts: List[str] = []

        def txt(x, y, size, s, gray=None):
            s = self._pdf_text_escape(str(s))
            if gray is not None:
                stream_parts.append(f"{gray} g")
            stream_parts.append(f"BT /F1 {size} Tf {x} {y} Td ({s}) Tj ET")
            if gray is not None:
                stream_parts.append("0 g")  # reset fill to black

        def stroke_rgb(r, g, b, width=1):
            stream_parts.append(f"{r} {g} {b} RG {width} w")

        def fill_rgb(r, g, b):
            stream_parts.append(f"{r} {g} {b} rg")

        def rect(x, y, w_, h_, fill=False, stroke=True):
            stream_parts.append(f"{x} {y} {w_} {h_} re")
            if fill and stroke:
                stream_parts.append("B")
            elif fill:
                stream_parts.append("f")
            elif stroke:
                stream_parts.append("S")

        def line(x1, y1, x2, y2):
            stream_parts.append(f"{x1} {y1} m {x2} {y2} l S")

        # ---------- Header band ----------
        fill_rgb(0.96, 0.97, 1.00)
        rect(0, 724, 612, 68, fill=True, stroke=False)

        margin_x = 40
        title_x = margin_x
        if image_obj_num:
            draw_h = 42
            draw_w = int(logo_w * (draw_h / max(1, logo_h)))
            x, y = margin_x, 740
            stream_parts.append("q")
            stream_parts.append(f"{draw_w} 0 0 {draw_h} {x} {y} cm /Im1 Do")
            stream_parts.append("Q")
            title_x = x + draw_w + 14

        txt(title_x, 760, 18, "Strategic Report")
        txt(title_x, 744, 11, f"{self.region} · {self.date_preset}", gray=0.35)
        txt(440, 760, 10, "Generated by Inspectra", gray=0.35)

        txt(margin_x, 710, 10, f"Report ID: {self.kpis.get('Report ID', self.last_report_id or 'N/A')}", gray=0.35)
        txt(260, 710, 10, f"Metric: {self.metric}", gray=0.35)

        # ---------- KPI grid (2 rows x 4 cols) ----------
        grid_x, grid_y = margin_x, 650
        grid_w, grid_h = 532, 90
        cell_w, cell_h = grid_w / 4, grid_h / 2

        stroke_rgb(0.80, 0.84, 0.93, width=0.8)
        fill_rgb(0.92, 0.94, 0.98)
        rect(grid_x, grid_y - grid_h, grid_w, grid_h, fill=True, stroke=True)

        stroke_rgb(0.75, 0.78, 0.86, width=0.7)
        for i in range(1, 4):
            x = grid_x + i * cell_w
            line(x, grid_y, x, grid_y - grid_h)
        line(grid_x, grid_y - cell_h, grid_x + grid_w, grid_y - cell_h)

        kpi_pairs = [
            ("Yield Rate", self.kpis.get("Yield Rate", "-")),
            ("Defect Rate", self.kpis.get("Defect Rate", "-")),
            ("Uptime", self.kpis.get("Uptime", "-")),
            ("Throughput", self.kpis.get("Throughput", "-")),
            ("Scrap %", self.kpis.get("Scrap %", "-")),
            ("Region", self.kpis.get("Region", "-")),
            ("Date Range", self.kpis.get("Date Range", "-")),
            ("Selected Metric", self.kpis.get("Selected Metric", "-")),
        ]
        idx = 0
        for row in range(2):
            for col in range(4):
                if idx >= len(kpi_pairs):
                    break
                lx = grid_x + col * cell_w + 12
                ly = grid_y - row * cell_h - 16
                vx = lx
                vy = ly - 16
                label, value = kpi_pairs[idx]
                txt(lx, ly, 9, label, gray=0.45)
                txt(vx, vy, 12, value)
                idx += 1

        # ---------- Charts (VERTICAL STACK) ----------
        # Extra whitespace below the KPI grid
        # Grid bottom is at (grid_y - grid_h) = 560; we start charts well lower.
        chart_left = margin_x + 8
        chart_width = 612 - 2 * margin_x - 16  # near full width (~496–532)
        bar_h = 150
        line_h = 150

        # BAR: Yield by Site — upper chart
        chart_x, chart_y = chart_left, 470  # lower Y -> more gap from grid
        chart_w, chart_h = chart_width, bar_h

        stroke_rgb(0.25, 0.27, 0.32, width=0.9)
        line(chart_x, chart_y, chart_x + chart_w, chart_y)
        line(chart_x, chart_y, chart_x, chart_y + chart_h)

        # y ticks & gridlines every 10 from 60..100
        stroke_rgb(0.82, 0.86, 0.92, width=0.5)
        for tick in (60, 70, 80, 90, 100):
            ty = chart_y + (tick - 60) / 40 * chart_h
            line(chart_x, ty, chart_x + chart_w, ty)
            txt(chart_x - 24, ty - 3, 8, str(tick), gray=0.45)

        txt(chart_x, chart_y + chart_h + 14, 11, "Yield by Site (%)")

        bars = self.site_yield or [("Site A", 80), ("Site B", 90)]
        max_val = max(100, max(v for _, v in bars))
        min_base = 60
        bw = chart_w / max(1, len(bars))
        fill_rgb(0.15, 0.43, 0.96)
        stroke_rgb(0.15, 0.43, 0.96, width=0.5)
        for i, (label, val) in enumerate(bars):
            h = chart_h * ((val - min_base) / (max_val - min_base))
            h = max(0, min(chart_h, h))
            x0 = chart_x + i * bw + 6
            w0 = bw - 12
            rect(x0, chart_y, w0, h, fill=True, stroke=False)
            txt(chart_x + i * bw + 2, chart_y - 12, 8, label[:12], gray=0.4)

        # LINE: Defect Rate Trend — lower chart
        l_x, l_y = chart_left, 280  # stacked below the bar chart
        l_w, l_h = chart_width, line_h

        stroke_rgb(0.25, 0.27, 0.32, width=0.9)
        line(l_x, l_y, l_x + l_w, l_y)
        line(l_x, l_y, l_x, l_y + l_h)

        series = self.defect_series or [("Mon", 4.0), ("Tue", 4.5), ("Wed", 5.1)]
        min_y = min(v for _, v in series)
        max_y = max(v for _, v in series)
        pad = (max_y - min_y) * 0.15 or 0.5
        min_y -= pad
        max_y += pad

        stroke_rgb(0.82, 0.86, 0.92, width=0.5)
        for i in range(5):
            tval = min_y + i * (max_y - min_y) / 4
            ty = l_y + (0 if max_y == min_y else (tval - min_y) / (max_y - min_y)) * l_h
            line(l_x, ty, l_x + l_w, ty)
            txt(l_x - 28, ty - 3, 8, f"{tval:.1f}", gray=0.45)

        txt(l_x, l_y + l_h + 14, 11, "Defect Rate Trend (%)")

        pts = []
        for i, (lab, val) in enumerate(series):
            px = l_x + (i * (l_w / max(1, len(series) - 1)))
            py = l_y + (0 if max_y == min_y else (val - min_y) / (max_y - min_y)) * l_h
            pts.append((px, py))
            txt(px - 6, l_y - 12, 8, lab, gray=0.4)

        if pts:
            stroke_rgb(0.96, 0.33, 0.27, width=1.6)
            stream_parts.append(f"{pts[0][0]} {pts[0][1]} m")
            for (px, py) in pts[1:]:
                stream_parts.append(f"{px} {py} l")
            stream_parts.append("S")
            fill_rgb(1, 1, 1)
            for (px, py) in pts:
                stream_parts.append(f"{px-1.8} {py-1.8} 3.6 3.6 re f")
                stroke_rgb(0.96, 0.33, 0.27, width=0.8)
                stream_parts.append(f"{px-1.8} {py-1.8} 3.6 3.6 re S")

        # ---------- footer ----------
        txt(margin_x, 36, 9, "© Mindtrace · Generated with Inspectra", gray=0.45)

        # Assemble content stream
        stream_bytes = ("\n".join(stream_parts) + "\n").encode("latin-1")

        # ----- PDF objects -----
        w(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
        w(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
        w(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
        w(f"5 0 obj << /Length {len(stream_bytes)} >> stream\n".encode("latin-1"))
        w(stream_bytes)
        w(b"endstream endobj\n")

        res = b"<< /Font << /F1 4 0 R >> "
        if resources_extras:
            res += resources_extras + b" "
        res += b">>"
        w(b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources " + res + b" /Contents 5 0 R >> endobj\n")

        # xref + trailer
        xref_pos = sum(len(o) for o in objects)
        out = [b"%PDF-1.4\n"] + objects
        xref = ["xref", f"0 {len(objects)+1}", "0000000000 65535 f "]
        for off in offsets:
            xref.append(f"{off+len(b'%PDF-1.4\\n'):010d} 00000 n ")

        trailer = (
            "trailer << /Size " + str(len(objects)+1) + " /Root 1 0 R >>\n"
            "startxref\n" + str(xref_pos + len(b"%PDF-1.4\n")) + "\n%%EOF\n"
        ).encode("latin-1")

        return b"".join(out) + ("\n".join(xref) + "\n").encode("latin-1") + trailer


    @rx.event
    def export_pdf(self):
        if not self.kpis:
            self.generate_report()
        pdf = self._build_pdf()
        name = f"{self.last_report_id or 'report'}.pdf"
        return rx.download(data=pdf, filename=name)

    @rx.event
    def export_excel(self):
        if not self.kpis:
            self.generate_report()

        # CSV with KPIs, a blank row, then site yields, then defect series
        lines: List[str] = []
        lines.append("Field,Value")
        for k, v in self.kpis.items():
            lines.append(f"{k},{v}")

        lines.append("")  # spacer
        lines.append("Site,Yield %")
        for s, val in self.site_yield:
            lines.append(f"{s},{val}")

        lines.append("")
        lines.append("Day,Defect Rate %")
        for d, val in self.defect_series:
            lines.append(f"{d},{val}")

        csv_data = ("\n".join(lines)).encode("utf-8")
        name = f"{self.last_report_id or 'report'}.csv"
        return rx.download(data=csv_data, filename=name)


# ────────────────────────── UI Fragments ──────────────────────────
def _header() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.text("Strategic Report Builder", class_name="rb-title"),
                rx.text("Generate comprehensive operational reports", class_name="rb-sub"),
                align_items="start",
                gap="2px",
            ),
            rx.spacer(),
            rx.hstack(
                rx.button(
                    rx.icon("eye"),
                    rx.text(" Show Config", as_="span"),
                    class_name="rb-ghost",
                    on_click=ReportBuilderState.toggle_config,
                ),
                rx.button(
                    rx.icon("sparkles"),
                    rx.text(" Generate Report", as_="span"),
                    class_name="rb-btn primary",
                    on_click=ReportBuilderState.generate_report,
                ),
                class_name="rb-actions",
            ),
            align="center",
            width="100%",
        ),
        class_name="rb-card rb-card-pad",
    )


def _filters() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.hstack(rx.icon("sliders-horizontal"), rx.text(" Filter Reports", weight="bold")),
            align="center",
            gap="8px",
        ),
        rx.box(
            rx.box(
                rx.select(REGIONS, value=ReportBuilderState.region, on_change=ReportBuilderState.set_region, class_name="rb-select"),
                rx.select(METRICS, value=ReportBuilderState.metric, on_change=ReportBuilderState.set_metric, class_name="rb-select"),
                rx.hstack(
                    rx.icon("calendar"),
                    rx.select(DATE_PRESETS, value=ReportBuilderState.date_preset, on_change=ReportBuilderState.set_preset, class_name="rb-select"),
                    align="center",
                    gap="8px",
                ),
                class_name="rb-grid three",
            ),
            margin_top="12px",
        ),
        class_name="rb-card rb-card-pad",
    )


def _structure() -> rx.Component:
    items = [
        "Executive Summary",
        "Global Performance Overview",
        "Site-by-Site Analysis",
        "Trend Analysis & Forecasting",
        "Critical Alerts & Actions",
        "AI ROI Assessment",
        "Recommendations",
    ]
    ol = rx.box(
        *[
            rx.box(
                rx.box(rx.text(str(i + 1)), class_name="rb-li-num"),
                rx.text(label),
                class_name="rb-li",
            )
            for i, label in enumerate(items)
        ],
        class_name="rb-ol",
    )
    return rx.box(
        rx.hstack(rx.icon("layout-list"), rx.text(" Report Structure", weight="bold"), align="center", gap="8px"),
        ol,
        rx.hstack(
            rx.box(
                rx.hstack(rx.icon("download"), rx.text(" Export PDF", as_="span"), justify="center", align="center", gap="8px"),
                class_name="rb-export",
                on_click=ReportBuilderState.export_pdf,
            ),
            rx.box(
                rx.hstack(rx.icon("download"), rx.text(" Export to Excel", as_="span"), justify="center", align="center", gap="8px"),
                class_name="rb-export",
                on_click=ReportBuilderState.export_excel,
            ),
            class_name="rb-footer-actions",
            margin_top="16px",
        ),
        class_name="rb-card rb-card-pad",
    )


def _config_panel() -> rx.Component:
    return rx.cond(
        ReportBuilderState.show_config,
        rx.box(
            rx.text("Current Configuration", weight="bold"),
            rx.box(rx.text(ReportBuilderState.config_json), class_name="rb-config", margin_top="8px"),
            class_name="rb-card rb-card-pad",
        ),
        None,
    )


# ────────────────────────── Page ──────────────────────────
def strategic_report_builder() -> rx.Component:
    return rx.box(
        _css(),
        rx.box(
            _header(),
            _filters(),
            _structure(),
            _config_panel(),
            class_name="rb-page",
        ),
        class_name="rb-shell",
    )
