from __future__ import annotations

import argparse
import io
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
        lon0, lon1 = sorted((self.minimum_longitude, self.maximum_longitude))
        lat0, lat1 = sorted((self.minimum_latitude, self.maximum_latitude))
        return Region(lon0, lon1, lat0, lat1)

    def as_extent(self) -> list[float]:
        return [self.minimum_longitude, self.maximum_longitude, self.minimum_latitude, self.maximum_latitude]


DEFAULT_WORLD_REGION = Region(-11.0, -5.0, 50.5, 56.5)
DEFAULT_ZOOM_REGION = Region(
    -8.742559512271514,
    -8.510014263814636,
    52.614007667018164,
    52.71198728589052,
)
DEFAULT_STAR = (52.6698042403715, -8.577276842533156)  # (lat, lon)


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


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
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
        return [(lat, lon, 1) for (lat, lon) in points]

    clusters: list[tuple[float, float, int]] = []
    for lat, lon in points:
        assigned = False
        for idx, (clat, clon, count) in enumerate(clusters):
            if haversine_m(lat, lon, clat, clon) <= min_distance_m:
                # update centroid as running mean
                new_count = count + 1
                new_lat = (clat * count + lat) / new_count
                new_lon = (clon * count + lon) / new_count
                clusters[idx] = (new_lat, new_lon, new_count)
                assigned = True
                break
        if not assigned:
            clusters.append((lat, lon, 1))
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
            raise ValueError(f"Invalid points line (expected 'lat,lon'): {raw!r}")
        points.append((float(parts[0]), float(parts[1])))
    return points


def _auto_region_from_points(points: list[tuple[float, float]]) -> Region:
    if not points:
        return DEFAULT_WORLD_REGION.normalized()

    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    lat0, lat1 = min(lats), max(lats)
    lon0, lon1 = min(lons), max(lons)

    # If points span most of the globe, fall back to a global-ish region.
    if (lon1 - lon0) > 180:
        return Region(-180.0, 180.0, max(-80.0, lat0 - 5.0), min(80.0, lat1 + 5.0)).normalized()

    lat_span = max(0.01, lat1 - lat0)
    lon_span = max(0.01, lon1 - lon0)
    lat_pad = max(0.5, lat_span * 0.35)
    lon_pad = max(0.5, lon_span * 0.35)
    return Region(lon0 - lon_pad, lon1 + lon_pad, lat0 - lat_pad, lat1 + lat_pad).normalized()


def render_summary_map(
    *,
    points_lat_lon: list[tuple[float, float]],
    min_distance_m: float,
    caption: str | None,
    theme: dict[str, Any],
    out_path: str,
    dpi: int,
    fig_width_in: float,
    show: bool,
) -> None:
    proj = ccrs.PlateCarree()

    world_region = _auto_region_from_points(points_lat_lon)
    aspect_main = geographic_aspect(world_region)
    fig_h = fig_width_in * aspect_main
    fig = plt.figure(figsize=(fig_width_in, fig_h), dpi=dpi)

    ax = fig.add_axes([0, 0, 1, 1], projection=proj)
    ax.set_extent(world_region.as_extent())
    ax.add_feature(cfeature.LAND, facecolor=theme["landcolor"])
    ax.add_feature(cfeature.OCEAN, facecolor=theme["oceancolor"])
    ax.add_feature(cfeature.BORDERS, linewidth=0.5, edgecolor=theme["bordercolor"])
    ax.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor=theme["bordercolor"])
    ax.set_aspect("equal", adjustable="box")

    clusters = cluster_points(points_lat_lon, min_distance_m=min_distance_m)
    for lat, lon, count in clusters:
        # Slightly scale star size for clusters, but keep it subtle.
        ms = 7.0 + min(6.0, 1.5 * math.log10(max(1, count)))
        ax.plot(lon, lat, marker="*", color=theme["starcolor"], markersize=ms, transform=proj, zorder=6)

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

    plt.savefig(out_path, bbox_inches="tight", dpi=dpi)
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


def parse_lat_lon(values: list[str]) -> tuple[float, float]:
    latitude, longitude = _float_list(values, 2, "lat/lon")
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
    offset = OffsetImage(image, zoom=1.0)
    ab = AnnotationBbox(
        offset,
        xy_axes,
        xycoords=ax.transAxes,
        frameon=False,
        box_alignment=(0, 0),
        zorder=10,
    )
    ax.add_artist(ab)


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
) -> None:
    proj = ccrs.PlateCarree()

    world_region = world_region.normalized()
    zoom_region = zoom_region.normalized()
    star_lat, star_lon = star_lat_lon

    inset_size = float(theme.get("inset_size", DEFAULT_THEME["inset_size"]))
    inset_margin = float(theme.get("inset_margin", DEFAULT_THEME["inset_margin"]))

    aspect_main = geographic_aspect(world_region)
    fig_h = fig_width_in * aspect_main
    fig = plt.figure(figsize=(fig_width_in, fig_h), dpi=dpi)

    ax_main = fig.add_axes([0, 0, 1, 1], projection=proj)
    ax_main.set_extent(world_region.as_extent())
    ax_main.add_feature(cfeature.LAND, facecolor=theme["landcolor"])
    ax_main.add_feature(cfeature.OCEAN, facecolor=theme["oceancolor"])
    ax_main.add_feature(cfeature.BORDERS, linewidth=0.5, edgecolor=theme["bordercolor"])
    ax_main.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor=theme["bordercolor"])
    ax_main.set_aspect("equal", adjustable="box")

    # inset placement: try to avoid covering the star
    x_fig, y_fig = ax_main.transData.transform((star_lon, star_lat))
    x_fig, y_fig = fig.transFigure.inverted().transform((x_fig, y_fig))

    x0 = min(max(x_fig + inset_margin, inset_margin), 1 - inset_size - inset_margin)
    y0 = min(max(y_fig + inset_margin, inset_margin), 1 - inset_size - inset_margin)

    ax_inset = fig.add_axes([x0, y0, inset_size, inset_size], projection=proj, zorder=5)
    ax_inset.set_extent(zoom_region.as_extent())
    ax_inset.add_feature(cfeature.LAND, facecolor=theme["landcolor"])
    ax_inset.add_feature(cfeature.BORDERS, linewidth=0.25, edgecolor=theme.get("bordercolor", "black"))
    ax_inset.add_feature(cfeature.COASTLINE, linewidth=0.25, edgecolor=theme.get("bordercolor", "black"))
    ax_inset.add_feature(cfeature.RIVERS, linewidth=0.5, facecolor=theme["watercolor"])
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
        _add_svg_badge(ax_inset, clock_svg, clock_size_px, (0.02, 0.02))

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

    def data_to_fig(ax, x, y):
        x_disp, y_disp = ax.transData.transform((x, y))
        return fig.transFigure.inverted().transform((x_disp, y_disp))

    rx0, ry0 = data_to_fig(ax_main, zoom_region.minimum_longitude, zoom_region.minimum_latitude)
    rx1, ry1 = data_to_fig(ax_main, zoom_region.maximum_longitude, zoom_region.maximum_latitude)
    rect_xmin, rect_xmax = min(rx0, rx1), max(rx0, rx1)
    rect_ymin, rect_ymax = min(ry0, ry1), max(ry0, ry1)

    inset_bbox = ax_inset.get_position()
    eps = 0.005

    if inset_bbox.y0 >= rect_ymax + eps:
        pos = "below"
    elif inset_bbox.y1 <= rect_ymin - eps:
        pos = "above"
    elif inset_bbox.x1 <= rect_xmin - eps:
        pos = "right"
    elif inset_bbox.x0 >= rect_xmax + eps:
        pos = "left"
    else:
        pos = "above"

    if pos == "below":
        xy = (zoom_region.minimum_longitude, zoom_region.minimum_latitude)
        ha, va = "left", "top"
        offset = (5, -5)
    elif pos == "above":
        xy = (zoom_region.minimum_longitude, zoom_region.maximum_latitude)
        ha, va = "left", "bottom"
        offset = (5, 5)
    elif pos == "left":
        xy = (zoom_region.minimum_longitude, (zoom_region.minimum_latitude + zoom_region.maximum_latitude) / 2)
        ha, va = "right", "center"
        offset = (-5, 0)
    else:
        xy = (zoom_region.maximum_longitude, (zoom_region.minimum_latitude + zoom_region.maximum_latitude) / 2)
        ha, va = "left", "center"
        offset = (5, 0)

    ax_main.annotate(
        title_main,
        xy=xy,
        xycoords=ccrs.PlateCarree(),
        xytext=offset,
        textcoords="offset points",
        ha=ha,
        va=va,
        fontsize=float(theme.get("title_fontsize", DEFAULT_THEME["title_fontsize"])) ,
        fontfamily=str(theme.get("fontfamily", DEFAULT_THEME["fontfamily"])) ,
        color=str(theme.get("textcolor", DEFAULT_THEME["textcolor"])) ,
        zorder=6,
    )

    for spine in ax_inset.spines.values():
        spine.set_edgecolor(theme["insetcolor"])
        spine.set_linewidth(1.0)
        spine.set_zorder(5)

    ax_inset.set_aspect("equal", adjustable="box")

    corners_main = [
        (zoom_region.minimum_longitude, zoom_region.minimum_latitude),
        (zoom_region.maximum_longitude, zoom_region.minimum_latitude),
        (zoom_region.minimum_longitude, zoom_region.maximum_latitude),
        (zoom_region.maximum_longitude, zoom_region.maximum_latitude),
    ]
    corners_inset = [(0, 0), (1, 0), (0, 1), (1, 1)]

    for (lon, lat), (xB, yB) in zip(corners_main, corners_inset):
        x_disp, y_disp = ax_main.projection.transform_point(lon, lat, ccrs.PlateCarree())
        conn = ConnectionPatch(
            xyA=(x_disp, y_disp),
            coordsA=ax_main.transData,
            xyB=(xB, yB),
            coordsB="axes fraction",
            axesA=ax_main,
            axesB=ax_inset,
            color=theme["insetcolor"],
            lw=0.8,
            alpha=0.9,
            zorder=2,
        )
        fig.add_artist(conn)

    plt.savefig(out_path, bbox_inches="tight", dpi=dpi)
    if show:
        plt.show()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Render a locator map with an inset zoom window.")
    p.add_argument(
        "--summary-points",
        default=None,
        help="CSV file of points (lat,lon per line). If provided, renders a summary map (no inset).",
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
        metavar=("LAT", "LON"),
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
    p.add_argument("--clock-size", type=int, default=64, help="Clock badge size in pixels.")
    p.add_argument("--out", default="locator_map_styled.png", help="Output image path.")
    p.add_argument("--dpi", type=int, default=300, help="Output DPI.")
    p.add_argument("--fig-width", type=float, default=8.0, help="Figure width in inches.")
    p.add_argument("--no-show", action="store_true", help="Do not open a preview window.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    theme = load_theme(args.theme_file)

    # Summary mode: a single zoomed-out map containing all points.
    if args.summary_points:
        points = _read_points_csv(args.summary_points)
        render_summary_map(
            points_lat_lon=points,
            min_distance_m=float(args.min_distance_m),
            caption=args.caption,
            theme=theme,
            out_path=args.out,
            dpi=args.dpi,
            fig_width_in=args.fig_width,
            show=not args.no_show,
        )
        return 0

    world_region = parse_region([str(x) for x in args.world_region])
    zoom_region = parse_region([str(x) for x in args.zoom_region])
    star = parse_lat_lon([str(x) for x in args.star])

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
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
