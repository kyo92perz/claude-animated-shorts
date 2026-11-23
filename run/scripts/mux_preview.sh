#!/usr/bin/env bash
# Monta a prévia final: concatena os clipes silenciosos (5 frames cada, 0,167 s) e coloca por cima o trecho
# correspondente da trilha pt-BR (mix.wav, 67,5 s), com fades curtos para não estalar.
set -e
C=${FFMPEG:-/tmp/ffmpeg}
cd "$(dirname "$0")/.."
OUT=out/preview
: > $OUT/list.txt
ARGS=(); N=0
for spec in 01_hook:0.20 02_cidade:4.60 04_balanco:14.80 06_assobio:21.80 09_queda:32.00 11_dourado:43.60 12_parque:46.30 14_regra:57.95; do
  id=${spec%%:*}; t=${spec##*:}
  f=$OUT/$id.mp4
  [ -f "$f" ] || { echo "faltando $f"; exit 1; }
  echo "file '$id.mp4'" >> $OUT/list.txt
  $C -y -loglevel error -ss "$t" -t 0.17 -i audio/mix.wav -ar 48000 -ac 2 \
     -af "afade=t=in:st=0:d=0.02,afade=t=out:st=0.14:d=0.03" $OUT/${id}_a.wav
  ARGS+=(-i $OUT/${id}_a.wav); N=$((N+1))
done
$C -y -loglevel error -f concat -safe 0 -i $OUT/list.txt -c copy $OUT/video_silent.mp4
$C -y -loglevel error "${ARGS[@]}" \
  -filter_complex "[0:a][1:a][2:a][3:a][4:a][5:a][6:a][7:a]concat=n=8:v=0:a=1[a]" -map "[a]" \
  -ar 48000 -ac 2 $OUT/audio_reel.wav
$C -y -loglevel error -i $OUT/video_silent.mp4 -i $OUT/audio_reel.wav -map 0:v:0 -map 1:a:0 \
  -c:v copy -c:a aac -b:a 320k -shortest out/preview_final.mp4
$C -hide_banner -i out/preview_final.mp4 2>&1 | grep -E "Duration|Stream"
