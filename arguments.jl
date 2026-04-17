s = ArgParseSettings()

@add_arg_table! s begin
    "--dir", "-d"
        help = "the photograph directory to process"
        arg_type = String
        default = nothing
        required = true
    "--theme-file", "-t"
        help = "the theme file to use"
        arg_type = String
        default = joinpath(@__DIR__, "themes/default_dark.json")
    "--zoom-area", "-z"
        help = "the area in degrees^2 for zoomed-in maps (default: 0.125)"
        arg_type = Float64
        default = 0.125
    "--zoom-aspect", "-a"
        help = "the aspect ratio for zoomed-in maps (default: 16:9)"
        arg_type = String
        default = "16:9"
    "--non-interactive", "-n"
        help = "disable interactive caption selection when multiple candidates are found"
        arg_type = Bool
        default = false
    "--no-clocks", "-n"
        help = "disable generation of clock SVGs"
        arg_type = Bool
        default = false
    "--overwrite-clocks", "-o"
        help = "overwrite existing clock SVGs instead of skipping them"
        arg_type = Bool
        default = false
    "--clock-dir", "-c"
        help = "directory to write clock SVGs"
        arg_type = String
        default = joinpath(@__DIR__, "clocks")
    "--python", "-p"
        help = "the python command to use for map rendering"
        arg_type = String
        default = "python"
    "--map-dir", "-m"
        help = "directory to write locator maps"
        arg_type = String
        default = joinpath(@__DIR__, "maps")
    "--overwrite-maps", "-w"
        help = "overwrite existing locator maps instead of skipping them"
        arg_type = Bool
        default = false
    "--show-maps", "-s"
        help = "display locator maps after rendering (default: false)"
        arg_type = Bool
        default = false
    "--no-summary"
        help = "disable generation of summary maps for the collection and countries"
        arg_type = Bool
        default = false
    "--summary-min-distance"
        help = "the minimum distance in meters between points for summary maps"
        arg_type = Float64
        default = 100.0
    "--summary-dir"
        help = "directory to write summary maps"
        arg_type = String
        default = nothing
        required = joinpath(@__DIR__, "summaries")
end
