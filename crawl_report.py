"""
Crawl speed report — computed from the crawl_runs table so it works no matter which
entrypoint ran the crawl (web app, CLI, or the scheduled job).

`get_speed_report()` returns the most recent crawl batch's timing: wall-clock, per-vendor
durations, the slowest few, and whether the run was parallel or sequential.
"""
from datetime import datetime
from pathlib import Path


def _parse(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    # The DB mixes tz-aware (pipeline) and naive (CLI) timestamps; normalize to naive
    # UTC so they compare cleanly.
    return dt.replace(tzinfo=None)


def get_speed_report(db_path, batch_window_seconds: int = 3600) -> dict | None:
    """Timing summary for the latest crawl batch.

    A "batch" = all finished runs whose start is within `batch_window_seconds` of the most
    recent finish — i.e. one crawl, whether its vendors ran in parallel (overlapping) or
    sequentially (back-to-back)."""
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT cr.vendor_key AS vendor_key, v.vendor_name AS vendor_name,
               cr.started_at AS started_at, cr.finished_at AS finished_at
        FROM crawl_runs cr
        LEFT JOIN vendors v ON v.vendor_key = cr.vendor_key
        WHERE cr.finished_at IS NOT NULL AND cr.started_at IS NOT NULL
        ORDER BY cr.id DESC LIMIT 400
    """).fetchall()
    conn.close()
    if not rows:
        return None

    parsed = []
    for r in rows:
        s, f = _parse(r["started_at"]), _parse(r["finished_at"])
        if s and f and f >= s:
            parsed.append((r["vendor_key"], r["vendor_name"] or r["vendor_key"], s, f))
    if not parsed:
        return None

    newest_finish = max(p[3] for p in parsed)
    batch = [p for p in parsed
             if (newest_finish - p[2]).total_seconds() <= batch_window_seconds]
    if not batch:
        return None

    wall_start = min(p[2] for p in batch)
    wall_end = max(p[3] for p in batch)
    wall = (wall_end - wall_start).total_seconds()

    per_vendor = sorted(
        ((vk, name, (f - s).total_seconds()) for vk, name, s, f in batch),
        key=lambda t: t[2], reverse=True)
    total_vendor_secs = sum(t[2] for t in per_vendor)

    # Parallel if the vendors' work overlapped meaningfully (sum >> wall-clock).
    parallel = total_vendor_secs > wall * 1.3 and len(batch) > 1

    return {
        "vendors": len(batch),
        "wall_seconds": round(wall, 1),
        "total_vendor_seconds": round(total_vendor_secs, 1),
        "avg_seconds": round(total_vendor_secs / len(batch), 1),
        "parallel": parallel,
        "slowest": [(vk, name, round(secs, 1)) for vk, name, secs in per_vendor[:5]],
        "finished_at": wall_end.isoformat(timespec="seconds"),
    }


def format_speed_report(rep: dict | None) -> str:
    """Plain-text speed report for CLI/log output."""
    if not rep:
        return "No crawl timing available."
    mode = "parallel" if rep["parallel"] else "sequential"
    lines = [
        "── Crawl Speed Report ─────────────────────────────",
        f"  Vendors:      {rep['vendors']}",
        f"  Wall-clock:   {rep['wall_seconds']:.0f}s ({rep['wall_seconds']/60:.1f} min)  [{mode}]",
        f"  Vendor-time:  {rep['total_vendor_seconds']:.0f}s total, {rep['avg_seconds']:.0f}s avg",
        "  Slowest:",
    ]
    for vk, name, secs in rep["slowest"]:
        lines.append(f"    {(name or vk):28} {secs:6.0f}s")
    return "\n".join(lines)
