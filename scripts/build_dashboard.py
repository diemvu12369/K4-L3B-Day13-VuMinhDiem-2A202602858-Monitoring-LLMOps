"""Dựng dashboard 6 panel từ data/logs.jsonl theo contract config/dashboard.yaml.

Output là một file HTML tĩnh (SVG inline, không cần thư viện ngoài):

    python scripts/build_dashboard.py            # ghi data/dashboard.html
    python scripts/build_dashboard.py --watch    # dựng lại mỗi refresh_seconds
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio
from app.metrics import percentile

LOCAL_TZ = timezone(timedelta(hours=7))
W, H, PAD_L, PAD_R, PAD_T, PAD_B = 520, 190, 52, 16, 14, 28


def load_records(path: Path) -> list[dict]:
    records = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
            record["_ts"] = datetime.fromisoformat(record["ts"].replace("Z", "+00:00"))
            records.append(record)
        except (ValueError, KeyError):
            continue
    return records


def by_minute(records: list[dict], start: datetime) -> dict[int, list[dict]]:
    buckets: dict[int, list[dict]] = defaultdict(list)
    for record in records:
        buckets[int((record["_ts"] - start).total_seconds() // 60)].append(record)
    return buckets


def compute(records: list[dict], start: datetime, minutes: int) -> dict:
    sent = [r for r in records if r.get("event") == "response_sent"]
    received = [r for r in records if r.get("event") == "request_received"]
    failed = [r for r in records if r.get("event") == "request_failed"]
    tools = [r for r in records if r.get("tool_success") is not None]
    sent_m, recv_m, fail_m, tool_m = (by_minute(x, start) for x in (sent, received, failed, tools))

    def series(fn, buckets):
        return [(m, fn(buckets[m])) for m in range(minutes) if buckets.get(m)]

    lat = lambda p: (lambda rs: percentile([r["latency_ms"] for r in rs], p))
    return {
        "latency": {
            "series": [
                ("P50", 1, series(lat(50), sent_m)),
                ("P95", 2, series(lat(95), sent_m)),
                ("P99", 3, series(lat(99), sent_m)),
                ("TTFT P95", 4, series(lambda rs: percentile([r["ttft_ms"] for r in rs], 95), sent_m)),
            ],
            "stats": {
                "p50": percentile([r["latency_ms"] for r in sent], 50),
                "p95": percentile([r["latency_ms"] for r in sent], 95),
                "p99": percentile([r["latency_ms"] for r in sent], 99),
                "ttft_p95": percentile([r["ttft_ms"] for r in sent], 95),
            },
        },
        "traffic": {
            "series": [("Requests/phút", 1, series(len, recv_m))],
            "bars": True,
            "stats": {
                "count": len(received),
                "rate_per_minute": round(len(received) / minutes, 2),
            },
        },
        "errors": {
            "series": [
                ("Error rate %", 8, [
                    (m, round(100 * len(fail_m.get(m, [])) / len(recv_m[m]), 2))
                    for m in range(minutes) if recv_m.get(m)
                ]),
                ("Retrieval success %", 1, series(
                    lambda rs: round(100 * sum(r["tool_success"] is True for r in rs) / len(rs), 2), tool_m
                )),
            ],
            "stats": {
                "error_rate_pct": round(100 * len(failed) / max(1, len(received)), 2),
                "tool_success_rate_pct": round(
                    100 * sum(r["tool_success"] is True for r in tools) / max(1, len(tools)), 2
                ),
                "count_by_value": ", ".join(
                    f"{error}: {count}" for error, count in Counter(r.get("error_type") for r in failed).items()
                ) or "không có lỗi",
            },
        },
        "cost": {
            "series": [("USD/phút", 1, series(lambda rs: round(sum(r["cost_usd"] for r in rs), 6), sent_m))],
            "bars": True,
            "stats": {"total": round(sum(r["cost_usd"] for r in sent), 4)},
        },
        "tokens": {
            "series": [
                ("tokens_in", 1, series(lambda rs: sum(r["tokens_in"] for r in rs), sent_m)),
                ("tokens_out", 2, series(lambda rs: sum(r["tokens_out"] for r in rs), sent_m)),
            ],
            "stats": {
                "sum_by_field": sum(r["tokens_in"] + r["tokens_out"] for r in sent),
                "tokens_in": sum(r["tokens_in"] for r in sent),
                "tokens_out": sum(r["tokens_out"] for r in sent),
            },
        },
        "quality": {
            "series": [("Mean quality", 1, series(lambda rs: round(mean(r["quality_score"] for r in rs), 3), sent_m))],
            "stats": {"mean": round(mean(r["quality_score"] for r in sent), 3) if sent else 0.0},
        },
    }


def nice_max(value: float) -> float:
    if value <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(value))
    return next(step * magnitude for step in (1, 2, 4, 8, 10) if value <= step * magnitude)


def fmt(value: float) -> str:
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:.3g}" if abs(value) < 1 else f"{value:,.1f}"


def chart(panel: dict, minutes: int, start: datetime, threshold_line: float | None, unit: str) -> str:
    values = [v for _, _, points in panel["series"] for _, v in points]
    y_max = nice_max(max(values + ([threshold_line] if threshold_line is not None else []) or [1]) * 1.1)
    if unit == "percent":
        y_max = 100.0
    plot_w, plot_h = W - PAD_L - PAD_R, H - PAD_T - PAD_B
    x = lambda m: PAD_L + plot_w * (m + 0.5) / minutes
    y = lambda v: PAD_T + plot_h * (1 - v / y_max)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" class="chart">']
    for i in range(5):
        gv = y_max * i / 4
        out.append(f'<line class="grid" x1="{PAD_L}" x2="{W - PAD_R}" y1="{y(gv):.1f}" y2="{y(gv):.1f}"/>')
        out.append(f'<text class="tick" x="{PAD_L - 6}" y="{y(gv) + 4:.1f}" text-anchor="end">{fmt(gv)}</text>')
    for m in range(0, minutes + 1, 15):
        label = (start + timedelta(minutes=m)).astimezone(LOCAL_TZ).strftime("%H:%M")
        out.append(f'<text class="tick" x="{PAD_L + plot_w * m / minutes:.1f}" y="{H - 8}" text-anchor="middle">{label}</text>')
    if threshold_line is not None:
        out.append(f'<line class="threshold" x1="{PAD_L}" x2="{W - PAD_R}" y1="{y(threshold_line):.1f}" y2="{y(threshold_line):.1f}"/>')
        out.append(f'<text class="threshold-label" x="{PAD_L + 6}" y="{y(threshold_line) - 5:.1f}">ngưỡng {fmt(threshold_line)}</text>')
    bar_w = max(2.0, plot_w / minutes - 2)
    for name, slot, points in panel["series"]:
        if panel.get("bars"):
            for m, v in points:
                top = y(v)
                out.append(
                    f'<rect class="bar" style="fill:var(--series-{slot})" x="{x(m) - bar_w / 2:.1f}" y="{top:.1f}" '
                    f'width="{bar_w:.1f}" height="{max(0.5, y(0) - top):.1f}" rx="2">'
                    f'<title>{name} {(start + timedelta(minutes=m)).astimezone(LOCAL_TZ):%H:%M}: {fmt(v)}</title></rect>'
                )
            continue
        if len(points) > 1:
            path = " ".join(f"{x(m):.1f},{y(v):.1f}" for m, v in points)
            out.append(f'<polyline class="line" style="stroke:var(--series-{slot})" points="{path}"/>')
        for m, v in points:
            out.append(
                f'<circle class="dot" style="fill:var(--series-{slot})" cx="{x(m):.1f}" cy="{y(v):.1f}" r="4">'
                f'<title>{name} {(start + timedelta(minutes=m)).astimezone(LOCAL_TZ):%H:%M}: {fmt(v)}</title></circle>'
            )
    out.append("</svg>")
    return "".join(out)


def status(value: float, threshold: dict) -> tuple[bool, str]:
    ok = value <= threshold["value"] if threshold["operator"] == "lte" else value >= threshold["value"]
    op = "≤" if threshold["operator"] == "lte" else "≥"
    return ok, f"{threshold['aggregation']} = {fmt(value)} (yêu cầu {op} {fmt(threshold['value'])})"


# Ngưỡng nào so sánh được với giá trị theo phút thì vẽ thành đường trên biểu đồ.
LINE_THRESHOLDS = {"p95", "rate_per_minute", "error_rate_pct", "mean"}


def render(config: dict, data: dict, start: datetime, end: datetime, n_records: int) -> str:
    dash = config["dashboard"]
    minutes = dash["time_range_minutes"]
    cards = []
    for panel in dash["panels"]:
        pdata = data[panel["id"]]
        threshold = panel["threshold"]
        ok, status_text = status(pdata["stats"][threshold["aggregation"]], threshold)
        line = threshold["value"] if threshold["aggregation"] in LINE_THRESHOLDS else None
        legend = "".join(
            f'<span class="key"><i style="background:var(--series-{slot})"></i>{html.escape(name)}</span>'
            for name, slot, _ in pdata["series"]
        ) if len(pdata["series"]) > 1 else ""
        stats = "".join(
            f"<tr><th>{html.escape(k)}</th><td>{html.escape(fmt(v) if isinstance(v, (int, float)) else str(v))}</td></tr>"
            for k, v in pdata["stats"].items()
        )
        has_data = any(points for _, _, points in pdata["series"])
        cards.append(f"""
<section class="card">
  <header><h2>{html.escape(panel['title'])}</h2><span class="unit">{html.escape(panel['unit'])}</span></header>
  <p class="status {'ok' if ok else 'bad'}"><b>{'✓ Đạt' if ok else ('✗ Vượt ngưỡng' if threshold['operator'] == 'lte' else '✗ Dưới ngưỡng')}</b> · {html.escape(status_text)}</p>
  {chart(pdata, minutes, start, line, panel['unit']) if has_data else '<p class="empty">Không có dữ liệu trong cửa sổ thời gian.</p>'}
  <div class="legend">{legend}</div>
  <table>{stats}</table>
  <p class="query"><code>{html.escape(panel['query'])}</code></p>
</section>""")
    fmt_t = lambda t: t.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{dash['refresh_seconds']}">
<title>Day13 Dashboard</title>
<style>
:root {{ color-scheme: light; --surface-0:#f4f3f0; --surface-1:#fcfcfb; --border:#e2e1dc; --grid:#ecebe7;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#7a7975;
  --series-1:#2a78d6; --series-2:#eb6834; --series-3:#1baf7a; --series-4:#eda100; --series-8:#e34948;
  --good:#006300; --critical:#d03b3b; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ color-scheme: dark; --surface-0:#111110;
  --surface-1:#1a1a19; --border:#2e2e2c; --grid:#262624; --text-primary:#fff; --text-secondary:#c3c2b7;
  --text-muted:#8f8e86; --series-1:#3987e5; --series-2:#d95926; --series-3:#199e70; --series-4:#c98500;
  --series-8:#e66767; --good:#0ca30c; --critical:#e66767; }} }}
:root[data-theme="dark"] {{ color-scheme: dark; --surface-0:#111110; --surface-1:#1a1a19; --border:#2e2e2c;
  --grid:#262624; --text-primary:#fff; --text-secondary:#c3c2b7; --text-muted:#8f8e86; --series-1:#3987e5;
  --series-2:#d95926; --series-3:#199e70; --series-4:#c98500; --series-8:#e66767; --good:#0ca30c; --critical:#e66767; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; padding:16px; background:var(--surface-0); color:var(--text-primary);
  font:14px/1.45 system-ui, "Segoe UI", sans-serif; }}
h1 {{ font-size:20px; margin:0 0 4px; }}
.meta {{ color:var(--text-secondary); margin:0 0 16px; }}
.grid-panels {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 520px), 1fr)); gap:16px; }}
.card {{ background:var(--surface-1); border:1px solid var(--border); border-radius:10px; padding:14px 16px; min-width:0; }}
.card header {{ display:flex; justify-content:space-between; align-items:baseline; gap:8px; }}
h2 {{ font-size:15px; margin:0; }}
.unit {{ color:var(--text-muted); font-size:12px; }}
.status {{ margin:6px 0; color:var(--text-secondary); font-size:13px; }}
.status.ok b {{ color:var(--good); }} .status.bad b {{ color:var(--critical); }}
.chart {{ width:100%; height:auto; display:block; }}
.grid {{ stroke:var(--grid); stroke-width:1; }}
.tick {{ fill:var(--text-muted); font-size:11px; }}
.threshold {{ stroke:var(--text-secondary); stroke-width:1.5; stroke-dasharray:6 4; }}
.threshold-label {{ fill:var(--text-secondary); font-size:11px; }}
.line {{ fill:none; stroke-width:2; }}
.dot {{ stroke:var(--surface-1); stroke-width:2; }}
.dot:hover, .bar:hover {{ opacity:.75; }}
.legend {{ display:flex; flex-wrap:wrap; gap:4px 14px; font-size:12px; color:var(--text-secondary); min-height:4px; }}
.key i {{ display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; vertical-align:-1px; }}
table {{ border-collapse:collapse; margin-top:8px; font-size:12px; font-variant-numeric:tabular-nums; }}
th {{ text-align:left; font-weight:500; color:var(--text-secondary); padding:1px 16px 1px 0; }}
.query {{ margin:8px 0 0; font-size:11px; color:var(--text-muted); overflow-wrap:anywhere; }}
.empty {{ color:var(--text-muted); }}
</style></head>
<body>
<h1>{html.escape(dash['title'])}</h1>
<p class="meta">Time range: {fmt_t(start)} → {fmt_t(end)} (UTC+7, {minutes} phút) · refresh {dash['refresh_seconds']}s ·
nguồn <code>data/logs.jsonl</code> ({n_records} records trong cửa sổ) · dựng lúc {fmt_t(datetime.now(timezone.utc))}</p>
<div class="grid-panels">{''.join(cards)}</div>
</body></html>"""


def build(config_path: Path, log_path: Path, out_path: Path) -> str:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    minutes = config["dashboard"]["time_range_minutes"]
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=1)
    start = end - timedelta(minutes=minutes)
    records = [r for r in load_records(log_path) if start <= r["_ts"] < end]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(config, compute(records, start, minutes), start, end, len(records)), encoding="utf-8")
    return f"Đã ghi {out_path} ({len(records)} records trong {minutes} phút gần nhất)"


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Dựng dashboard 6 panel từ data/logs.jsonl")
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "config" / "dashboard.yaml")
    parser.add_argument("--logs", type=Path, default=REPO_ROOT / "data" / "logs.jsonl")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "dashboard.html")
    parser.add_argument("--watch", action="store_true", help="Dựng lại theo refresh_seconds")
    args = parser.parse_args()
    while True:
        print(build(args.config, args.logs, args.out))
        if not args.watch:
            return 0
        config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
        time.sleep(config["dashboard"]["refresh_seconds"])


if __name__ == "__main__":
    raise SystemExit(main())
