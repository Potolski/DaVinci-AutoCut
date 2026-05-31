# DaVinci AutoCut

A free, open-source tool that removes silent gaps from a **DaVinci Resolve**
timeline. It runs **inside Resolve** as a script (`Workspace → Scripts →
DaVinci AutoCut`), analyzes your source audio with ffmpeg, and builds a **new
cut timeline** with the silences removed — your original timeline is left
untouched.

Works on the **free** version of DaVinci Resolve *and* Studio. No video is ever
exported or rendered; the new timeline just references your existing media.

## What it does

1. Reads every video clip on the **currently open timeline** (source media path
   + in/out points).
2. For each clip, uses **ffmpeg's `silencedetect`** to find silent regions —
   "silent" means below a configurable dB threshold, and only silences longer
   than a configurable minimum duration are cut.
3. Keeps the non-silent ranges, with a small configurable padding (default
   150 ms) on each side so cuts don't clip speech.
4. Builds a **new timeline** (`<original> - AutoCut`) from those ranges, beside
   the original.

## Why it runs *inside* Resolve (important)

The free version of DaVinci Resolve **does not allow external programs to control
it** via the scripting API — that's a Studio-only feature. What the free version
*does* allow is running a script from **`Workspace → Scripts`**, where Resolve
hands the script a working connection to itself.

So DaVinci AutoCut is delivered as a **Resolve script/plugin**, not a standalone
app. This is the same mechanism commercial tools like AutoCut use to support the
free version.

## Install — Windows (recommended)

1. Download **`DaVinciAutoCut-Setup.exe`** from the
   [Releases](../../releases/latest) page.
2. Run it. The installer:
   - copies the plugin into Resolve's Scripts folder (no admin needed),
   - bundles **ffmpeg** next to the plugin (you don't install it or touch your
     PATH),
   - checks for **Python 3** — which Resolve needs to run Python scripts — and
     offers to install it for you if it's missing.
3. Restart DaVinci Resolve.
4. Open your timeline, then run **`Workspace → Scripts → DaVinci AutoCut`**.

> Windows may show a SmartScreen "unknown publisher" warning for an unsigned
> installer. Click **More info → Run anyway**.

## Install — macOS / Linux (manual)

There's no packaged installer yet for macOS/Linux, but installing by hand is
quick:

1. Install **ffmpeg** and make sure Resolve can find a **Python 3**:
   - macOS: `brew install ffmpeg` (and install Python 3 from python.org if you
     don't have it).
   - Linux: `sudo apt install ffmpeg python3` (or your distro's equivalent).
2. Copy `DaVinci AutoCut.py` **and** the `autocut/` folder into Resolve's
   Scripts folder:
   - macOS: `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/`
   - Linux: `~/.local/share/DaVinciResolve/Fusion/Scripts/Edit/`
3. Restart Resolve → `Workspace → Scripts → DaVinci AutoCut`.

(ffmpeg on your PATH is fine; or drop an `ffmpeg` binary in `autocut/bin/` next
to the plugin.)

## Using it

When you launch it, a small window opens and connects to Resolve automatically.
Adjust the settings and click **Cut Timeline**:

- **Silence threshold (dB)** — default `-40`. Lower (more negative) keeps quieter
  audio.
- **Min silence (seconds)** — default `0.5`. Shorter pauses are never cut.
- **Padding (ms)** — default `150`. Breathing room kept around each segment.

A new timeline `<your timeline> - AutoCut` is created and selected in Resolve.

## Requirements

- DaVinci Resolve 18.6 or 19+ (free or Studio), with a project and timeline open.
- A **Python 3** install Resolve can use (the Windows installer sets this up).
- **ffmpeg** (bundled by the Windows installer; install it yourself on
  macOS/Linux).

There are **no Python package dependencies** — silence detection uses ffmpeg
directly, so there's nothing to `pip install`.

> **Note on Blackmagic's scripting modules:** this project does not bundle or
> redistribute any Blackmagic code. It uses the scripting connection Resolve
> provides to scripts launched from its own Scripts menu.

## How it's organized

```
DaVinci AutoCut.py        # launcher Resolve runs; grabs the injected `resolve`
autocut/
  resolve_api.py          # connect via the injected object, read clips, build timeline
  audio_analysis.py       # ffmpeg silencedetect, padding, merging, ffmpeg location
  processor.py            # orchestration + millisecond-to-frame conversion
  gui.py                  # Tkinter interface
  resolve_env.py          # fallback env setup for external (Studio) connection
installer/
  davinci-autocut.iss     # Inno Setup script for the Windows installer
```

## Building the Windows installer

GitHub Actions builds it for you ([`build-windows.yml`](.github/workflows/build-windows.yml)):
push a version tag and the finished `DaVinciAutoCut-Setup.exe` is attached to a
Release.

```bash
git tag v0.2.0
git push origin v0.2.0
```

To build locally on Windows, install [Inno Setup](https://jrsoftware.org/isinfo.php),
put `ffmpeg.exe` (and optionally `ffprobe.exe`) in `installer/vendor/`, then:

```bat
cd installer
iscc /DFFmpegDir=vendor davinci-autocut.iss
```

The installer lands in `installer/output/`.

## Troubleshooting

- **"Could not obtain the DaVinci Resolve scripting object"** — you're on the
  free version and ran it as a standalone app. Run it from
  `Workspace → Scripts → DaVinci AutoCut` instead, and make sure a project is
  open.
- **Nothing appears under `Workspace → Scripts`** — the files aren't in the
  Scripts folder, or Resolve wasn't restarted after installing.
- **"ffmpeg could not be found"** — on macOS/Linux, install ffmpeg or place an
  `ffmpeg` binary in `autocut/bin/`. On Windows the installer handles this.
- **The Scripts menu is greyed out / Python errors** — Resolve can't find a
  Python 3 interpreter. Install Python 3 (the Windows installer offers to) and
  restart Resolve.
- **"No timeline is open"** — open a timeline in Resolve first.

## License

[MIT](LICENSE) © 2026 David Potolski Lafetá

Blackmagic Design, DaVinci Resolve, and related marks are trademarks of
Blackmagic Design. This project is an independent tool and is not affiliated
with or endorsed by Blackmagic Design.
