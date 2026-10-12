#!/bin/bash
# run_all.sh MODE(layer|nolayer): prototype over every baseline parse
W=$(dirname $(dirname $(readlink -f $0))); cd $W
mode=$1; out=reg_$mode; mkdir -p $out
flag=""; [ "$mode" = nolayer ] && flag="--no-layer"
for j in base/*/*.json; do k=$(basename $j .json); [ "$k" = "$(basename $(dirname $j))" ] || continue
  uv run --no-project -q tools/region.py $j pdf/$k.pdf $out/$k.json $flag || echo "FAIL $k"
done
uv run --no-project -q tools/compare.py base $out cmp_$mode.tsv
