# From Stockholm, outward. — the Hiking Club film

A brand film for Hiking Club, SASSE. It plays last on the home page and is cut three more ways for
the site and for social. There is no stock footage and no generated video in it: the picture is the
club's own photographs (the ones the site already uses, graded colder and moved with a camera), the
real terrain of Abisko, and a handful of scenes drawn in code. The sound is synthesised, every bit
of it: wind, snow under boots, breath, a carabiner gate, lake ice, a night train, the score.

| File (`site/assets/film/`) | Length | Use |
|---|---|---|
| `hiking-club-film.mp4` | 1:30, 16:9, sound | The film: home page, events, recruitment |
| `hiking-club-film-30s.mp4` | 0:30, 16:9, sound | Social, club promotion, before a talk |
| `hiking-club-film-30s-vertical.mp4` | 0:30, 9:16, sound | Stories, Reels, TikTok |
| `hiking-club-loop.mp4`, `.webm` | 0:12, silent, seamless | Website background: fog, the mountain, a tiny group, snow |
| `poster.webp`, `poster-film.webp` | stills | The loop's first frame; the film's last people standing |

## Rebuild

```
python3 site/tools/film/film.py full      # frames, then the mix, then the mp4   (~40 min on 4 cores)
python3 site/tools/film/film.py cut       # the 30 s cut                          (~13 min)
python3 site/tools/film/film.py cut --size 1080x1920   # the same cut, framed for vertical
python3 site/tools/film/film.py loop      # the loop, mp4 + webm, cut to start on its poster
python3 site/tools/film/film.py posters
python3 site/tools/film/film.py full --sheet           # one frame per shot, for review (seconds)
python3 site/tools/film/sound.py full full.wav         # the mix alone (15 s)
```

Needs Python 3.11+, `numpy pillow scipy fonttools brotli cairosvg`, and ffmpeg with libx264,
libvpx-vp9 and aac (`pip install imageio-ffmpeg` ships one). `--work DIR` keeps the rendered PNG
frames between runs; only missing frames are rendered again.

| File | What it holds |
|---|---|
| `film.py` | The edit: every shot, its framing and camera move, the three timelines, the words, the expedition labels, the white card, the renderer |
| `kit.py` | The camera over a still, the grade, fog, snow and spindrift, light, grain, type, people |
| `scenes.py` | The drawn scenes: Sveavägen before sunrise, the doorway, rain on a window, the night train, the metro, a lecture hall, a spreadsheet, the Abisko map under a headlamp, headlamps in the valley, the hut, the altimeter |
| `sound.py` | The instruments, the score, the rooms (convolution reverb) and the mix; reads the same timeline as the picture |

## How it is made

- **Stills, moved.** Each photograph is framed by a point of interest and a zoom, so the same shot
  crops itself to 16:9 or 9:16; a few shots carry their own vertical framing. Subjects stay out of
  the outer tenth of the frame, and the labels stay inside a safe area.
- **Weather is drawn on top.** Fog is two layers of drifting fractal noise; snow, spindrift and rain
  are particles with motion blur. The light in the dark scenes (lamps, headlamps, windows) is a
  core, a halo and a wide bloom.
- **People.** Distant walkers are drawn silhouettes (eight times over-sampled, eight to forty pixels
  tall). The group standing with the red-jacketed hiker at the end is that hiker himself, cut out of
  his photograph and placed four more times, smaller, mirrored, in other jackets.
- **Stockholm is geometry, the north is texture.** The school, the streets, the lecture hall and the
  laptop are drawn in code: rows of lights, a lit doorway, a grid of numbers. The wilderness is
  photographs. The contrast is the point of the film, and it is also honest: there was no footage of
  SSE to use. These are the shots to replace first with real footage (below).
- **The words are type, not voice.** Newsreader, where the voice-over would be, so the film works
  muted (a website autoplays muted) and with sound. The voice can be added without re-rendering.
- **Grade.** The site's documentary grade, then colder: less saturation, a low contrast pivot, navy
  in the shadows, a matte black, film grain in the midtones.

## The edit (full film)

| Time | Section | Picture | Sound |
|---|---|---|---|
| 0:00 | Dark | Black, then a ridge through cloud | Distant wind, a boot in snow, breath, fabric, a carabiner, lake ice |
| 0:08 | Stockholm | Sveavägen before sunrise · the doors of Sveavägen 65 · rain on a window, fading out | The city through glass, footsteps, a heavy door, rain |
| 0:18 | The world opens | Night train · the Abisko map under a headlamp · headlamps in the valley · Lapporten at dawn | The train comes in hard; paper, a click; the score begins, low |
| 0:30 | Manifesto | Whiteout, one walker · a skier · the track, pulling back · the wall, tilting up · the Kebnekaise ridge | Wind, steps, breath |
| 0:45 | The body | Thirteen cuts: rope, rain on granite, snow, ice, spindrift, map, altimeter, water, forest, rock, a climber, fog, a belay | One sound per cut; a heartbeat that quickens; a riser |
| 0:53 | Scale | Six people crossing Storglaciären under Kebnekaise | Everything stops. Wind |
| 0:57 | The voice returns | The moon ridge · the train · the hut, a headlamp arriving · the rope | A door, the stove, a mug; felt piano |
| 1:09 | Two lives | Lecture hall / mountain · laptop / map · metro / night train | Fluorescent hum against the wind |
| 1:14 | The ending | One hiker on the plateau; the others come into frame as the camera pulls back · Lapporten, the group almost invisible | Near silence, three notes |
| 1:24 | White | Hiking Club · SASSE, Stockholm School of Economics · *From Stockholm, outward.* · Join the next expedition. | Nothing, then one low note |

## The voice-over

The film is finished without a voice; it was written for one. To add it, record the lines below,
put each as a WAV in `site/tools/film/vo/` under the name shown, and run the mix and the encode
again (the picture does not need re-rendering if the frames are kept with `--work`):

```
python3 site/tools/film/film.py full --work /tmp/film-full     # reuses frames, re-mixes, re-encodes
```

Each file is placed at its line, the rest of the mix ducks under it, and the 30 s cut picks up the
lines it shares. `python3 site/tools/film/sound.py lines` prints this list.

| File (`vo/…`) | At | Length | Line |
|---|---|---|---|
| `most-days-begin-the-same-way.wav` | 0:05.7 | 2.8 s | Most days begin the same way. |
| `the-same-streets.wav` | 0:09.1 | 2.3 s | The same streets. |
| `the-same-doors.wav` | 0:12.0 | 2.2 s | The same doors. |
| `the-same-distance-between-where-you-are.wav` | 0:14.8 | 2.5 s | The same distance between where you are… |
| `and-somewhere-else.wav` | 0:17.4 | 1.4 s | …and somewhere else. |
| `some-places-dont-ask-who-you-are.wav` | 0:30.9 | 2.8 s | Some places don't ask who you are. |
| `only-whether-you-keep-moving.wav` | 0:34.2 | 2.6 s | Only whether you keep moving. |
| `further.wav` | 0:38.2 | 1.9 s | Further. |
| `higher.wav` | 0:40.5 | 1.8 s | Higher. |
| `together.wav` | 0:42.9 | 2.4 s | Together. |
| `you-will-forget-the-cold.wav` | 0:57.4 | 2.5 s | You will forget the cold. |
| `you-will-forget-the-distance.wav` | 1:00.3 | 2.4 s | You will forget the distance. |
| `you-will-probably-forget-how-much-your-legs-hurt.wav` | 1:03.1 | 3.1 s | You will probably forget how much your legs hurt. |
| `but-you-wont-forget-who-was-there.wav` | 1:06.6 | 3.0 s | But you won't forget who was there. |
| `stockholm-is-where-we-meet.wav` | 1:15.6 | 2.6 s | Stockholm is where we meet. |
| `not-where-we-stop.wav` | 1:18.8 | 2.8 s | Not where we stop. |

**Casting and delivery.** One voice, low, unhurried, a little rough: someone who has been on the
trips, not an announcer. Record close (a hand's width from a cardioid, in a small dead room: a
wardrobe of coats works), at conversational level, never projected. Leave a second of silence
before and after each line; the mix trims nothing, so start the line at the start of the file.
Say the three single words as a person thinking, not a slogan. "Legs hurt" gets the smallest smile
in the voice and nothing more. After recording, change the caption in `build_pages.py` (`film()`)
that says every sound was synthesised.

## Replacing a drawn shot with real footage

The drawn Stockholm shots are stand-ins until there is footage. Shoot it, then swap the shot in
`film.py` for a clip; `footage()` frames and grades it like everything else:

```python
P["doors"] = footage("site/tools/film/footage/sse-doors.mov", fx=0.5, fy=0.55, z=(1.0, 1.04), ev=-0.3, sat=0.5)
```

Shot list, in the order they would help most. Shoot flat (a log profile or a neutral picture style),
at 25 or 24 fps, 180° shutter, 4K if possible for the crops; never direct anyone to camera.

1. **The doors of Sveavägen 65**, 07:45–08:10 in November, from across the street on a long lens:
   people going in, the door swinging, the light inside warmer than the street. 10 s.
2. **Sveavägen before sunrise**, long lens down the street, wet asphalt, lamps still on. 10 s.
3. **A window with rain**, from inside the school, the street soft behind. 10 s.
4. **Hands**: lacing boots, closing a pack, a rope through a belay device, a map unfolded on a
   knee, a thumb on a headlamp switch. 3 s each, handheld, close.
5. **The night train**: a compartment window at night, a reflection, forest passing. 10 s.
6. **A lecture hall, a laptop, the metro**: one second of each is enough.
7. **On the next expedition**: headlamps before dawn, jackets drying in a hut, coffee poured
   outside a tent, someone pulling someone up onto a rock, the group on a ridge from behind and
   very far away. These would replace stills with the club's own people.
