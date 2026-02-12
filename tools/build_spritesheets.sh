#!/bin/bash
# build_spritesheets.sh
# Combines individual SVG specialization icons into spritesheets for GUI frame selection.
#
# Pipeline: SVG -> PNG (Inkscape) -> montage grid/strip -> optionally DDS (NVIDIA nvcompress)
#
# Frame layout (16 cells: 15 icons + 1 empty):
#   Frames 1-5:   regular      mining(red), farming(green), gathering(blue), woodland(brown), commercial(purple)
#   Frames 6-10:  prov_cap     mining(red), farming(green), gathering(blue), woodland(brown), commercial(purple)
#   Frames 11-15: capital      mining(red), farming(green), gathering(blue), woodland(brown), commercial(purple)
#   Frame 16:     (empty)
#
# GUI formula: frame = capital_offset + sul_spec_type
#   regular = 0, provincial_capital = 5, capital = 10
#   mining=1(red), farming=2(green), gathering=3(blue), woodland=4(brown), commercial=5(purple)
#
# Requirements: inkscape, ImageMagick (montage, convert), NVIDIA Texture Tools (nvcompress.exe) for DDS

set -euo pipefail

# === DEFAULTS ===
CELL_RURAL=64
CELL_TOWN=80
CELL_CITY=96
FORMAT="png"       # png or dds
LAYOUT="grid"      # grid (4x4) or strip (16x1)

# === CLI ARGS ===
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --rural SIZE    Cell size for rural (default: $CELL_RURAL)"
    echo "  --town SIZE     Cell size for town (default: $CELL_TOWN)"
    echo "  --city SIZE     Cell size for city (default: $CELL_CITY)"
    echo "  --scale N       Multiply all sizes by N (e.g. --scale 2 doubles)"
    echo "  --format FMT    Output format: png or dds (default: $FORMAT)"
    echo "  --layout LAY    Layout: grid (4x4) or strip (16x1) (default: $LAYOUT)"
    echo "  -h, --help      Show this help"
    exit 0
}

SCALE=1
while [[ $# -gt 0 ]]; do
    case "$1" in
        --rural)  CELL_RURAL="$2"; shift 2 ;;
        --town)   CELL_TOWN="$2"; shift 2 ;;
        --city)   CELL_CITY="$2"; shift 2 ;;
        --scale)  SCALE="$2"; shift 2 ;;
        --format) FORMAT="$2"; shift 2 ;;
        --layout) LAYOUT="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

CELL_RURAL=$((CELL_RURAL * SCALE))
CELL_TOWN=$((CELL_TOWN * SCALE))
CELL_CITY=$((CELL_CITY * SCALE))

if [[ "$LAYOUT" == "grid" ]]; then
    TILE="4x4"
elif [[ "$LAYOUT" == "strip" ]]; then
    TILE="16x1"
else
    echo "ERROR: --layout must be 'grid' or 'strip'"
    exit 1
fi

if [[ "$FORMAT" != "png" && "$FORMAT" != "dds" ]]; then
    echo "ERROR: --format must be 'png' or 'dds'"
    exit 1
fi

# === CONFIGURATION ===
ICON_SRC="/mnt/c/Users/Mjaklitsch/OneDrive/Desktop/inkscape_icons/svg"
MOD_DIR="/mnt/c/Users/Mjaklitsch/Documents/Paradox Interactive/Europa Universalis V/mod/Specialized Urban Locations Development"
OUTPUT_DIR="$MOD_DIR/main_menu/gfx/interface/mapitems"
NVCOMPRESS="/mnt/c/Program Files/NVIDIA Corporation/NVIDIA Texture Tools/nvcompress.exe"

# Colors in spec_type order: mining=1, farming=2, gathering=3, woodland=4, commercial=5
COLORS=(red green blue brown purple)

# Capital types in frame-offset order: regular=0, provincial_capital=5, capital=10
CAPITAL_PREFIXES=("" "provincial_capital_" "capital_")

# Rank -> cell size (px)
declare -A RANK_SIZE
RANK_SIZE[rural]=$CELL_RURAL
RANK_SIZE[town]=$CELL_TOWN
RANK_SIZE[city]=$CELL_CITY

# === BUILD ===
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "Building spritesheets..."
echo "  Source:  $ICON_SRC"
echo "  Output:  $OUTPUT_DIR"
echo "  Format:  $FORMAT | Layout: $LAYOUT ($TILE)"
echo "  Sizes:   rural=${CELL_RURAL}px  town=${CELL_TOWN}px  city=${CELL_CITY}px"
echo ""

for rank in "${!RANK_SIZE[@]}"; do
    cell_size="${RANK_SIZE[$rank]}"
    out_name="sul_${rank}_spritesheet"

    if [[ "$LAYOUT" == "grid" ]]; then
        sheet_w=$((cell_size * 4))
        sheet_h=$((cell_size * 4))
    else
        sheet_w=$((cell_size * 16))
        sheet_h=$cell_size
    fi

    echo "--- $out_name (${cell_size}px cells, ${sheet_w}x${sheet_h}, $LAYOUT) ---"

    # Rasterize SVGs to PNG at target size
    FILE_LIST=()
    for cap_prefix in "${CAPITAL_PREFIXES[@]}"; do
        for color in "${COLORS[@]}"; do
            svg_name="${color}_${cap_prefix}${rank}.svg"
            svg_path="$ICON_SRC/$svg_name"

            if [[ ! -f "$svg_path" ]]; then
                echo "  ERROR: Missing $svg_path"
                exit 1
            fi

            png_path="$TMPDIR/${out_name}_${cap_prefix}${color}.png"
            inkscape "$svg_path" \
                --export-type=png \
                --export-filename="$png_path" \
                -w "$cell_size" -h "$cell_size" \
                2>/dev/null
            FILE_LIST+=("$png_path")
        done
    done

    # Create transparent placeholder for cell 16 (empty)
    empty_png="$TMPDIR/${out_name}_empty.png"
    convert -size "${cell_size}x${cell_size}" xc:transparent "$empty_png"
    FILE_LIST+=("$empty_png")

    echo "  Rasterized: $((${#FILE_LIST[@]} - 1)) icons + 1 empty at ${cell_size}x${cell_size}"

    # Stitch into grid/strip
    grid_png="$OUTPUT_DIR/${out_name}.png"
    montage "${FILE_LIST[@]}" -tile "$TILE" -geometry +0+0 -background none "$grid_png"

    dims=$(identify -format "%wx%h" "$grid_png")
    echo "  PNG: $grid_png ($dims)"

    if [[ "$FORMAT" == "dds" ]]; then
        out_dds="$OUTPUT_DIR/${out_name}.dds"
        win_png=$(wslpath -w "$grid_png")
        win_dds=$(wslpath -w "$out_dds")
        "$NVCOMPRESS" -bc7 -highest -alpha -mipfilter kaiser "$win_png" "$win_dds"
        echo "  DDS: $out_dds"
    fi

    echo ""
done

echo "Done. 3 spritesheets created ($FORMAT, $LAYOUT)."
echo ""
echo "Frame reference (16 cells):"
echo "  1=mining(red) 2=farming(green) 3=gathering(blue) 4=woodland(brown) 5=commercial(purple)"
echo "  +0=regular  +5=provincial_capital  +10=capital"
echo "  Frame 16 = empty"
