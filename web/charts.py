"""
Inline SVG charts for the control panel.

The panel ships no charting library (and loads nothing from a CDN), so these
render plain SVG the browser can style: geometry is computed here, colours come
from the panel's CSS variables. Everything is drawn in a fixed viewBox and
scaled by CSS, so the charts stay sharp and responsive.
"""

from __future__ import annotations

import html

# Fixed drawing surface; CSS scales it to the container width.
_WIDTH = 900
_HEIGHT = 220
_PAD_LEFT = 44
_PAD_BOTTOM = 26
_PAD_TOP = 10


def _nice_ceiling(value: int) -> int:
    """Round an axis maximum up to something readable (10, 25, 500, 2000...)."""
    if value <= 5:
        return max(1, value)
    magnitude = 10 ** (len(str(value)) - 1)
    for step in (1, 1.5, 2, 2.5, 5, 10):
        candidate = int(magnitude * step)
        if candidate >= value:
            return candidate
    return value


def bar_chart(
    points: list[dict],
    *,
    key: str,
    value: str = "count",
    tick=str,
    empty: str = "No data for this period.",
) -> str:
    """A labelled bar chart. ``points`` are dicts holding a label and a count.

    ``tick`` formats a point's label for the x axis (the full label is kept for
    the hover tooltip).
    """
    if not points:
        return f'<p class="muted">{html.escape(empty)}</p>'

    counts = [max(0, int(point[value])) for point in points]
    top = _nice_ceiling(max(counts) or 1)
    plot_width = _WIDTH - _PAD_LEFT
    plot_height = _HEIGHT - _PAD_BOTTOM - _PAD_TOP
    slot = plot_width / len(points)
    # Keep a visible gap between bars until they get too thin for one to matter.
    bar_width = max(1.0, slot * (0.7 if slot > 4 else 0.9))

    bars = ""
    for index, point in enumerate(points):
        count = counts[index]
        height = (count / top) * plot_height
        x = _PAD_LEFT + index * slot + (slot - bar_width) / 2
        y = _PAD_TOP + plot_height - height
        label = html.escape(f"{point[key]}: {count}")
        bars += (
            f'<rect class="bar" x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{height:.2f}" rx="1">'
            f"<title>{label}</title></rect>"
        )

    # Horizontal guides at 0 / 50% / 100% of the axis.
    guides = ""
    for fraction in (0, 0.5, 1):
        y = _PAD_TOP + plot_height - fraction * plot_height
        guides += f'<line class="guide" x1="{_PAD_LEFT}" y1="{y:.2f}" x2="{_WIDTH}" y2="{y:.2f}"></line>'
        guides += f'<text class="axis" x="{_PAD_LEFT - 8}" y="{y + 4:.2f}" text-anchor="end">{int(top * fraction)}</text>'

    # Only label a few x positions, otherwise dense ranges turn into mush.
    ticks = ""
    step = max(1, len(points) // 8)
    for index in range(0, len(points), step):
        x = _PAD_LEFT + index * slot + slot / 2
        ticks += (
            f'<text class="axis" x="{x:.2f}" y="{_HEIGHT - 8}" text-anchor="middle">'
            f"{html.escape(tick(points[index][key]))}</text>"
        )

    return f'<svg class="chart" viewBox="0 0 {_WIDTH} {_HEIGHT}" role="img">{guides}{bars}{ticks}</svg>'


def hour_chart(hours: list[int]) -> str:
    """Activity by hour of day (UTC), as a 24-slot bar chart."""
    points = [{"hour": f"{hour:02d}:00", "count": count} for hour, count in enumerate(hours)]
    if not any(hours):
        return '<p class="muted">No data for this period.</p>'
    return bar_chart(points, key="hour")
