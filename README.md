# Delivery Shelf launch film (source archive)

This branch archives the source for the urban launch video. It holds no plugin code and is not meant to be merged.
The published web cut lives on the plugin branch as `docs/assets/launch-urban.mp4`.

Everything is in [`launch-film/`](launch-film/).

| Path | What it is |
| --- | --- |
| `output/delivery-shelf-launch-hq.mp4` | High-quality render (1080p30, ~9 Mbps, AAC 320k, 80s) |
| `film.js` | The whole film: scenes, effects and timing. `renderFrame(i)` draws frame `i` deterministically |
| `index.html` | Page that loads the bundled fonts and `film.js` |
| `render.mjs` | Playwright driver: renders stills for review, or frame ranges piped to ffmpeg |
| `build.sh` | Full render: 4 parallel segments, concat, mux music, write `out/master.mp4` and `out/web.mp4` |
| `audio.json` | Per-frame energy (RMS, low and high bands) from the track; drives the HUD meter, shake and RGB split |
| `music/Neon_Genesis_Protocol.wav` | The soundtrack |
| `assets/` | Brand images from the plugin repo (`hero.png` is `docs/assets/hero.webp` converted) |
| `fonts/` | Anton, Permanent Marker, Saira Stencil One, JetBrains Mono, Inter, each with its license |
| `tools/analyze.py` | Regenerates `audio.json` from a track (needs `librosa`) |
| `tools/sheet.py` | Tiles rendered stills into 2x2 contact sheets for review |

## Render

Needs Node with Playwright and Chromium, ffmpeg, and Python with Pillow for contact sheets.

```bash
cd launch-film
node render.mjs stills 4.6,25.6,58.0,73.0 ../stills   # quick review frames
./build.sh                                            # full film, ~3-5 min on 4 cores
```

## Timing

The beat grid is hard-coded in `film.js`: first beat at `B0 = 0.093s`, one beat every `BP = 0.6009s` (~99.8 BPM).
`bt(n)` gives the time of beat `n`. Scenes are listed in `SCENES` by beat. The cuts to black are listed in `STOPS`.

| Beats | Time | Scene |
| --- | --- | --- |
| 0-6 | 0-3.7s | Cold open: glitched Hermes statue, typed "3 files delivered" |
| 6-24 | 3.7-14.5s | Problem: accelerating chat feed, word slams, "Where'd it go?" |
| 24-48 | 14.5-28.9s | Reveal: caution tape, logo build, Keep the work / Skip the hunt, `/shelf add` |
| 48-60 | 28.9-36.2s | Breakdown: neon and rain over the Together and Library screenshots |
| 60-96 | 36.2-57.8s | Features: versions, recovery, originals, Telegram, metadata, privacy, riser |
| 96-112 | 57.8-67.4s | Drop: one word per beat, sticker bomb |
| 112-120 | 67.4-72.2s | Install command |
| 120-128 | 72.2-77.0s | Finale lockup |
| 128+ | 77.0-80s | End card |

To retime for a different track, run `tools/analyze.py` on it, then update `B0`, `BP`, `STOPS` and the scene beat numbers.
