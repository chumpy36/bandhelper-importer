# BandHelper song importer

Turns a short list of songs into BandHelper-ready files, auto-filling the
tedious fields. Built because BandHelper has no API — but it *does* import
ChordPro files and tab-delimited batches natively, so this generates those.

> Tempo (BPM) and song key data provided by
> **[GetSongBPM](https://getsongbpm.com)** — https://getsongbpm.com

## Why this exists
The band picks a few songs in person, then someone hand-enters each one into
BandHelper (key, tempo, duration, lyrics, chords) and adds it to the gig's set
list. This automates everything except the final set-list ordering (no API for
that — but songs get pre-tagged by gig so it's a fast filtered drag).

## One-time setup
1. Python 3 (already on the Mac).
2. Free GetSongBPM key for BPM + Key (optional but recommended):
   - Register at https://getsongbpm.com/api
   - `export GETSONGBPM_API_KEY=xxxxxxxx`  (add to ~/.zshrc to persist)
   - Their terms require a backlink to https://getsongbpm.com — satisfied by
     this line in the README.

## Each gig
1. Edit `songs.txt`:
   ```
   # tag: Smith Wedding 2026-07-04
   Brown Eyed Girl | Van Morrison
   Wonderwall | Oasis
   ```
   The `# tag:` line is the gig name; every song gets tagged with it.
   Separator between title and artist can be `|`, `-`, or `—`.

2. (Optional, for chords) On Ultimate Guitar, select the chord chart, copy it,
   and paste into `chords/<exact song title>.txt`. The tool converts UG's
   "chords above lyrics" layout into inline ChordPro automatically.
   Skip this and you still get metadata + lyrics.

3. Run:
   ```
   python3 bandhelper.py songs.txt
   ```

4. Import into BandHelper:
   - **ChordPro (recommended):** drag `out/*.pro` into BandHelper. Each file
     carries title, artist, key, tempo, duration, tags, and chords/lyrics.
   - **Batch import fallback:** Repertoire → Songs → Batch Import → `out/import.tsv`.

5. In BandHelper, filter songs by the gig tag and drag them into the set list
   in the order you want. (This last step stays manual — no API.)

## Data sources
| Field      | Source            | Key needed |
|------------|-------------------|------------|
| Duration   | iTunes Search API | no         |
| Lyrics     | lyrics.ovh        | no         |
| BPM + Key  | GetSongBPM        | free key   |
| Chords     | your UG paste     | —          |

## Known limits
- Ultimate Guitar blocks automated fetching (Cloudflare 403), so chords come
  from your copy-paste, not auto-download.
- lyrics.ovh doesn't have every song; misses leave the lyrics field blank
  (the UG paste includes lyrics anyway).
- Chord/lyric column alignment depends on UG's spacing; tweak the pasted text
  if a chord lands a character off.
