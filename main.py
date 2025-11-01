import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib.patches import Rectangle, ConnectionPatch
import math

location = {"lat": 52.6698042403715, "lon": -8.577276842533156} 
zoom_region = [-8.742559512271514, -8.510014263814636, 52.614007667018164, 52.71198728589052]
world_region = [-11.0, -5.0, 50.5, 56.5]

fig = plt.figure(figsize=(8, 6), dpi=300)
proj = ccrs.PlateCarree()

oceancolor = "#000000"
#landcolor = "#183081"
landcolor = "#0F0F0F"
watercolor = "#29449b"
bordercolor = "#A4A4A4"
gold = "#C8A51C"
insetcolor = "#880000"

inset_size = 0.30
title_main = "Limerick, Ireland"
title_inset = "The University of Limerick"

def geographic_aspect(lon_min, lon_max, lat_min, lat_max):
    mean_lat = (lat_min + lat_max) / 2
    return (lat_max - lat_min) / ((lon_max - lon_min) * math.cos(math.radians(mean_lat)))

aspect_main = geographic_aspect(*world_region)

fig_w = 8
fig_h = fig_w * aspect_main
fig = plt.figure(figsize=(fig_w, fig_h), dpi=300)

proj = ccrs.PlateCarree()

ax_main = fig.add_axes([0, 0, 1, 1], projection=proj)
ax_main.set_extent(world_region)
ax_main.add_feature(cfeature.LAND, facecolor=landcolor)
ax_main.add_feature(cfeature.OCEAN, facecolor=oceancolor)
ax_main.add_feature(cfeature.BORDERS, linewidth=0.5, edgecolor=bordercolor)
ax_main.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor=bordercolor)
ax_main.set_aspect("equal", adjustable="box")

x_fig, y_fig = ax_main.transData.transform((location["lon"], location["lat"]))
x_fig, y_fig = fig.transFigure.inverted().transform((x_fig, y_fig))

x0 = min(max(x_fig + 0.02, 0.02), 1 - inset_size - 0.02)
y0 = min(max(y_fig + 0.02, 0.02), 1 - inset_size - 0.02)

ax_inset = fig.add_axes([x0, y0, inset_size, inset_size], projection=proj, zorder=5)
ax_inset.set_extent(zoom_region)
ax_inset.add_feature(cfeature.LAND, facecolor=landcolor)
ax_inset.add_feature(cfeature.BORDERS, linewidth=0.25)
ax_inset.add_feature(cfeature.COASTLINE, linewidth=0.25)
ax_inset.add_feature(cfeature.RIVERS, linewidth=0.5, facecolor=watercolor)
ax_inset.add_feature(cfeature.OCEAN, linewidth=0.5, facecolor=watercolor)
ax_inset.add_feature(cfeature.LAKES, linewidth=0.5, facecolor=watercolor)
ax_inset.plot(location["lon"], location["lat"], marker="*", color=gold,
              markersize=9, transform=proj, zorder=5)

ax_inset.text(
    0.02, 0.97, title_inset,
    transform=ax_inset.transAxes,
    ha="left", va="top",
    fontsize=6,
    fontfamily="serif",
    color="white",
    zorder=6,
)

rect = Rectangle(
    (zoom_region[0], zoom_region[2]),
    zoom_region[1] - zoom_region[0],
    zoom_region[3] - zoom_region[2],
    linewidth=0.8,
    edgecolor=insetcolor,
    facecolor="none",
    transform=proj,
    zorder=4,
)
ax_main.add_patch(rect)

def data_to_fig(ax, x, y):
    x_disp, y_disp = ax.transData.transform((x, y))
    return fig.transFigure.inverted().transform((x_disp, y_disp))

rx0, ry0 = data_to_fig(ax_main, zoom_region[0], zoom_region[2])
rx1, ry1 = data_to_fig(ax_main, zoom_region[1], zoom_region[3])
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
    xy = (zoom_region[0], zoom_region[2])
    ha, va = "left", "top"
    offset = (5, -5)
elif pos == "above":
    xy = (zoom_region[0], zoom_region[3])
    ha, va = "left", "bottom"
    offset = (5, 5)
elif pos == "left":
    xy = (zoom_region[0], (zoom_region[2] + zoom_region[3]) / 2)
    ha, va = "right", "center"
    offset = (-5, 0)
else:
    xy = (zoom_region[1], (zoom_region[2] + zoom_region[3]) / 2)
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
    fontsize=6,
    fontfamily="serif",
    color="white",
    zorder=6,
)

for spine in ax_inset.spines.values():
    spine.set_edgecolor(insetcolor)
    spine.set_linewidth(1.0)
    spine.set_zorder(5)

ax_inset.set_aspect("equal", adjustable="box")

corners_main = [
    (zoom_region[0], zoom_region[2]),
    (zoom_region[1], zoom_region[2]),
    (zoom_region[0], zoom_region[3]),
    (zoom_region[1], zoom_region[3]) 
]

corners_inset = [
    (0, 0),
    (1, 0),
    (0, 1),
    (1, 1)
]

for (lon, lat), (xB, yB) in zip(corners_main, corners_inset):
    x_disp, y_disp = ax_main.projection.transform_point(lon, lat, ccrs.PlateCarree())
    conn = ConnectionPatch(
        xyA=(x_disp, y_disp), coordsA=ax_main.transData,
        xyB=(xB, yB), coordsB="axes fraction",
        axesA=ax_main, axesB=ax_inset,
        color=insetcolor,
        lw=0.8,
        alpha=0.9,
        zorder=2  
    )
    fig.add_artist(conn)

#plt.savefig("locator_map_styled.svg", bbox_inches="tight")
plt.savefig("locator_map_styled.png", bbox_inches="tight", dpi=300)
plt.show()
