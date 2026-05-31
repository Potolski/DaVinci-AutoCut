# DaVinci Resolve Auto-Cut

A small, standalone desktop tool that removes silent gaps from a
**DaVinci Resolve** timeline. It connects to a running Resolve instance over the
official Python scripting API, analyzes the source audio outside of Resolve with
**ffmpeg + pydub**, and produces a **new cut timeline** that you can keep
editing.

Your original timeline is never touched — the result is always a fresh timeline
in the same project, so the original stays as a backup.

> Works with the **free** version of DaVinci Resolve. No Studio-only features are
> used, and no video is ever exported or rendered — the new timeline just
> references your existing media via in/out subclips.

## What it does

1. Connects to an already-running DaVinci Resolve instance.
2. Reads every video clip on the **currently open timeline**, including each
   clip's source media path and source in/out points.
3. For each clip, analyzes the source audio to find silent regions —
   "silent" means below a configurable dB threshold, and only silences longer
   than a configurable minimum duration are cut.
4. Computes the **keep** (non-silent) ranges and adds a small configurable
   padding (default 150 ms) on each side so cuts don't clip speech.
5. Builds a **new timeline** (named `<original> - AutoCut`) from those keep
   ranges. The original timeline is left intact.

## Windows: download and run (no Python, no ffmpeg)

The easiest way on Windows is the prebuilt **`DaVinciAutoCut.exe`**. It bundles
Python, all dependencies, **and ffmpeg** — so you just download one file and
double-click it.

1. Make sure **DaVinci Resolve is installed and running**, with scripting set to
   **Local** (see [Enable scripting](#1-enable-scripting-in-resolve)) and the
   timeline you want to cut open.
2. Download `DaVinciAutoCut.exe` from the
   [**Releases**](../../releases/latest) page. (Don't have a release yet? See
   [Building the Windows .exe](#building-the-windows-exe) — it can be produced
   automatically by GitHub Actions.)
3. Double-click `DaVinciAutoCut.exe`.
4. Click **Connect to Resolve**, adjust the sliders, and click **Cut Timeline**.

That's it — nothing else to install. The only thing the .exe can't include is
DaVinci Resolve itself, because the whole point is to connect to *your* running
copy.

> Windows may show a SmartScreen "unknown publisher" warning for an unsigned
> executable. Click **More info → Run anyway**.

## Requirements

> These apply if you run from source or on macOS/Linux. Windows users running the
> prebuilt `.exe` only need DaVinci Resolve.

- **DaVinci Resolve** (free or Studio), installed and running.
- **Python 3.9+** with **Tkinter** (ships with the standard python.org
  installers and on macOS/Windows; on some Linux distros install `python3-tk`).
- **ffmpeg** installed and on your `PATH`.
- The Python packages in `requirements.txt`.

> **Note on Blackmagic's scripting modules:** this project does **not** bundle or
> redistribute Blackmagic's `DaVinciResolveScript` Python module. The app loads
> it at runtime from *your own* DaVinci Resolve installation. You must have
> Resolve installed for the scripting bridge to work.

## Setup

### 1. Enable scripting in Resolve

In DaVinci Resolve:

**Preferences → System → General → "External scripting using"** → set it to
**Local**.

Then restart Resolve and open the project/timeline you want to cut.

### 2. Install ffmpeg

- **macOS:** `brew install ffmpeg`
- **Windows:** download a build from
  <https://www.gyan.dev/ffmpeg/builds/> and add its `bin/` folder to your
  `PATH`.
- **Linux:** `sudo apt install ffmpeg` (or your distro's equivalent).

Verify it's reachable:

```bash
ffmpeg -version
```

### 3. Install Python dependencies

```bash
python -m pip install -r requirements.txt
```

On **Python 3.13+**, `requirements.txt` also pulls in `audioop-lts`, a backport
of the `audioop` module that pydub needs (it was removed from the standard
library in 3.13).

## Running

With Resolve open and a timeline loaded:

```bash
python autocut.py
```

Then in the window:

1. Click **Connect to Resolve** — the status turns green when connected.
2. Adjust the settings if you like:
   - **Silence threshold (dB)** — default `-40`. Lower (more negative) keeps
     quieter audio.
   - **Min silence (seconds)** — default `0.5`. Shorter pauses are never cut.
   - **Padding (ms)** — default `150`. Breathing room kept around each segment.
3. Click **Cut Timeline**. Progress and results appear in the log.

When it finishes, a new timeline called `<your timeline> - AutoCut` is created
and selected in Resolve.

### Quick connection test

To verify the scripting bridge before using the GUI, run the read-only smoke
test (Resolve must be open with a timeline):

```bash
python -m autocut.list_clips
```

It prints the clips on the current timeline with their source paths and in/out
frames.

## How it's organized

```
autocut.py              # GUI entry point
autocut/
  resolve_env.py        # locates Resolve's scripting modules, sets env vars
  resolve_api.py        # connect, read timeline clips, build the new timeline
  audio_analysis.py     # ffmpeg + pydub silence detection, padding, merging
  processor.py          # orchestration + millisecond-to-frame conversion
  gui.py                # Tkinter interface
  list_clips.py         # 'python -m autocut.list_clips' connection smoke test
```

The Resolve connection, audio analysis, and GUI are deliberately kept in
separate modules.

## Building the Windows .exe

The repo ships everything needed to produce the standalone
`DaVinciAutoCut.exe`. It bundles ffmpeg via the
[`autocut.spec`](autocut.spec) PyInstaller spec.

### Option A — let GitHub Actions build it (no Windows machine needed)

The [`build-windows.yml`](.github/workflows/build-windows.yml) workflow builds
the `.exe` on a Windows runner automatically:

- **Every push to `main`** (and manual *Run workflow* from the Actions tab):
  the `.exe` is uploaded as a downloadable **build artifact**.
- **Pushing a version tag** publishes the `.exe` to a **GitHub Release**:

  ```bash
  git tag v0.1.0
  git push origin v0.1.0
  ```

  The finished `DaVinciAutoCut.exe` then appears on the repo's Releases page.

### Option B — build locally on Windows

With Python 3.9+ installed, from the repo root:

```bat
build_windows.bat
```

It installs the dependencies, downloads ffmpeg into `vendor/`, runs PyInstaller,
and leaves the result at `dist\DaVinciAutoCut.exe`.

Notes:

- DaVinci Resolve still has to be installed on the target machine — PyInstaller
  bundles the Python app and ffmpeg, but not Resolve.
- Blackmagic's scripting module is still loaded from the local Resolve install
  at runtime, by design.
- The bundled ffmpeg is a GPL build from <https://www.gyan.dev/ffmpeg/builds/>;
  it is downloaded at build time and is not committed to this repository.

### macOS / Linux

The same spec works for a native app bundle if you place an `ffmpeg` binary in
`vendor/` first:

```bash
python -m pip install pyinstaller
pyinstaller autocut.spec
```

## Troubleshooting

- **"Could not connect to DaVinci Resolve"** — make sure Resolve is running and
  that external scripting is set to **Local** (see Setup), then restart Resolve.
- **"Could not import the DaVinci Resolve scripting module"** — Resolve isn't
  installed in a standard location. Set the `RESOLVE_SCRIPT_API` and
  `RESOLVE_SCRIPT_LIB` environment variables to your install's paths before
  launching.
- **"ffmpeg was not found on your PATH"** — install ffmpeg and make sure
  `ffmpeg -version` works in the same terminal.
- **"No timeline is open"** — open a timeline in Resolve first.

## License

[MIT](LICENSE) © 2026 David Potolski Lafetá

Blackmagic Design, DaVinci Resolve, and related marks are trademarks of
Blackmagic Design. This project is an independent tool and is not affiliated
with or endorsed by Blackmagic Design.
