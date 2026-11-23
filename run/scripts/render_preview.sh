#!/usr/bin/env bash
# Renderiza 2 frames de cada ato e monta uma prévia com a trilha pt-BR (67,5 s).
set -e
export LD_LIBRARY_PATH=/tmp/nssext:/tmp/nssdist/lib
export BROWSER_EXECUTABLE=/tmp/chromium
mkdir -p out/preview
C=/tmp/ffmpeg
SEGS=()
for spec in 01_hook:20 02_cidade:190 04_balanco:500 06_assobio:760 09_queda:1040 11_dourado:1200 12_parque:1450 14_regra:1790; do
  id=${spec%%:*}; f0=${spec##*:}; f1=$((f0+2))
  echo "== clipe $id frames $f0-$f1"
  npx remotion render src/index.ts BridgeShort out/preview/${id}.mp4 \
    --frames=${f0}-${f1} --scale=0.5 --browser-executable=/tmp/chromium --gl=swangle \
    --concurrency=1 --log=error --codec=h264 --crf=20 --overwrite
  SEGS+=("file '${id}.mp4'")
done
printf '%s\n' "${SEGS[@]}" > out/preview/list.txt
$C -y -loglevel error -f concat -safe 0 -i out/preview/list.txt -c copy out/preview/video_silent.mp4
DUR=$($C -i out/preview/video_silent.mp4 2>&1 | grep -o "Duration: [0-9:.]*" | head -1)
echo "video: $DUR"
