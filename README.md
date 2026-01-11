![locator_map_styled.png](locator_map_styled.png)

## snapshot.py

Renders a locator map with a zoom inset.

### Summary (collection/country)

Render a single zoomed-out map with a star for each point in a CSV (one `lat,lon` per line). Nearby points can be merged by a minimum distance in meters.

```bash
python snapshot.py \
	--summary-points points.csv \
	--min-distance-m 100 \
	--theme themes/default_dark.json \
	--caption "120 Photos. Friday, January 3, 2020 – Sunday, June 9, 2024" \
	--out summary.png
```

### Basic

```bash
python snapshot.py \
	--world-region -11 -5 50.5 56.5 \
	--zoom-region -8.742559512271514 -8.510014263814636 52.614007667018164 52.71198728589052 \
	--star 52.6698042403715 -8.577276842533156 \
	--theme themes/default_dark.json \
	--title-main "Limerick, Ireland" \
	--title-inset "The University of Limerick" \
	--out locator_map_styled.png
```

## driver.jl (Julia -> Python)

`driver.jl` scans a photo directory, extracts EXIF GPS/date/captions, optionally generates a clock SVG, then calls `snapshot.py` per photo with the right `--world-region/--zoom-region/--star/--theme/--caption/--clock-svg` arguments.

It also generates summary images into `_locator_summaries` by default:

- `collection-summary.png` (all photos with GPS)
- `country-<Country>.png` for each discovered country (and `country-UNKNOWN.png` when applicable)

Example:

```bash
julia driver.jl --dir "C:\\path\\to\\photos" --theme-file themes/default_dark.json --non-interactive
```

### Summary map knobs

- Disable summaries: `--no-summary`
- Merge threshold in meters: `--summary-min-distance 100`
- Output directory: `--summary-dir "C:\\path\\to\\photos\\_locator_summaries"`

If Python isn’t on PATH or you want to be explicit:

```bash
julia driver.jl \
	--dir "C:\\path\\to\\photos" \
	--python python \
	--snapshot-script snapshot.py \
	--map-dir "C:\\path\\to\\photos\\_locator_maps" \
	--overwrite-maps \
	--theme-file themes/default_dark.json \
	--non-interactive
```

### Add caption + clock SVG

Clock rendering requires extra deps:

```bash
pip install cairosvg pillow
```

Then:

```bash
python snapshot.py \
	--world-region -11 -5 50.5 56.5 \
	--zoom-region -8.742559512271514 -8.510014263814636 52.614007667018164 52.71198728589052 \
	--star 52.6698042403715 -8.577276842533156 \
	--theme themes/default_dark.json \
	--caption "Campus, Aug 2024" \
	--clock-svg path/to/clock.svg \
	--clock-size 64 \
	--out locator_map_styled.png
```
