<img width="537" height="449" alt="sf2" src="https://github.com/user-attachments/assets/26ee9c45-1c52-4643-9102-3492afff44c9" />

# sf2-to-ableton

**Convert SoundFont (.sf2) files into native Ableton Live Sampler presets — no beta, no extension SDK required.**

Ableton removed native `.sf2` import from Live's UI starting with Live 11. The
only way to bring it back right now is a Live 12 **beta** extension (using
Ableton's still-in-beta Extensions SDK). If you don't want to run beta
software just to import a SoundFont, this tool does the same job as a
completely standalone script: point it at a `.sf2` file (or a whole folder of
them), and it drops ready-to-use Sampler presets straight into your User
Library.

No Ableton version requirement, no beta, no plugin installation, no external
Python dependencies — just Python 3's standard library.

## What it does

For every preset inside a SoundFont, the tool generates one Ableton **Sampler**
device preset (`.adv`), with:

- key range and velocity range per zone
- root key / base pitch
- sustain loop points (when present in the SoundFont)
- each sample exported as a standalone 16-bit mono AIFF file

The generated `.adv` file is a gzip-compressed XML using Ableton's
Live-10.1-era Sampler schema, which Live 10, 11 and 12 all read natively —
this is exactly the format Ableton's own SoundFont importer used to produce
before it was removed from the UI.

## Why this works without the Live 12 beta

The Extensions SDK (used by [soundfont-importer](https://github.com/norakorra/soundfont-importer),
the project this tool is based on) only provides the right-click "Import
SoundFont" menu entry inside Live's UI. The actual conversion — parsing the
SF2 file and writing the `.adv`/`.aif` files — has nothing to do with the SDK
or the beta; it's plain file I/O. This project extracts that logic into a
standalone script so you don't need Live 12 beta at all.

## Installation

Nothing to install beyond Python 3 (already on macOS; easy to grab on
Windows/Linux). Just download `sf2_lib.py` and `sf2_to_ableton.py` and keep
them in the same folder.

## Usage

### GUI (double-click, no terminal needed)

Double-click `sf2_to_ableton.py`, or run it with no arguments. A small window
lets you:

- pick a single `.sf2` file, **or**
- pick a folder — every `.sf2` found in it (including subfolders) gets
  converted in one batch, with a progress bar and a per-file log. A broken or
  unsupported file is reported and skipped; it won't stop the rest of the
  batch.

### Command line

```bash
# Single file (auto-detects your Ableton User Library based on your OS)
python3 sf2_to_ableton.py "MyInstrument.sf2"

# Custom User Library location
python3 sf2_to_ableton.py "MyInstrument.sf2" --user-library "/path/to/User Library"

# Only convert presets whose name contains a given text
python3 sf2_to_ableton.py "MyInstrument.sf2" --filter "Piano"

# Preview the presets inside a SoundFont without converting anything
python3 sf2_to_ableton.py --list "MyInstrument.sf2"

# Whole folder, recursively (any nesting of subfolders)
python3 sf2_to_ableton.py "C:\My SoundFonts"
python3 sf2_to_ableton.py "C:\My SoundFonts" --user-library "D:\Ableton\User Library"
```

Default User Library locations:
- macOS: `~/Music/Ableton/User Library`
- Windows: `%USERPROFILE%\Documents\Ableton\User Library`

### After conversion

Files are written under your User Library as:

```
User Library/
  Samples/<SoundFontName>/*.aif
  SoundFont Imports/<SoundFontName>/*.adv
```

In Live: **Browser > Places** → right-click → **Add Folder** → select the
`SoundFont Imports` folder. You only need to do this once — every future
conversion shows up automatically inside it, in its own per-SoundFont
subfolder.

## Known limitations

- Stereo sample pairs in the SoundFont (linked left/right channels) are
  exported as two independent mono samples rather than merged into a true
  stereo sample — this matches the behavior of the original extension this
  project is based on.
- ROM-based samples (SoundFonts pointing at hardware sound chips — rare
  nowadays) aren't exported, since there's no audio data for them inside the
  file itself.
- SF2 modulators (LFOs, advanced envelopes, etc.) aren't carried over — only
  key/velocity mapping, base tuning, and loop points are, matching Ableton's
  historical native SF2 import behavior.

## Documentation in other languages

A French version of the usage guide is available in [`LISEZMOI.md`](./LISEZMOI.md).

## Credits

The SoundFont parsing logic and the `.adv` preset XML structure are adapted
from [**soundfont-importer**](https://github.com/norakorra/soundfont-importer)
by **Nora Korra** (Aaron Werinussa), released under the MIT License. That
project's Extensions-SDK approach is the "official", UI-integrated way to get
this functionality inside Ableton Live 12 beta — if you're comfortable
running the beta, it's a great option and a much smoother in-app experience.
This repository exists purely as a beta-free, dependency-free alternative for
people who want the same conversion without upgrading their install.

See [`THIRD_PARTY_LICENSES.md`](./THIRD_PARTY_LICENSES.md) for the full
original license text, reproduced as required by its terms.

## License

MIT — see [`LICENSE`](./LICENSE).
