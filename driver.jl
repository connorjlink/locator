# TODO: import photo directory logic

# Requirements:
# - exiftool (installed and in PATH externally)
# - package ReverseGeocode
# - package ArchGDAL


using ReverseGeocode, StaticArrays
gc = Geocoder()

using ArchGDAL, DataFrames
dataset = ArchGDAL.open("ne_10m_admin_0_countries.shp")
layer = ArchGDAL.getlayer(dataset, 0)

results = DataFrame(
    name = String[],
    iso_a3 = String[],
    min_lon = Float64[],
    min_lat = Float64[],
    max_lon = Float64[],
    max_lat = Float64[],
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

function get_directory()
    if length(ARGS) >= 1
        d = ARGS[1]
        if isdir(d)
            return abspath(d)
        else
            @warn "Argument is not a directory: $d"
        end
    end
    print("Enter photograph directory (or Enter to cancel): ")
    d = strip(readline())
    isempty(d) && error("Directory not specified.")
    if !isdir(d)
        error("Invalid directory: $d")
    end
    return abspath(d)
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
    min_latitude::Float64
    max_latitude::Float64
    min_longitude::Float64
    max_longitude::Float64
end

struct PhotoMetadata
    latitude::Union{Float64, Nothing}
    longitude::Union{Float64, Nothing}
    caption::Union{String, Nothing}
    country::Union{String, Nothing}
    rectangle::Union{PhotoRectangle, Nothing}
end

function parse_photo_metadata(path::AbstractString)
    command = `exiftool -n -GPSLatitude -GPSLongitude -ImageDescription -Caption-Abstract -UserComment -XPComment -Keywords $path`
    try
        out = read(command, String)
    catch e
        @warn "Could not run exiftool for $path: $(e)"
        return nothing
    end

    latitude = nothing
    longitude = nothing
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
        elseif key in ("imagedescription", "caption-abstract", "usercomment", "xpcomment", "keywords")
            push!(captions, value)
        end
    end

    caption = isempty(captions) ? nothing : join(captions, "; ")
    if latitude === nothing && longitude === nothing && caption === nothing
        @warn "No usable metadata found for $path"
            return nothing
        end
    return PhotoMetadata(latitude, longitude, caption, nothing, nothing)
end

function get_country_from_coordinates(latitude::Float64, longitude::Float64)
    decode(gc, SA[latitude, longitude]) do result
        if result === nothing
            return nothing
        else
            return result.country
        end
    end
end

# determine target directory and enumerate images therein or within child directories thereof
target_directory = try
    get_directory()
catch e
    @error e isa Exception ? e.msg : string(e)
    ""
end

if target_directory != ""
    image_paths = collect_image_files(target_directory)
    println("Found $(length(image_paths)) image files...")
    for p in image_paths
        println("Parsing $p...")

        metadata = parse_photo_metadata(p)
        if metadata !== nothing && metadata.latitude !== nothing && metadata.longitude !== nothing
            country = get_country_from_coordinates(metadata.latitude, metadata.longitude)
            rectangle = nothing
            if country !== nothing
                country_row = filter(row -> row.iso_a3 == country, results)
                if nrow(country_row) == 1
                    row = country_row[1, :]
                    rectangle = PhotoRectangle(
                        row.min_lat,
                        row.max_lat,
                        row.min_lon,
                        row.max_lon
                    )
                end
            end
            metadata = PhotoMetadata(metadata.latitude, metadata.longitude, metadata.caption, country, rectangle)
        end
        photo_index[p] = metadata
        if metadata === nothing
            @warn "Metadata missing or unparsable for $p"
        else
            latstr = metadata.latitude === nothing ? "NULL" : string(metadata.latitude)
            lonstr = metadata.longitude === nothing ? "NULL" : string(metadata.longitude)
            capstr = metadata.caption === nothing ? "NULL" : metadata.caption
            ctry = metadata.country === nothing ? "NULL" : metadata.country
            println("  -> latitude=$latstr longitude=$lonstr country=$(ctry) caption=$(capstr)")
        end
    end
end




# TODO: determine how to crop the zoom region? automatically center the POI +- some margin?
# TODO: determine how to crop the world region? maybe fixed according to country information?
    # could look up the country boundaries from cartopy per latitude/long and build a bounding box
    # could set custom regions per known locations in a config file? per-country basis?
        # e.g., set one for USA (continental), one for mainland UK, etc.

# TODO: allow for custom styling light/dark themes: maybe import theme from file? w/ swatches

# TODO: want a way, maybe to figure out location data smartly from latitude/long (lookup on-line?)

# TODO: want to plot a world map bounding box minimum around the custom bounding boxes of the countries referenced in the directory, finish the directory parse with a star plot of every photo location
    # final result is a locator map of all photo locations in the directory
