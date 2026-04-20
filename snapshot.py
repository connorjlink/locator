from __future__ import annotations

import argparse
import io
import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.pyplot as plt
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.patches import ConnectionPatch, Rectangle


@dataclass(frozen=True)
class Region:
    minimum_longitude: float
    maximum_longitude: float
    minimum_latitude: float
    maximum_latitude: float

    def normalized(self) -> "Region":
        longitude0, longitude1 = sorted((self.minimum_longitude, self.maximum_longitude))
        latitude0, latitude1 = sorted((self.minimum_latitude, self.maximum_latitude))
        return Region(longitude0, longitude1, latitude0, latitude1)

    def as_extent(self) -> list[float]:
        return [self.minimum_longitude, self.maximum_longitude, self.minimum_latitude, self.maximum_latitude]


DEFAULT_WORLD_REGION = Region(-11.0, -5.0, 50.5, 56.5)
DEFAULT_ZOOM_REGION = Region(
    -8.742559512271514,
    -8.510014263814636,
    52.614007667018164,
    52.71198728589052,
)
DEFAULT_STAR = (52.6698042403715, -8.577276842533156)  # (latitute, longitude)


DEFAULT_THEME: dict[str, Any] = {
    "oceancolor": "#000000",
    "landcolor": "#0F0F0F",
    "watercolor": "#29449b",
    "bordercolor": "#A4A4A4",
    "starcolor": "#C8A51C",
    "insetcolor": "#880000",
    "textcolor": "#FFFFFF",
    "fontfamily": "serif",
    "inset_size": 0.30,
    "inset_margin": 0.02,
    "title_fontsize": 6,
    "inset_title_fontsize": 6,
    "caption_fontsize": 5.5,
}


def haversine_m(latitude1: float, longitude1: float, latitude2: float, longitude2: float) -> float:
    r = 6371000.0
    phi1 = math.radians(latitude1)
    phi2 = math.radians(latitude2)
    dphi = phi2 - phi1
    dlambda = math.radians(longitude2 - longitude1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def cluster_points(
    points: list[tuple[float, float]],
    *,
    min_distance_m: float,
) -> list[tuple[float, float, int]]:
    if not points:
        return []
    if min_distance_m <= 0:
        return [(latitute, longitude, 1) for (latitute, longitude) in points]

    clusters: list[tuple[float, float, int]] = []
    for latitute, longitude in points:
        assigned = False
        for index, (clat, clon, count) in enumerate(clusters):
            if haversine_m(latitute, longitude, clat, clon) <= min_distance_m:
                # update centroid as running mean
                new_count = count + 1
                new_lat = (clat * count + latitute) / new_count
                new_lon = (clon * count + longitude) / new_count
                clusters[index] = (new_lat, new_lon, new_count)
                assigned = True
                break
        if not assigned:
            clusters.append((latitute, longitude, 1))
    return clusters


def _read_points_csv(path: str) -> list[tuple[float, float]]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Points file not found: {p}")
    points: list[tuple[float, float]] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [x.strip() for x in line.split(",")]
        if len(parts) != 2:
            raise ValueError(f"Invalid points line (expected 'latitute,longitude'): {raw!r}")
        points.append((float(parts[0]), float(parts[1])))
    return points


def _auto_region_from_points(points: list[tuple[float, float]]) -> Region:
    if not points:
        return DEFAULT_WORLD_REGION.normalized()

    latitutes = [p[0] for p in points]
    longitudes = [p[1] for p in points]
    latitude0, latitude1 = min(latitutes), max(latitutes)
    longitude0, longitude1 = min(longitudes), max(longitudes)

    # if points span most of the globe, fall back to a global-ish region.
    if (longitude1 - longitude0) > 180:
        return Region(-180.0, 180.0, max(-80.0, latitude0 - 5.0), min(80.0, latitude1 + 5.0)).normalized()

    lat_span = max(0.01, latitude1 - latitude0)
    lon_span = max(0.01, longitude1 - longitude0)
    latitude_padded = max(0.5, lat_span * 0.35)
    longitude_padded = max(0.5, lon_span * 0.35)
    return Region(longitude0 - longitude_padded, longitude1 + longitude_padded, latitude0 - latitude_padded, latitude1 + latitude_padded).normalized()


def render_summary_map(
    *,
    points_lat_lon: list[tuple[float, float]],
    min_distance_m: float,
    caption: str | None,
    world_region: Region | None,
    theme: dict[str, Any],
    out_path: str,
    dpi: int,
    fig_width_in: float,
    show: bool,
) -> None:
    proj = ccrs.PlateCarree()

    world_region = (world_region or _auto_region_from_points(points_lat_lon)).normalized()
    aspect_main = geographic_aspect(world_region)
    fig_h = fig_width_in * aspect_main
    fig = plt.figure(figsize=(fig_width_in, fig_h), dpi=dpi)
    fig.patch.set_facecolor(str(theme.get("oceancolor", DEFAULT_THEME["oceancolor"])))
    fig.patch.set_edgecolor("none")

    ax = fig.add_axes([0, 0, 1, 1], projection=proj)
    ax.set_extent(world_region.as_extent())
    ax.add_feature(cfeature.LAND, facecolor=theme["landcolor"])
    ax.add_feature(cfeature.OCEAN, facecolor=theme["oceancolor"])
    ax.add_feature(cfeature.BORDERS, linewidth=0.5, edgecolor=theme["bordercolor"])
    ax.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor=theme["bordercolor"])
    ax.set_aspect("equal", adjustable="box")

    clusters = cluster_points(points_lat_lon, min_distance_m=min_distance_m)
    for latitute, longitude, count in clusters:
        # slightly scale star size for clusters, but keep it subtle.
        ms = 7.0 + min(6.0, 1.5 * math.log10(max(1, count)))
        ax.plot(longitude, latitute, marker="*", color=theme["starcolor"], markersize=ms, transform=proj, zorder=6)

    if caption:
        ax.text(
            0.02,
            0.02,
            caption,
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=float(theme.get("caption_fontsize", DEFAULT_THEME["caption_fontsize"])),
            fontfamily=str(theme.get("fontfamily", DEFAULT_THEME["fontfamily"])),
            color=str(theme.get("textcolor", DEFAULT_THEME["textcolor"])),
            zorder=10,
        )

    plt.savefig(
        out_path,
        bbox_inches="tight",
        pad_inches=0,
        dpi=dpi,
        facecolor=fig.get_facecolor(),
        edgecolor="none",
    )
    if show:
        plt.show()


def geographic_aspect(region: Region) -> float:
    region = region.normalized()
    mean_latitude = (region.minimum_latitude + region.maximum_latitude) / 2
    denominator = (region.maximum_longitude - region.minimum_longitude) * math.cos(math.radians(mean_latitude))
    if denominator == 0:
        return 1.0
    return (region.maximum_latitude - region.minimum_latitude) / denominator


def _float_list(values: Iterable[str], count: int, name: str) -> list[float]:
    vals = list(values)
    if len(vals) != count:
        raise argparse.ArgumentTypeError(f"{name} expects {count} numbers, got {len(vals)}")
    try:
        return [float(v) for v in vals]
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"{name} expects floats: {e}") from e


def parse_region(values: list[str]) -> Region:
    minimum_longitude, maximum_longitude, minimum_latitude, maximum_latitude = _float_list(values, 4, "region")
    return Region(minimum_longitude, maximum_longitude, minimum_latitude, maximum_latitude).normalized()


def parse_coordinates(values: list[str]) -> tuple[float, float]:
    latitude, longitude = _float_list(values, 2, "latitude/longitude")
    return (latitude, longitude)


def load_theme(theme_path: str | None) -> dict[str, Any]:
    theme = dict(DEFAULT_THEME)
    if not theme_path:
        return theme

    p = Path(theme_path)
    if not p.is_file():
        raise FileNotFoundError(f"Theme file not found: {p}")

    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Theme JSON must be an object (dictionary).")

    theme.update(data)
    return theme


def _add_svg_badge(ax, svg_path: str, size_px: int, xy_axes: tuple[float, float]) -> None:
    try:
        import cairosvg
        from PIL import Image
    except Exception as e:
        raise RuntimeError(
            "Rendering SVG requires `cairosvg` and `Pillow`. "
            "Install with: pip install cairosvg pillow"
        ) from e

    svg_bytes = Path(svg_path).read_bytes()
    png_bytes = cairosvg.svg2png(bytestring=svg_bytes, output_width=size_px, output_height=size_px)
    image = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    offset = OffsetImage(image, zoom=0.2)
    ab = AnnotationBbox(
        offset,
        xy_axes,
        xycoords=ax.transAxes,
        frameon=False,
        box_alignment=(1, 0),
        zorder=10,
    )
    ax.add_artist(ab)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _gap_px_to_fig(fig, gap_px: float) -> float:
    px = max(0.0, float(gap_px))
    width_px = max(1.0, fig.get_figwidth() * fig.dpi)
    height_px = max(1.0, fig.get_figheight() * fig.dpi)
    return px / min(width_px, height_px)


def _point_in_rect(
    x: float,
    y: float,
    rect_x0: float,
    rect_y0: float,
    rect_x1: float,
    rect_y1: float,
    *,
    pad: float = 0.0,
) -> bool:
    return (rect_x0 - pad) <= x <= (rect_x1 + pad) and (rect_y0 - pad) <= y <= (rect_y1 + pad)


def _rects_overlap(
    ax0: float, ay0: float, ax1: float, ay1: float,
    bx0: float, by0: float, bx1: float, by1: float,
    *,
    pad: float = 0.0,
) -> bool:
    return not (
        (ax1 <= bx0 + pad) or
        (ax0 >= bx1 - pad) or
        (ay1 <= by0 + pad) or
        (ay0 >= by1 - pad)
    )


def _rect_distance_sq(
    ax0: float, ay0: float, ax1: float, ay1: float,
    bx0: float, by0: float, bx1: float, by1: float,
) -> float:
    dx = max(bx0 - ax1, ax0 - bx1, 0.0)
    dy = max(by0 - ay1, ay0 - by1, 0.0)
    return dx * dx + dy * dy


def _data_to_fig(fig, ax, x: float, y: float) -> tuple[float, float]:
    x_disp, y_disp = ax.transData.transform((x, y))
    return fig.transFigure.inverted().transform((x_disp, y_disp))


def _segments_intersect(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]) -> bool:
    def orient(p, q, r) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on_segment(p, q, r) -> bool:
        return min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)

    if o1 == 0 and on_segment(a, c, b):
        return True
    if o2 == 0 and on_segment(a, d, b):
        return True
    if o3 == 0 and on_segment(c, a, d):
        return True
    if o4 == 0 and on_segment(c, b, d):
        return True

    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


def _best_connector_pairs(fig, ax_main, ax_inset, zoom_region: Region) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    # zoom corners in fixed order
    zoom_data = [
        (zoom_region.minimum_longitude, zoom_region.minimum_latitude),  # bl
        (zoom_region.maximum_longitude, zoom_region.minimum_latitude),  # br
        (zoom_region.maximum_longitude, zoom_region.maximum_latitude),  # tr
        (zoom_region.minimum_longitude, zoom_region.maximum_latitude),  # tl
    ]
    zoom_fig = [_data_to_fig(fig, ax_main, x, y) for (x, y) in zoom_data]

    inset_axes = [(0, 0), (1, 0), (1, 1), (0, 1)]  # bl, br, tr, tl
    inset_fig: list[tuple[float, float]] = []
    for xa, ya in inset_axes:
        xd, yd = ax_inset.transAxes.transform((xa, ya))
        xf, yf = fig.transFigure.inverted().transform((xd, yd))
        inset_fig.append((xf, yf))

    best_perm: tuple[int, int, int, int] | None = None
    best_key = (10**9, float("inf"))  # (crossings, total_distance_sq)

    for perm in itertools.permutations(range(4)):
        segs = [(zoom_fig[i], inset_fig[perm[i]]) for i in range(4)]

        crossings = 0
        for i in range(4):
            for j in range(i + 1, 4):
                if _segments_intersect(segs[i][0], segs[i][1], segs[j][0], segs[j][1]):
                    crossings += 1

        dist = 0.0
        for i in range(4):
            dx = zoom_fig[i][0] - inset_fig[perm[i]][0]
            dy = zoom_fig[i][1] - inset_fig[perm[i]][1]
            dist += dx * dx + dy * dy

        key = (crossings, dist)
        if key < best_key:
            best_key = key
            best_perm = perm

    assert best_perm is not None
    return [(zoom_data[i], inset_axes[best_perm[i]]) for i in range(4)]


def _pick_inset_position(
    *,
    fig,
    ax_main,
    star_lon: float,
    star_lat: float,
    inset_size: float,
    inset_margin: float,
    bounds_xmin: float,
    bounds_xmax: float,
    bounds_ymin: float,
    bounds_ymax: float,
    rect_xmin: float,
    rect_xmax: float,
    rect_ymin: float,
    rect_ymax: float,
    min_gap_fig: float = 0.005
) -> tuple[float, float, float]:
    bounds_w = max(0.0, bounds_xmax - bounds_xmin)
    bounds_h = max(0.0, bounds_ymax - bounds_ymin)

    max_size = min(bounds_w - 2.0 * inset_margin, bounds_h - 2.0 * inset_margin)
    max_size = max(0.08, max_size)
    size = min(inset_size, max_size)

    x_disp, y_disp = ax_main.transData.transform((star_lon, star_lat))
    star_x, star_y = fig.transFigure.inverted().transform((x_disp, y_disp))

    star_pad = 0.02
    gap = max(0.002, inset_margin * 0.6)
    min_clearance = max(gap, 0.008, max(0.0, min_gap_fig))

    rcx = (rect_xmin + rect_xmax) * 0.5
    rcy = (rect_ymin + rect_ymax) * 0.5

    # prefer side with more map space available
    usable_xmin = bounds_xmin + inset_margin
    usable_xmax = bounds_xmax - inset_margin
    usable_ymin = bounds_ymin + inset_margin
    usable_ymax = bounds_ymax - inset_margin

    left_space = max(0.0, rect_xmin - usable_xmin)
    right_space = max(0.0, usable_xmax - rect_xmax)
    bottom_space = max(0.0, rect_ymin - usable_ymin)
    top_space = max(0.0, usable_ymax - rect_ymax)

    x_eps = max(1e-9, 0.02 * bounds_w)
    y_eps = max(1e-9, 0.02 * bounds_h)

    x_pref = 1 if (right_space - left_space) > x_eps else (-1 if (left_space - right_space) > x_eps else 0)
    y_pref = 1 if (top_space - bottom_space) > y_eps else (-1 if (bottom_space - top_space) > y_eps else 0)

    def candidate_positions(s: float) -> list[tuple[float, float]]:
        top = rect_ymax + gap
        bottom = rect_ymin - s - gap
        left = rect_xmin - s - gap
        right = rect_xmax + gap
        cx = rcx - s * 0.5
        cy = rcy - s * 0.5
        return [
            (right, cy),              # right-adjacent
            (left, cy),               # left-adjacent
            (cx, top),                # above-adjacent
            (cx, bottom),             # below-adjacent
            (right, top),             # top-right diagonal
            (left, top),              # top-left diagonal
            (right, bottom),          # bottom-right diagonal
            (left, bottom),           # bottom-left diagonal
            (right, rect_ymin),       # right, lower aligned
            (right, rect_ymax - s),   # right, upper aligned
            (left, rect_ymin),        # left, lower aligned
            (left, rect_ymax - s),    # left, upper aligned
            (rect_xmin, top),         # above, left aligned
            (rect_xmax - s, top),     # above, right aligned
            (rect_xmin, bottom),      # below, left aligned
            (rect_xmax - s, bottom),  # below, right aligned
        ]

    def side_penalty(x0: float, y0: float, s: float) -> float:
        cx = x0 + s * 0.5
        cy = y0 + s * 0.5
        p = 0.0
        if x_pref != 0:
            on_right = cx >= rcx
            if (x_pref == 1 and not on_right) or (x_pref == -1 and on_right):
                p += 1.0
        if y_pref != 0:
            on_top = cy >= rcy
            if (y_pref == 1 and not on_top) or (y_pref == -1 and on_top):
                p += 0.35
        return p

    def nudge_away(x0: float, y0: float, s: float) -> tuple[float, float]:
        for _ in range(6):
            x1, y1 = x0 + s, y0 + s
            d2 = _rect_distance_sq(x0, y0, x1, y1, rect_xmin, rect_ymin, rect_xmax, rect_ymax)
            if d2 >= (min_clearance * min_clearance):
                break

            need = min_clearance - math.sqrt(max(0.0, d2))
            ccx = x0 + s * 0.5
            ccy = y0 + s * 0.5
            dx = ccx - rcx
            dy = ccy - rcy

            if abs(dx) >= abs(dy):
                step = need if dx >= 0 else -need
                x0 = _clamp(x0 + step, usable_xmin, usable_xmax - s)
            else:
                step = need if dy >= 0 else -need
                y0 = _clamp(y0 + step, usable_ymin, usable_ymax - s)

        return x0, y0

    for _ in range(12):
        # pass 1: enforce min_clearance
        # pass 2: allow tighter if no solution
        for require_clearance in (True, False):
            best: tuple[float, float] | None = None
            # (side_penalty, distance_to_zoom, -distance_to_star)
            best_key = (float("inf"), float("inf"), float("inf"))

            for x0, y0 in candidate_positions(size):
                x0 = _clamp(x0, usable_xmin, usable_xmax - size)
                y0 = _clamp(y0, usable_ymin, usable_ymax - size)
                x1, y1 = x0 + size, y0 + size

                if _point_in_rect(star_x, star_y, x0, y0, x1, y1, pad=star_pad):
                    continue

                if _rects_overlap(x0, y0, x1, y1, rect_xmin, rect_ymin, rect_xmax, rect_ymax, pad=0.0):
                    continue

                d_zoom = _rect_distance_sq(x0, y0, x1, y1, rect_xmin, rect_ymin, rect_xmax, rect_ymax)
                if require_clearance and d_zoom < (min_clearance * min_clearance):
                    continue

                cx, cy = x0 + size * 0.5, y0 + size * 0.5
                d_star = (cx - star_x) ** 2 + (cy - star_y) ** 2
                key = (side_penalty(x0, y0, size), d_zoom, -d_star)
                if key < best_key:
                    best_key = key
                    best = (x0, y0)

            if best is not None:
                bx, by = nudge_away(best[0], best[1], size)
                return bx, by, size

        size *= 0.9
        if size < 0.08:
            size = 0.08

    # final safe fallback inside map bounds
    x0 = _clamp(bounds_xmax - size - inset_margin, usable_xmin, usable_xmax - size)
    y0 = _clamp(bounds_ymax - size - inset_margin, usable_ymin, usable_ymax - size)
    x0, y0 = nudge_away(x0, y0, size)
    return x0, y0, size


def _pick_inset_position_corner_snap(
    *,
    fig,
    ax_main,
    star_lon: float,
    star_lat: float,
    inset_size: float,
    inset_margin: float,
    bounds_xmin: float,
    bounds_xmax: float,
    bounds_ymin: float,
    bounds_ymax: float,
    rect_xmin: float,
    rect_xmax: float,
    rect_ymin: float,
    rect_ymax: float,
    min_gap_fig: float = 0.005
) -> tuple[float, float, float]:
    bounds_w = max(0.0, bounds_xmax - bounds_xmin)
    bounds_h = max(0.0, bounds_ymax - bounds_ymin)

    max_size = min(bounds_w - 2.0 * inset_margin, bounds_h - 2.0 * inset_margin)
    max_size = max(0.08, max_size)
    size = min(inset_size, max_size)

    min_clearance = max(0.0, min_gap_fig)

    x_disp, y_disp = ax_main.transData.transform((star_lon, star_lat))
    star_x, star_y = fig.transFigure.inverted().transform((x_disp, y_disp))

    star_pad = 0.02
    usable_xmin = bounds_xmin + inset_margin
    usable_xmax = bounds_xmax - inset_margin
    usable_ymin = bounds_ymin + inset_margin
    usable_ymax = bounds_ymax - inset_margin

    def corners(s: float) -> list[tuple[float, float]]:
        return [
            (usable_xmin, usable_ymin),          # bottom-left
            (usable_xmax - s, usable_ymin),      # bottom-right
            (usable_xmax - s, usable_ymax - s),  # top-right
            (usable_xmin, usable_ymax - s),      # top-left
        ]

    for _ in range(14):
        best: tuple[float, float] | None = None
        # (distance_to_zoom_rect, -distance_to_star)
        best_key = (float("inf"), float("inf"))

        for x0, y0 in corners(size):
            x0 = _clamp(x0, usable_xmin, usable_xmax - size)
            y0 = _clamp(y0, usable_ymin, usable_ymax - size)
            x1, y1 = x0 + size, y0 + size

            if _rects_overlap(x0, y0, x1, y1, rect_xmin, rect_ymin, rect_xmax, rect_ymax, pad=0.0):
                continue
            if _point_in_rect(star_x, star_y, x0, y0, x1, y1, pad=star_pad):
                continue

            d_zoom = _rect_distance_sq(x0, y0, x1, y1, rect_xmin, rect_ymin, rect_xmax, rect_ymax)
            if d_zoom < (min_clearance * min_clearance):
                continue
            cx, cy = x0 + size * 0.5, y0 + size * 0.5
            d_star = (cx - star_x) ** 2 + (cy - star_y) ** 2
            key = (d_zoom, -d_star)
            if key < best_key:
                best_key = key
                best = (x0, y0)

        if best is not None:
            return best[0], best[1], size

        size *= 0.9
        if size < 0.08:
            size = 0.08

    fallback_best: tuple[float, float] | None = None
    # (overlap_penalty, star_penalty, distance_to_zoom_rect)
    fallback_key = (10**9, 10**9, float("inf"))
    for x0, y0 in corners(size):
        x0 = _clamp(x0, usable_xmin, usable_xmax - size)
        y0 = _clamp(y0, usable_ymin, usable_ymax - size)
        x1, y1 = x0 + size, y0 + size

        overlap_penalty = 1 if _rects_overlap(x0, y0, x1, y1, rect_xmin, rect_ymin, rect_xmax, rect_ymax, pad=0.0) else 0
        star_penalty = 1 if _point_in_rect(star_x, star_y, x0, y0, x1, y1, pad=star_pad) else 0
        d_zoom = _rect_distance_sq(x0, y0, x1, y1, rect_xmin, rect_ymin, rect_xmax, rect_ymax)
        gap_penalty = 0 if d_zoom >= (min_clearance * min_clearance) else 1
        key = (overlap_penalty, star_penalty, gap_penalty, d_zoom)
        if key < fallback_key:
            fallback_key = key
            fallback_best = (x0, y0)

    assert fallback_best is not None
    return fallback_best[0], fallback_best[1], size


def _expand_world_for_zoom(
    world_region: Region,
    zoom_region: Region,
    *,
    edge_buffer_frac: float = 0.06,
    min_buffer_deg: float = 0.03,
) -> Region:
    world = world_region.normalized()
    zoom = zoom_region.normalized()

    lon_span = max(0.01, world.maximum_longitude - world.minimum_longitude)
    lat_span = max(0.01, world.maximum_latitude - world.minimum_latitude)
    lon_buf = max(min_buffer_deg, lon_span * edge_buffer_frac)
    lat_buf = max(min_buffer_deg, lat_span * edge_buffer_frac)

    return Region(
        min(world.minimum_longitude, zoom.minimum_longitude - lon_buf),
        max(world.maximum_longitude, zoom.maximum_longitude + lon_buf),
        min(world.minimum_latitude, zoom.minimum_latitude - lat_buf),
        max(world.maximum_latitude, zoom.maximum_latitude + lat_buf),
    ).normalized()


def render_map(
    *,
    world_region: Region,
    zoom_region: Region,
    star_lat_lon: tuple[float, float],
    title_main: str,
    title_inset: str,
    caption: str | None,
    clock_svg: str | None,
    theme: dict[str, Any],
    out_path: str,
    dpi: int,
    fig_width_in: float,
    show: bool,
    clock_size_px: int,
    inset_placement_mode: str = "smart",
) -> None:
    proj = ccrs.PlateCarree()

    world_region = world_region.normalized()
    zoom_region = zoom_region.normalized()
    world_region = _expand_world_for_zoom(world_region, zoom_region)

    star_lat, star_lon = star_lat_lon

    inset_size = float(theme.get("inset_size", DEFAULT_THEME["inset_size"]))
    inset_margin = float(theme.get("inset_margin", DEFAULT_THEME["inset_margin"]))

    aspect_main = geographic_aspect(world_region)
    fig_h = fig_width_in * aspect_main
    fig = plt.figure(figsize=(fig_width_in, fig_h), dpi=dpi)
    fig.patch.set_facecolor(str(theme.get("oceancolor", DEFAULT_THEME["oceancolor"])))
    fig.patch.set_edgecolor("none")

    ax_main = fig.add_axes([0, 0, 1, 1], projection=proj)
    ax_main.set_extent(world_region.as_extent())
    ax_main.add_feature(cfeature.LAND, facecolor=theme["landcolor"])
    ax_main.add_feature(cfeature.OCEAN, facecolor=theme["oceancolor"])
    ax_main.add_feature(cfeature.BORDERS, linewidth=0.5, edgecolor=theme["bordercolor"])
    ax_main.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor=theme["bordercolor"])
    ax_main.set_aspect("equal", adjustable="box")

    ax_main.plot(
        star_lon,
        star_lat,
        marker="*",
        color=theme["starcolor"],
        markersize=10,
        transform=proj,
        zorder=7,
    )

    fig.canvas.draw()

    # inset bounds in figure coordinates
    wx0, wy0 = _data_to_fig(fig, ax_main, world_region.minimum_longitude, world_region.minimum_latitude)
    wx1, wy1 = _data_to_fig(fig, ax_main, world_region.maximum_longitude, world_region.maximum_latitude)
    map_xmin, map_xmax = min(wx0, wx1), max(wx0, wx1)
    map_ymin, map_ymax = min(wy0, wy1), max(wy0, wy1)

    # zoom source data in figure coordinates
    rx0, ry0 = _data_to_fig(fig, ax_main, zoom_region.minimum_longitude, zoom_region.minimum_latitude)
    rx1, ry1 = _data_to_fig(fig, ax_main, zoom_region.maximum_longitude, zoom_region.maximum_latitude)
    rect_xmin, rect_xmax = min(rx0, rx1), max(rx0, rx1)
    rect_ymin, rect_ymax = min(ry0, ry1), max(ry0, ry1)

    mode = str(inset_placement_mode).strip().lower()
    if mode == "corner-snap":
        x0, y0, inset_size = _pick_inset_position_corner_snap(
            fig=fig,
            ax_main=ax_main,
            star_lon=star_lon,
            star_lat=star_lat,
            inset_size=inset_size,
            inset_margin=inset_margin,
            bounds_xmin=map_xmin,
            bounds_xmax=map_xmax,
            bounds_ymin=map_ymin,
            bounds_ymax=map_ymax,
            rect_xmin=rect_xmin,
            rect_xmax=rect_xmax,
            rect_ymin=rect_ymin,
            rect_ymax=rect_ymax,
        )
    else:
        x0, y0, inset_size = _pick_inset_position(
            fig=fig,
            ax_main=ax_main,
            star_lon=star_lon,
            star_lat=star_lat,
            inset_size=inset_size,
            inset_margin=inset_margin,
            bounds_xmin=map_xmin,
            bounds_xmax=map_xmax,
            bounds_ymin=map_ymin,
            bounds_ymax=map_ymax,
            rect_xmin=rect_xmin,
            rect_xmax=rect_xmax,
            rect_ymin=rect_ymin,
            rect_ymax=rect_ymax,
        )

    ax_inset = fig.add_axes([x0, y0, inset_size, inset_size], projection=proj, zorder=5)
    
    inset_edge = str(theme.get("insetcolor", DEFAULT_THEME["insetcolor"]))
    if "geo" in ax_inset.spines:
        ax_inset.spines["geo"].set_edgecolor(inset_edge)
        ax_inset.spines["geo"].set_linewidth(0.9)
    else:
        for spine in ax_inset.spines.values():
            spine.set_edgecolor(inset_edge)
            spine.set_linewidth(0.9)

    ax_inset.set_extent(zoom_region.as_extent())
    ax_inset.add_feature(cfeature.LAND, facecolor=theme["landcolor"])
    ax_inset.add_feature(cfeature.BORDERS, linewidth=0.25, edgecolor=theme.get("bordercolor", "black"))
    ax_inset.add_feature(cfeature.COASTLINE, linewidth=0.25, edgecolor=theme.get("bordercolor", "black"))
    ax_inset.add_feature(cfeature.RIVERS, linewidth=0.5, edgecolor=theme["watercolor"])
    ax_inset.add_feature(cfeature.OCEAN, linewidth=0.5, facecolor=theme["watercolor"])
    ax_inset.add_feature(cfeature.LAKES, linewidth=0.5, facecolor=theme["watercolor"])
    ax_inset.plot(star_lon, star_lat, marker="*", color=theme["starcolor"], markersize=9, transform=proj, zorder=5)

    ax_inset.text(
        0.02,
        0.97,
        title_inset,
        transform=ax_inset.transAxes,
        ha="left",
        va="top",
        fontsize=float(theme.get("inset_title_fontsize", DEFAULT_THEME["inset_title_fontsize"])) ,
        fontfamily=str(theme.get("fontfamily", DEFAULT_THEME["fontfamily"])) ,
        color=str(theme.get("textcolor", DEFAULT_THEME["textcolor"])) ,
        zorder=6,
    )

    if clock_svg:
        _add_svg_badge(ax_inset, clock_svg, clock_size_px, (0.98, 0.02))

    if caption:
        ax_inset.text(
            0.02,
            0.02,
            caption,
            transform=ax_inset.transAxes,
            ha="left",
            va="bottom",
            fontsize=float(theme.get("caption_fontsize", DEFAULT_THEME["caption_fontsize"])) ,
            fontfamily=str(theme.get("fontfamily", DEFAULT_THEME["fontfamily"])) ,
            color=str(theme.get("textcolor", DEFAULT_THEME["textcolor"])) ,
            zorder=11,
        )

    rect = Rectangle(
        (zoom_region.minimum_longitude, zoom_region.minimum_latitude),
        zoom_region.maximum_longitude - zoom_region.minimum_longitude,
        zoom_region.maximum_latitude - zoom_region.minimum_latitude,
        linewidth=0.8,
        edgecolor=theme["insetcolor"],
        facecolor="none",
        transform=proj,
        zorder=4,
    )
    ax_main.add_patch(rect)

    fig.canvas.draw()

    connector_pairs = _best_connector_pairs(fig, ax_main, ax_inset, zoom_region)

    for (longitude, latitute), (xB, yB) in connector_pairs:
        connection = ConnectionPatch(
            xyA=(longitude, latitute),
            coordsA="data",
            xyB=(xB, yB),
            coordsB="axes fraction",
            axesA=ax_main,
            axesB=ax_inset,
            color=theme["insetcolor"],
            lw=0.8,
            alpha=0.9,
            zorder=2,
        )
        fig.add_artist(connection)

    plt.savefig(
        out_path,
        bbox_inches="tight",
        pad_inches=0,
        dpi=dpi,
        facecolor=fig.get_facecolor(),
        edgecolor="none",
    )
    if show:
        plt.show()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Render a locator map with an inset zoom window.")
    p.add_argument(
        "--summary-points",
        default=None,
        help="CSV file of points (latitute,longitude per line). If provided, renders a summary map (no inset).",
    )
    p.add_argument(
        "--min-distance-m",
        type=float,
        default=0.0,
        help="Minimum distance (meters) to merge nearby points in summary mode.",
    )
    p.add_argument(
        "--world-region",
        nargs=4,
        metavar=("LON_MIN", "LON_MAX", "LAT_MIN", "LAT_MAX"),
        default=DEFAULT_WORLD_REGION.as_extent(),
        help="Main map extent as lon_min lon_max lat_min lat_max.",
    )
    p.add_argument(
        "--zoom-region",
        nargs=4,
        metavar=("LON_MIN", "LON_MAX", "LAT_MIN", "LAT_MAX"),
        default=DEFAULT_ZOOM_REGION.as_extent(),
        help="Inset extent as lon_min lon_max lat_min lat_max.",
    )
    p.add_argument(
        "--star",
        nargs=2,
        metavar=("latitute", "longitude"),
        default=list(DEFAULT_STAR),
        help="Star (photo) location as latitude longitude.",
    )
    p.add_argument("--theme", dest="theme_file", default=None, help="Path to a theme JSON file.")
    p.add_argument("--title-main", default="Limerick, Ireland", help="Label shown on the main map.")
    p.add_argument("--title-inset", default="The University of Limerick", help="Title shown inside inset.")
    p.add_argument(
        "--caption",
        default=None,
        help="Optional caption text shown in the inset (e.g., photo caption / location string).",
    )
    p.add_argument(
        "--clock-svg",
        default=None,
        help="Optional clock SVG path to render in the inset (requires cairosvg + pillow).",
    )
    p.add_argument(
        "--inset-placement",
        choices=("smart", "corner-snap"),
        default="smart",
        help="Inset placement mode: 'smart' (default) or 'corner-snap'.",
    )
    p.add_argument("--clock-size", type=int, default=64, help="Clock badge size in pixels.")
    p.add_argument("--out", default="locator_map_styled.png", help="Output image path.")
    p.add_argument("--dpi", type=int, default=300, help="Output DPI.")
    p.add_argument("--fig-width", type=float, default=8.0, help="Figure width in inches.")
    p.add_argument("--no-show", action="store_true", help="Do not open a preview window.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    theme = load_theme(args.theme_file)

    # summary comprises a single zoomed-out map containing all points
    if args.summary_points:
        points = _read_points_csv(args.summary_points)

        default_world = DEFAULT_WORLD_REGION.as_extent()
        override_world = args.world_region
        summary_world_region: Region | None = None
        if list(override_world) != list(default_world):
            summary_world_region = parse_region([str(x) for x in override_world])

        render_summary_map(
            points_lat_lon=points,
            min_distance_m=float(args.min_distance_m),
            caption=args.caption,
            world_region=summary_world_region,
            theme=theme,
            out_path=args.out,
            dpi=args.dpi,
            fig_width_in=args.fig_width,
            show=not args.no_show,
        )
        return 0

    world_region = parse_region([str(x) for x in args.world_region])
    zoom_region = parse_region([str(x) for x in args.zoom_region])
    star = parse_coordinates([str(x) for x in args.star])

    render_map(
        world_region=world_region,
        zoom_region=zoom_region,
        star_lat_lon=star,
        title_main=args.title_main,
        title_inset=args.title_inset,
        caption=args.caption,
        clock_svg=args.clock_svg,
        theme=theme,
        out_path=args.out,
        dpi=args.dpi,
        fig_width_in=args.fig_width,
        show=not args.no_show,
        clock_size_px=args.clock_size,
        inset_placement_mode=args.inset_placement,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
