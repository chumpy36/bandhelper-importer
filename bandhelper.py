#!/usr/bin/env python3
"""
bandhelper.py — turn a short list of songs into BandHelper-ready files.

Workflow (matches how the band actually works):
  1. You decide on a few songs in person.
  2. List them in songs.txt, one per line:   Title | Artist
     (the first comment line can set a gig tag, see below)
  3. (Optional) For each song you want chords on, copy the chord text from
     Ultimate Guitar and paste it into  chords/<Title>.txt
  4. Run:  python3 bandhelper.py songs.txt
  5. Drag the generated out/*.pro files into BandHelper (it imports ChordPro
     natively). Or use out/import.tsv via Repertoire > Songs > Batch Import.

What gets filled automatically:
  - Duration   <- iTunes Search API      (no key)
  - Lyrics     <- lyrics.ovh             (no key)
  - BPM + Key  <- GetSongBPM API         (free key, set GETSONGBPM_API_KEY)
  - Chords     <- your pasted UG text, converted to inline ChordPro

GetSongBPM is optional: if no key is set, BPM/Key are just left blank.
Register a free key at https://getsongbpm.com/api  (a backlink to their site
is required by their terms — already included in the README).
"""

import os
import re
import sys
import json
import time
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) BandHelperImporter/1.0"
GETSONGBPM_KEY = os.environ.get("GETSONGBPM_API_KEY", "").strip()
GETSONGBPM_HOST = os.environ.get("GETSONGBPM_HOST", "https://api.getsong.co")

HERE = os.path.dirname(os.path.abspath(__file__))
CHORDS_DIR = os.path.join(HERE, "chords")
OUT_DIR = os.path.join(HERE, "out")


# ----------------------------------------------------------------------------- HTTP
def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def _get_json(url):
    return json.loads(_get(url))


# ----------------------------------------------------------------------------- lookups
def itunes(title, artist):
    """Return (canonical_title, canonical_artist, duration 'm:ss') or (None,...)."""
    q = urllib.parse.quote(f"{title} {artist}")
    url = f"https://itunes.apple.com/search?term={q}&entity=song&limit=1"
    try:
        res = _get_json(url).get("results", [])
        if not res:
            return None, None, None
        d = res[0]
        ms = d.get("trackTimeMillis")
        dur = f"{ms // 60000}:{(ms // 1000) % 60:02d}" if ms else None
        return d.get("trackName"), d.get("artistName"), dur
    except Exception as e:
        print(f"    ! iTunes lookup failed: {e}")
        return None, None, None


def lyrics(title, artist):
    url = (f"https://api.lyrics.ovh/v1/"
           f"{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}")
    try:
        return (_get_json(url).get("lyrics") or "").strip()
    except Exception:
        return ""


def getsongbpm(title, artist):
    """Return (bpm, key) or ('',''). Requires GETSONGBPM_API_KEY."""
    if not GETSONGBPM_KEY:
        return "", ""
    lookup = urllib.parse.quote(f"song:{title} artist:{artist}")
    url = (f"{GETSONGBPM_HOST}/search/?api_key={GETSONGBPM_KEY}"
           f"&type=both&lookup={lookup}")
    try:
        data = _get_json(url)
        hits = data.get("search") or []
        if isinstance(hits, dict):  # API returns an error object sometimes
            return "", ""
        if not hits:
            return "", ""
        h = hits[0]
        bpm = str(h.get("tempo") or "").strip()
        key = (h.get("key_of") or "").strip()
        return bpm, key
    except Exception as e:
        print(f"    ! GetSongBPM lookup failed: {e}")
        return "", ""


# ----------------------------------------------------------------------------- chords
# root + any sequence of quality tokens (maj, min, m, sus, add, dim, aug, …)
# and extensions (7, 9, b5, #11, …), plus optional slash bass. Permissive
# enough for Amadd9 / Fmaj7/C / C#m7b5, strict enough to skip English words.
_QUAL = r"(?:maj|min|sus|add|aug|dim|m|M|\+|°|ø)"
_EXT = r"(?:[#b]?(?:11|13|2|4|5|6|7|9))"
CHORD_RE = re.compile(
    rf"^[A-G][#b]?(?:{_QUAL}|{_EXT})*(?:/[A-G][#b]?)?$"
)


def _is_chord_line(line):
    toks = line.split()
    if not toks:
        return False
    good = sum(1 for t in toks if CHORD_RE.match(t))
    return good == len(toks) and good >= 1


def parse_chord_header(text):
    """Pull optional Capo / Key from a UG chart's header lines.

    UG pastes often start with 'Tuning: …  Key: Eb  Capo: 3rd fret' (sometimes
    mashed onto one line). The transcriber's key/capo describe the actual
    arrangement, so they should override the auto-detected GetSongBPM key.
    Returns (capo, key) as strings ('' if absent)."""
    head = text[:400]
    capo = ""
    m = re.search(r"Capo:\s*(\d+)", head, re.I)
    if m:
        capo = m.group(1)
    key = ""
    m = re.search(r"Key:\s*([A-G][#b]?m?)", head)
    if m:
        key = m.group(1)
    return capo, key


def ug_to_chordpro(text):
    """Convert Ultimate-Guitar copy-paste (chords above lyrics) to ChordPro."""
    out_lines = []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        # Drop UG metadata header lines (Tuning:/Key:/Capo:) — parsed separately.
        if re.match(r"^\s*(?:Tuning|Key|Capo)\s*:", line):
            i += 1
            continue
        # UG section headers: [Verse], [Chorus], etc.
        m = re.match(r"^\[(.+?)\]\s*$", line.strip())
        if m:
            out_lines.append(f"{{comment: {m.group(1)}}}")
            i += 1
            continue
        if _is_chord_line(line):
            nxt = lines[i + 1].rstrip() if i + 1 < len(lines) else ""
            if nxt and not _is_chord_line(nxt):
                out_lines.append(_merge(line, nxt))
                i += 2
                continue
            # chord-only line (intro/instrumental)
            out_lines.append(" ".join(f"[{t}]" for t in line.split()))
            i += 1
            continue
        out_lines.append(line)
        i += 1
    return "\n".join(out_lines).strip()


def _merge(chord_line, lyric_line):
    """Place [chords] inline above the lyric at the right column positions."""
    positions = []  # (col, chord)
    for mt in re.finditer(r"\S+", chord_line):
        positions.append((mt.start(), mt.group(0)))
    if len(lyric_line) < len(chord_line):
        lyric_line = lyric_line + " " * (len(chord_line) - len(lyric_line))
    out = []
    last = 0
    for col, chord in positions:
        col = min(col, len(lyric_line))
        out.append(lyric_line[last:col])
        out.append(f"[{chord}]")
        last = col
    out.append(lyric_line[last:])
    return "".join(out).rstrip()


def load_chords(title):
    """Return (chordpro_text, capo, key) for a pasted UG chart, or ('','','')."""
    for name in (title, title.lower()):
        p = os.path.join(CHORDS_DIR, f"{name}.txt")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                raw = f.read()
            capo, key = parse_chord_header(raw)
            return ug_to_chordpro(raw), capo, key
    return "", "", ""


# ----------------------------------------------------------------------------- output
def safe(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def write_chordpro(song, tag):
    lines = [f"{{title: {song['title']}}}", f"{{artist: {song['artist']}}}"]
    if song["key"]:
        lines.append(f"{{key: {song['key']}}}")
    if song.get("capo"):
        lines.append(f"{{capo: {song['capo']}}}")
    if song["bpm"]:
        lines.append(f"{{tempo: {song['bpm']}}}")
    if song["duration"]:
        lines.append(f"{{time: {song['duration']}}}")
    if tag:
        lines.append(f"{{meta: tags {tag}}}")
    lines.append("")
    if song["chords"]:
        lines.append(song["chords"])
    elif song["lyrics"]:
        lines.append(song["lyrics"])
    path = os.path.join(OUT_DIR, f"{safe(song['title'])}.pro")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


# BandHelper's tab-delimited Songs import expects this EXACT 16-column order
# (no header row; line breaks inside a field encoded as literal \n).
TSV_COLS = ["Title", "Artist", "Tags", "Key", "Time signature", "Tempo",
            "Duration", "Starting pitch", "Document filenames",
            "Recording filenames", "MIDI preset names", "Lyrics", "Chords",
            "Notes", "MIDI song number", "MIDI program change"]


def write_tsv(songs, tag):
    # .txt extension because BandHelper's Songs > Batch Import requires it.
    path = os.path.join(OUT_DIR, "import.txt")
    with open(path, "w", encoding="utf-8") as f:
        for s in songs:
            notes = f"Capo {s['capo']}" if s.get("capo") else ""
            # Mirror BandHelper's own ChordPro import: the inline-chord chart
            # (which already contains the lyrics) goes in the main Lyrics field,
            # which is shown by default and renders [chords]. Plain lyrics only
            # when there's no chart.
            body = s["chords"] or s["lyrics"]
            row = {
                "Title": s["title"], "Artist": s["artist"], "Tags": tag,
                "Key": s["key"], "Tempo": s["bpm"], "Duration": s["duration"],
                "Lyrics": body.replace("\n", "\\n"),
                "Notes": notes,
            }
            line = [str(row.get(col, "") or "") for col in TSV_COLS]
            f.write("\t".join(line) + "\n")
    return path


# ----------------------------------------------------------------------------- main
def parse_input(path):
    tag = ""
    songs = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                m = re.search(r"tag\s*:\s*(.+)", line, re.I)
                if m:
                    tag = m.group(1).strip()
                continue
            parts = re.split(r"\s*[|\-—]\s*", line, maxsplit=1)
            title = parts[0].strip()
            artist = parts[1].strip() if len(parts) > 1 else ""
            songs.append((title, artist))
    return tag, songs


def main():
    if len(sys.argv) < 2:
        print("usage: python3 bandhelper.py songs.txt")
        sys.exit(1)
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(CHORDS_DIR, exist_ok=True)
    tag, pairs = parse_input(sys.argv[1])
    if tag:
        print(f"Gig tag: {tag}")
    if not GETSONGBPM_KEY:
        print("(no GETSONGBPM_API_KEY set — BPM/Key will be blank)\n")

    results = []
    for title, artist in pairs:
        print(f"• {title} — {artist or '?'}")
        c_title, c_artist, dur = itunes(title, artist)
        title = c_title or title
        artist = c_artist or artist
        bpm, key = getsongbpm(title, artist)
        chords, capo, chart_key = load_chords(title)
        # The chart's own key (from the transcriber) wins over GetSongBPM's guess.
        if chart_key:
            key = chart_key
        song = {
            "title": title, "artist": artist, "duration": dur or "",
            "bpm": bpm, "key": key, "capo": capo,
            "lyrics": lyrics(title, artist),
            "chords": chords,
        }
        got = []
        if dur:
            got.append(f"dur {dur}")
        if bpm:
            got.append(f"{bpm} bpm")
        if key:
            got.append(f"key {key}" + (f" capo {capo}" if capo else ""))
        if song["lyrics"]:
            got.append("lyrics")
        got.append("CHORDS" if song["chords"] else "no-chords(paste UG)")
        print("    " + ", ".join(got))
        p = write_chordpro(song, tag)
        print(f"    -> {os.path.relpath(p, HERE)}")
        results.append(song)
        time.sleep(0.3)  # be polite to the free APIs

    tsv = write_tsv(results, tag)
    print(f"\nDone. {len(results)} songs.")
    print(f"  Web app:  Repertoire > Songs > Batch Import  ->  "
          f"{os.path.relpath(tsv, HERE)}")
    print(f"  Mobile/ChordPro:  out/*.pro  (iOS/Android: Songs > Import > "
          f"ChordPro)")


if __name__ == "__main__":
    main()
