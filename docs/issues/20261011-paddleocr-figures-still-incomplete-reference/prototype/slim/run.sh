#!/bin/bash
# run.sh VERSION SET BASE_DIR PDF_DIR PLUSL_DIR OUT_DIR: one second-opinion version over one set of parses, both modes,
# then option G's raw signals (../bigtest/detect.py). VERSION: frozen, slim (core 6), s7b, s7h (core 6 + one rule), slim8 (core 6 + both).
# eval_all.py BIG OUT_DIR then scores every version against the stage-4 grades (BIG = the stage-4 working directory).
v=$1; set_=$2; base=$3; pdfs=$4; plusl=$5; out=$6; here=$(dirname $(readlink -f $0))
for m in layer nolayer; do
  mkdir -p $out/${v}_${set_}_$m
  flag=""; [ $m = nolayer ] && flag=--no-layer
  for j in $base/*/*.json; do k=$(basename $j .json); [ "$k" = "$(basename $(dirname $j))" ] && [ -f $pdfs/$k.pdf ] || continue
    if [ $v = frozen ]; then  # ../region.py reads the plus-L boxes from ../../plusl
      uv run --no-project -q $here/../region.py $j $pdfs/$k.pdf $out/${v}_${set_}_$m/$k.json $flag || echo "FAIL $k"
    else
      uv run --no-project -q $here/region_$v.py $j $pdfs/$k.pdf $out/${v}_${set_}_$m/$k.json $plusl $flag || echo "FAIL $k"
    fi
  done
  uv run --no-project -q $here/../bigtest/detect.py $set_ $base $out/${v}_${set_}_$m $out/det_${v}_${set_}_$m.tsv
done
