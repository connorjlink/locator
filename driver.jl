# Requirements:
# - exiftool (installed and in PATH externally)
# - package ReverseGeocode
# - package ArchGDAL


using ReverseGeocode, StaticArrays
gc = Geocoder()

using Dates

using ArchGDAL, DataFrames
dataset = ArchGDAL.open("ne_10m_admin_0_countries.shp")
layer = ArchGDAL.getlayer(dataset, 0)

results = DataFrame(
    name = String[],
    iso_a3 = String[],
    minimum_longitude = Float64[],
    minimum_latitude = Float64[],
    maximum_longitude = Float64[],
    maximum_latitude = Float64[],
)

for feature in layer
    geom = ArchGDAL.getgeom(feature)
    envelope = ArchGDAL.envelope(geom)

    push!(results, (
        ArchGDAL.getfield(feature, "NAME"),
        ArchGDAL.getfield(feature, "ISO_A3"),
        envelope.MinX,
        envelope.MinY,
        envelope.MaxX,
        envelope.MaxY
    ))
end

const IMAGE_EXTS = Set([".png", ".jpg", ".jpeg", ".heic", ".heif"])

struct CollectionMetadata
    directory::Union{String, Nothing}
    theme_file::Union{String, Nothing}
    zoom_area_deg2::Float64
    zoom_aspect_ratio::Float64  # width/height
    interactive_caption_selection::Bool
    photo_locations::Vector{Tuple{Float64, Float64}}
    generate_clock_svgs::Bool
    clock_output_dir::Union{String, Nothing}
    clock_size_px::Int
    clock_stroke_px::Float64
    overwrite_clock_svgs::Bool
end

function with_directory(collection::CollectionMetadata, directory::AbstractString)
    return CollectionMetadata(
        abspath(directory),
        collection.theme_file,
        collection.zoom_area_deg2,
        collection.zoom_aspect_ratio,
        collection.interactive_caption_selection,
        collection.photo_locations,
        collection.generate_clock_svgs,
        collection.clock_output_dir,
        collection.clock_size_px,
        collection.clock_stroke_px,
        collection.overwrite_clock_svgs,
    )
end

function with_photo_locations(collection::CollectionMetadata, locations::Vector{Tuple{Float64, Float64}})
    return CollectionMetadata(
        collection.directory,
        collection.theme_file,
        collection.zoom_area_deg2,
        collection.zoom_aspect_ratio,
        collection.interactive_caption_selection,
        locations,
        collection.generate_clock_svgs,
        collection.clock_output_dir,
        collection.clock_size_px,
        collection.clock_stroke_px,
        collection.overwrite_clock_svgs,
    )
end

function parse_aspect_ratio(value::AbstractString)
    s = strip(value)
    isempty(s) && return nothing
    if occursin(":", s)
        parts = split(s, ":")
        length(parts) == 2 || return nothing
        w = tryparse(Float64, strip(parts[1]))
        h = tryparse(Float64, strip(parts[2]))
        (w === nothing || h === nothing || h == 0) && return nothing
        return w / h
    end
    r = tryparse(Float64, s)
    (r === nothing || r <= 0) && return nothing
    return r
end

function parse_arguments(args::Vector{String})
    directory = nothing
    theme_file = nothing
    zoom_area_deg2 = 0.125
    zoom_aspect_ratio = 16 / 9
    interactive_caption_selection = true

    # defaults
    photo_locations = Tuple{Float64, Float64}[]
    generate_clock_svgs = true
    clock_output_dir = nothing
    clock_size_px = 64
    clock_stroke_px = 2.0
    overwrite_clock_svgs = false

    i = 1
    while i <= length(args)
        a = args[i]
        if a in ("--help", "-h")
            println("Usage: julia driver.jl [--dir PATH] [--theme-file PATH] [--zoom-area DEG2] [--zoom-aspect 16:9|1.777] [--non-interactive]\n")
            println("Defaults: --zoom-area 0.125, --zoom-aspect 16:9")
            exit(0)
        elseif a in ("--dir", "-d")
            i += 1
            i <= length(args) || error("Missing value for $a")
            directory = args[i]
        elseif a in ("--theme-file", "-t")
            i += 1
            i <= length(args) || error("Missing value for $a")
            theme_file = args[i]
        elseif a == "--zoom-area"
            i += 1
            i <= length(args) || error("Missing value for --zoom-area")
            v = tryparse(Float64, args[i])
            (v === nothing || v <= 0) && error("Invalid --zoom-area: $(args[i])")
            zoom_area_deg2 = v
        elseif a == "--zoom-aspect"
            i += 1
            i <= length(args) || error("Missing value for --zoom-aspect")
            r = parse_aspect_ratio(args[i])
            r === nothing && error("Invalid --zoom-aspect: $(args[i])")
            zoom_aspect_ratio = r
        elseif a == "--non-interactive"
            interactive_caption_selection = false
        elseif a == "--no-clocks"
            generate_clock_svgs = false
        elseif a == "--clock-dir"
            i += 1
            i <= length(args) || error("Missing value for --clock-dir")
            clock_output_dir = args[i]
        elseif a == "--clock-size"
            i += 1
            i <= length(args) || error("Missing value for --clock-size")
            v = tryparse(Int, args[i])
            (v === nothing || v <= 0) && error("Invalid --clock-size: $(args[i])")
            clock_size_px = v
        elseif a == "--clock-stroke"
            i += 1
            i <= length(args) || error("Missing value for --clock-stroke")
            v = tryparse(Float64, args[i])
            (v === nothing || v <= 0) && error("Invalid --clock-stroke: $(args[i])")
            clock_stroke_px = v
        elseif a == "--overwrite-clocks"
            overwrite_clock_svgs = true
        elseif startswith(a, "-")
            error("Unknown argument: $a")
        else
            # positional directory (first only)
            directory === nothing && (directory = a)
        end
        i += 1
    end

    return CollectionMetadata(
        directory === nothing ? nothing : abspath(directory),
        theme_file === nothing ? nothing : abspath(theme_file),
        zoom_area_deg2,
        zoom_aspect_ratio,
        interactive_caption_selection,
        photo_locations,
        generate_clock_svgs,
        clock_output_dir === nothing ? nothing : abspath(clock_output_dir),
        clock_size_px,
        clock_stroke_px,
        overwrite_clock_svgs,
    )
end

function canonical_latlon(latitude::Float64, longitude::Float64; digits::Int = 6)
    return (round(latitude; digits = digits), round(longitude; digits = digits))
end

function get_directory(collection::CollectionMetadata)
    if collection.directory !== nothing
        directory = collection.directory
        if isdir(directory)
            return abspath(directory)
        else
            @warn "Argument is not a directory: $directory"
        end
    end
    print("Enter photograph directory (or Enter to cancel): ")
    directory = strip(readline())
    isempty(directory) && error("Directory not specified.")
    if !isdir(directory)
        error("Invalid directory: $directory")
    end
    return abspath(directory)
end

function collect_image_files(dir::AbstractString)
    result = String[]
    for (root, _, names) in walkdir(dir)
        for name in names
            extension = lowercase(splitext(name)[2])
            if extension in IMAGE_EXTS
                push!(result, joinpath(root, name))
            end
        end
    end
    return result
end

struct PhotoRectangle
    minimum_latitude::Float64
    maximum_latitude::Float64
    minimum_longitude::Float64
    maximum_longitude::Float64
end

struct PhotoMetadata
    latitude::Union{Float64, Nothing}
    longitude::Union{Float64, Nothing}
    taken_at::Union{DateTime, Nothing}
    date_string::Union{String, Nothing}
    captions::Vector{String}
    selected_caption::Union{String, Nothing}
    city::Union{String, Nothing}
    country::Union{String, Nothing}
    location_string::Union{String, Nothing}
    rectangle::Union{PhotoRectangle, Nothing}
    zoom_rectangle::Union{PhotoRectangle, Nothing}
    clock_svg_path::Union{String, Nothing}
end

function normalize_captions(captions::Vector{String})
    cleaned = String[]
    seen = Set{String}()
    for c in captions
        s = strip(c)
        isempty(s) && continue
        key = lowercase(s)
        if !(key in seen)
            push!(cleaned, s)
            push!(seen, key)
        end
    end
    return cleaned
end

function choose_caption_for_location(path::AbstractString, captions::Vector{String}; interactive::Bool = true)
    captions = normalize_captions(captions)
    if isempty(captions)
        return nothing
    elseif length(captions) == 1
        return captions[1]
    end

    if !interactive
        return captions[1]
    end

    println("Multiple captions found for:\n  $path")
    labels = collect('A':'Z')
    for (i, c) in enumerate(captions)
        label = i <= length(labels) ? string(labels[i]) : string(i)
        println("  [$label] $c")
    end
    print("Select caption for location name (Enter for [A]): ")
    choice = strip(readline())
    isempty(choice) && return captions[1]

    # Accept A/B/C... or 1/2/3...
    if length(choice) == 1 && isletter(choice[1])
        idx = Int(uppercase(choice[1]) - 'A') + 1
        return (1 <= idx <= length(captions)) ? captions[idx] : captions[1]
    end
    idx = tryparse(Int, choice)
    return (idx !== nothing && 1 <= idx <= length(captions)) ? captions[idx] : captions[1]
end

function parse_exif_datetime(value::AbstractString)
    v = strip(value)
    isempty(v) && return nothing

    # Common EXIF patterns:
    # - 2020:07:24 13:04:55
    # - 2020-07-24 13:04:55
    # - 2020:07:24 13:04:55-05:00 (timezone suffix)
    v = replace(v, r"Z$" => "")
    v_no_tz = replace(v, r"[+-]\d\d:\d\d$" => "")

    for fmt in (dateformat"yyyy:mm:dd HH:MM:SS", dateformat"yyyy-mm-dd HH:MM:SS")
        dt = try
            DateTime(v_no_tz, fmt)
        catch
            nothing
        end
        dt !== nothing && return dt
    end
    return nothing
end

function format_taken_date(dt::DateTime)
    return "$(dayname(dt)), $(monthname(dt)) $(day(dt)), $(year(dt))"
end

function clamp_latitude(x::Float64)
    return max(-90.0, min(90.0, x))
end

function clamp_longitude(x::Float64)
    return max(-180.0, min(180.0, x))
end

function compute_zoom_rectangle(latitude::Float64, longitude::Float64, area_deg2::Float64, aspect_ratio::Float64)
    # area_deg2 = width_deg * height_deg, aspect_ratio = width/height
    width_deg = sqrt(area_deg2 * aspect_ratio)
    height_deg = sqrt(area_deg2 / aspect_ratio)
    half_w = width_deg / 2
    half_h = height_deg / 2
    return PhotoRectangle(
        clamp_latitude(latitude - half_h),
        clamp_latitude(latitude + half_h),
        clamp_longitude(longitude - half_w),
        clamp_longitude(longitude + half_w)
    )
end

function get_reverse_geocode(latitude::Float64, longitude::Float64)
    decode(gc, SA[latitude, longitude]) do result
        return result
    end
end

function maybe_getprop(obj, name::Symbol)
    try
        return getproperty(obj, name)
    catch
        return nothing
    end
end

function get_city_country_from_coordinates(latitude::Float64, longitude::Float64)
    result = get_reverse_geocode(latitude, longitude)
    result === nothing && return (nothing, nothing)

    # ReverseGeocode result fields vary by dataset; try common ones.
    city = something(
        maybe_getprop(result, :city),
        maybe_getprop(result, :name),
        maybe_getprop(result, :locality),
        maybe_getprop(result, :admin2),
        maybe_getprop(result, :admin1),
        nothing
    )
    country = something(
        maybe_getprop(result, :country),
        maybe_getprop(result, :country_name),
        nothing
    )
    return (city, country)
end

function sanitize_filename_component(s::AbstractString)
    # Windows-invalid: <>:"/\|?* plus control chars
    t = replace(s, r"[<>:\"/\\|?*\x00-\x1F]" => "_")
    t = replace(t, r"\s+" => " ")
    t = strip(t)
    isempty(t) ? "file" : t
end

function is_within_dir(child::AbstractString, parent::AbstractString)
    c = normpath(abspath(child))
    p = normpath(abspath(parent))
    sep = string(Base.Filesystem.path_separator)
    p_with_sep = endswith(p, sep) ? p : p * sep
    return c == p || startswith(c, p_with_sep)
end

function resolve_clock_output_dir(collection::CollectionMetadata)
    collection.generate_clock_svgs || return nothing
    collection.directory === nothing && return nothing

    base = collection.directory
    outdir = collection.clock_output_dir === nothing ? joinpath(base, "_clock_svgs") : collection.clock_output_dir

    is_within_dir(outdir, base) || error("Cannot write clocks outside photo directory. clock-dir=$outdir base=$base")
    mkpath(outdir)
    return outdir
end

function clock_svg_string(dt::DateTime; size_px::Int = 64, stroke_px::Float64 = 2.0)
    size = float(size_px)
    cx = size / 2
    cy = size / 2
    r = max(0.0, (size / 2) - stroke_px)  # ring radius

    # time fractions
    h = mod(hour(dt), 12)
    m = minute(dt)
    s = second(dt)

    hour_frac = (h + m / 60 + s / 3600) / 12
    min_frac = (m + s / 60) / 60

    function endpoint(frac::Float64, len::Float64)
        θ = 2π * frac - π/2  # 0 at 12 o'clock; increases clockwise in SVG coords
        x = cx + len * cos(θ)
        y = cy + len * sin(θ)
        return (x, y)
    end

    hour_len = r * 0.55
    min_len  = r * 0.82

    hx, hy = endpoint(hour_frac, hour_len)
    mx, my = endpoint(min_frac, min_len)

    # transparent fill, round caps, slightly thicker hour hand
    return """
<svg xmlns="http://www.w3.org/2000/svg" width="$(size_px)" height="$(size_px)" viewBox="0 0 $(size_px) $(size_px)">
  <circle cx="$(cx)" cy="$(cy)" r="$(r)" fill="none" stroke="black" stroke-width="$(stroke_px)"/>
  <line x1="$(cx)" y1="$(cy)" x2="$(hx)" y2="$(hy)" stroke="black" stroke-width="$(max(stroke_px, 2.0))" stroke-linecap="round"/>
  <line x1="$(cx)" y1="$(cy)" x2="$(mx)" y2="$(my)" stroke="black" stroke-width="$(max(1.0, stroke_px))" stroke-linecap="round"/>
  <circle cx="$(cx)" cy="$(cy)" r="$(max(1.0, stroke_px))" fill="black"/>
</svg>
"""
end

function maybe_generate_clock_svg(image_path::AbstractString, dt::Union{DateTime, Nothing}, collection::CollectionMetadata)
    dt === nothing && return nothing
    outdir = resolve_clock_output_dir(collection)
    outdir === nothing && return nothing

    base = sanitize_filename_component(splitext(basename(image_path))[1])
    hhmm = Dates.format(dt, "HHMM")
    digest = bytes2hex(sha1(image_path))[1:10]
    outpath = joinpath(outdir, "$(base)-$(hhmm)-$(digest).svg")

    if isfile(outpath) && !collection.overwrite_clock_svgs
        return outpath
    end

    svg = clock_svg_string(dt; size_px = collection.clock_size_px, stroke_px = collection.clock_stroke_px)
    open(outpath, "w") do io
        write(io, svg)
    end
    return outpath
end

function parse_photo_metadata(path::AbstractString, collection::CollectionMetadata)
    command = `exiftool -n -GPSLatitude -GPSLongitude -DateTimeOriginal -CreateDate -ModifyDate -ImageDescription -Caption-Abstract -UserComment -XPComment -Keywords $path`
    try
        out = read(command, String)
    catch e
        @warn "Could not run exiftool for $path: $(e)"
        return nothing
    end

    latitude = nothing
    longitude = nothing
    taken_at = nothing
    captions = String[]
    for line in split(out, '\n')
        m = match(r"^\s*([^:]+)\s*:\s*(.*)\s*$", line)
        m === nothing && continue
        key = lowercase(strip(m.captures[1]))
        value = strip(m.captures[2])
        if isempty(value)
            continue
        elseif key == "gps latitude"
            v = tryparse(Float64, value)
            v !== nothing && (latitude = v)
        elseif key == "gps longitude"
            v = tryparse(Float64, value)
            v !== nothing && (longitude = v)
        elseif key in ("datetimeoriginal", "create date", "modify date")
            if taken_at === nothing
                dt = parse_exif_datetime(value)
                dt !== nothing && (taken_at = dt)
            end
        elseif key in ("imagedescription", "caption-abstract", "usercomment", "xpcomment", "keywords")
            push!(captions, value)
        end
    end

    captions = normalize_captions(captions)

    if latitude === nothing && longitude === nothing && taken_at === nothing && isempty(captions)
        @warn "No usable metadata found for $path"
        return nothing
    end

    date_string = taken_at === nothing ? nothing : format_taken_date(taken_at)
    selected_caption = choose_caption_for_location(path, captions; interactive = collection.interactive_caption_selection)

    return PhotoMetadata(
        latitude,
        longitude,
        taken_at,
        date_string,
        captions,
        selected_caption,
        nothing,
        nothing,
        nothing,
        nothing,
        nothing,
        nothing,
    )
end

function build_location_string(selected_caption::Union{String, Nothing}, city::Union{String, Nothing}, country::Union{String, Nothing})
    parts = String[]
    selected_caption !== nothing && !isempty(strip(selected_caption)) && push!(parts, strip(selected_caption))
    city !== nothing && !isempty(strip(city)) && push!(parts, strip(city))
    country !== nothing && !isempty(strip(country)) && push!(parts, strip(country))
    isempty(parts) && return nothing
    return join(parts, ", ")
end

# determine target directory and enumerate images therein or within child directories thereof
collection_metadata = parse_arguments(ARGS)

target_directory = try
    get_directory(collection_metadata)
catch e
    @error e isa Exception ? e.msg : string(e)
    ""
end

if target_directory != ""
    collection_metadata = with_directory(collection_metadata, target_directory)

    seen_locations = Set{Tuple{Float64, Float64}}()

    photo_index = Dict{String, Union{PhotoMetadata, Nothing}}()
    image_paths = collect_image_files(target_directory)
    println("Found $(length(image_paths)) image files...")
    for p in image_paths
        println("Parsing $p...")

        metadata = parse_photo_metadata(p, collection_metadata)
        if metadata !== nothing && metadata.latitude !== nothing && metadata.longitude !== nothing
            push!(seen_locations, canonical_latlon(metadata.latitude, metadata.longitude))
            city, country = get_city_country_from_coordinates(metadata.latitude, metadata.longitude)
            rectangle = nothing
            zoom_rectangle = compute_zoom_rectangle(metadata.latitude, metadata.longitude, collection_metadata.zoom_area_deg2, collection_metadata.zoom_aspect_ratio)

            if country !== nothing
                country_lower = lowercase(strip(country))
                country_row = filter(row -> lowercase(strip(row.name)) == country_lower, results)
                if nrow(country_row) == 1
                    row = country_row[1, :]
                    rectangle = PhotoRectangle(
                        row.minimum_latitude,
                        row.maximum_latitude,
                        row.minimum_longitude,
                        row.maximum_longitude
                    )
                end
            end

            location_string = build_location_string(metadata.selected_caption, city, country)

            clock_svg_path = maybe_generate_clock_svg(p, metadata.taken_at, collection_metadata)

            metadata = PhotoMetadata(
                metadata.latitude,
                metadata.longitude,
                metadata.taken_at,
                metadata.date_string,
                metadata.captions,
                metadata.selected_caption,
                city,
                country,
                location_string,
                rectangle,
                zoom_rectangle,
                clock_svg_path,
            )
        elseif metadata !== nothing
            # still generate clock even if GPS missing, if taken_at exists
            clock_svg_path = maybe_generate_clock_svg(p, metadata.taken_at, collection_metadata)
            metadata = PhotoMetadata(
                metadata.latitude,
                metadata.longitude,
                metadata.taken_at,
                metadata.date_string,
                metadata.captions,
                metadata.selected_caption,
                metadata.city,
                metadata.country,
                metadata.location_string,
                metadata.rectangle,
                metadata.zoom_rectangle,
                clock_svg_path,
            )
        end

        photo_index[p] = metadata
        if metadata === nothing
            @warn "Metadata missing or unparsable for $p"
        else
            latstr = metadata.latitude === nothing ? "NULL" : string(metadata.latitude)
            lonstr = metadata.longitude === nothing ? "NULL" : string(metadata.longitude)
            datestr = metadata.date_string === nothing ? "NULL" : metadata.date_string
            locstr = metadata.location_string === nothing ? "NULL" : metadata.location_string
            ctry = metadata.country === nothing ? "NULL" : metadata.country
            clk = metadata.clock_svg_path === nothing ? "NULL" : metadata.clock_svg_path
            println("  -> latitude=$latstr longitude=$lonstr country=$(ctry) date=$(datestr) location=$(locstr) clock=$(clk)")
        end
    end

    # Save directory-wide, deduplicated (lat, lon) list into the collection metadata.
    collection_metadata = with_photo_locations(collection_metadata, sort!(collect(seen_locations)))
    println("\n==== Collection GPS Locations ====")
    println("Unique photo GPS points: $(length(collection_metadata.photo_locations))")
    for (lat, lon) in collection_metadata.photo_locations
        println("  - lat=$(lat) lon=$(lon)")
    end

    # final structured output grouped by country
    function rect_string(r::PhotoRectangle)
        return "min_lat=$(round(r.minimum_latitude, digits=6)) max_lat=$(round(r.maximum_latitude, digits=6)) min_lon=$(round(r.minimum_longitude, digits=6)) max_lon=$(round(r.maximum_longitude, digits=6))"
    end

    by_country = Dict{String, Vector{Tuple{String, PhotoMetadata}}}()
    unknown = Tuple{String, PhotoMetadata}[]
    for (path, md_any) in photo_index
        md_any === nothing && continue
        md = md_any
        if md.country === nothing
            push!(unknown, (path, md))
        else
            push!(get!(by_country, md.country, Tuple{String, PhotoMetadata}[]), (path, md))
        end
    end

    println("\n==== Country Map Summary ====")
    for country in sort(collect(keys(by_country)))
        entries = by_country[country]
        println("\nCountry: $country (photos: $(length(entries)))")
        # pick first available country rectangle among entries
        country_rect = nothing
        for (_, md) in entries
            if md.rectangle !== nothing
                country_rect = md.rectangle
                break
            end
        end
        if country_rect !== nothing
            println("  Country bounds: $(rect_string(country_rect))")
        else
            println("  Country bounds: NULL")
        end

        for (path, md) in sort(entries; by = x -> x[1])
            zoom_str = md.zoom_rectangle === nothing ? "NULL" : rect_string(md.zoom_rectangle)
            datestr = md.date_string === nothing ? "NULL" : md.date_string
            locstr = md.location_string === nothing ? "NULL" : md.location_string
            println("  - $(basename(path)) | date=$datestr | location=$locstr")
            println("    zoom bounds: $zoom_str")
        end
    end
    if !isempty(unknown)
        println("\nCountry: UNKNOWN (photos: $(length(unknown)))")
        for (path, md) in sort(unknown; by = x -> x[1])
            zoom_str = md.zoom_rectangle === nothing ? "NULL" : rect_string(md.zoom_rectangle)
            datestr = md.date_string === nothing ? "NULL" : md.date_string
            locstr = md.location_string === nothing ? "NULL" : md.location_string
            println("  - $(basename(path)) | date=$datestr | location=$locstr")
            println("    zoom bounds: $zoom_str")
        end
    end
end

# TODO: send each image task over to python script with corresponding parameters for rendering
# TODO: send final collection metadata to python script for metadata rendering
