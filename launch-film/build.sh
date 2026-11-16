#!/usr/bin/env bash
# Render the full 80s film: 4 parallel segments, then mux with the music.
# Needs: node + playwright (with Chromium), ffmpeg.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out/seg
for i in 0 1 2 3; do
  node render.mjs segment $((i*600)) $((i*600+600)) out/seg/seg$i.mp4 > out/seg/log$i.txt 2>&1 &
done
wait
printf "file 'seg/seg0.mp4'\nfile 'seg/seg1.mp4'\nfile 'seg/seg2.mp4'\nfile 'seg/seg3.mp4'\n" > out/list.txt
ffmpeg -v error -y -f concat -safe 0 -i out/list.txt -i music/Neon_Genesis_Protocol.wav \
  -map 0:v -map 1:a -c:v copy -c:a aac -b:a 320k -shortest -movflags +faststart out/master.mp4
ffmpeg -v error -y -i out/master.mp4 -c:v libx264 -preset slow -crf 24 -pix_fmt yuv420p \
  -profile:v high -c:a aac -b:a 256k -movflags +faststart out/web.mp4
ls -la out/*.mp4
