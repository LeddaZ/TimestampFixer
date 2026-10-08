# Filename to Modified Date

## ⚠️ Slop alert! ⚠️

I vibecoded this months ago because I needed to fix some files, I only tested it on Windows amd64.

A small PyQt6 desktop app that fixes the "last modified" timestamp of files
using the date written in their filename.

It runs on Windows, Linux and macOS (Python 3.10 or newer).

## Run

The app runs from a virtual environment in `.venv`. A virtual environment only
works on the machine it was created on, so create it once per machine:

**Windows**

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then double-click `run.bat`, or run `.venv\Scripts\python.exe main.py`.

**Linux and macOS**

```
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Then run `sh run.sh`, or `.venv/bin/python main.py`.

On Linux, if the app exits at startup with an error about the Qt "xcb"
platform plugin, a system library is missing. On Debian or Ubuntu:

```
sudo apt install libxcb-cursor0
```

## How to use

1. Type or pick the **timestamp format** used by your filenames.
2. Pick the **folder** (subfolders are included by default).
3. Press **Scan folder**. The table lists every file with its current and new
   modified date, plus a status.
4. Untick anything you want to leave alone, then press **Apply**. A
   confirmation dialog appears before anything is written.

Files whose name does not contain the format are listed greyed out and cannot
be selected; files that already carry the right timestamp show "up to date" and
start unticked.

## Format tokens

| Token      | Meaning                                        |
|------------|------------------------------------------------|
| `yyyy`     | 4-digit year                                   |
| `yy`       | 2-digit year (00-69 → 2000s, 70-99 → 1900s)    |
| `mm`       | month, or minute when it comes after the hour  |
| `dd`       | day                                            |
| `HH`       | hour, 24h                                      |
| `nn`, `mi` | minute (use these to be explicit)              |
| `ss`       | second                                         |

Everything else in the format is matched literally, and the format is searched
**anywhere inside the filename** — so `yyyymmdd` matches
`backup_20200704_final.zip`. A run of digits longer than the format will not
match, so `yyyymmdd` deliberately ignores `202301151200.txt`.

Anything the format does not cover defaults to the lowest value: **missing time
of day becomes midnight**, a missing day becomes the 1st.

Dates are interpreted in your local timezone. Only the modification time is
written; the access time is preserved and the creation time is left untouched.

Two platform differences:

- **macOS** moves a file's creation date back whenever the modified date is set
  to something earlier than it, so back-dated files get a new creation date too.
- **Linux and macOS** only let you change timestamps on files you own. Other
  files are reported as failed and left alone.

## Standalone build

PyInstaller packages the app so it runs without Python or a venv. It cannot
cross-compile: each build has to be made on the system it is meant for.

| Built on | Command        | Output                    |
|----------|----------------|---------------------------|
| Windows  | `build.bat`    | `dist\TimestampFixer.exe` |
| Linux    | `sh build.sh`  | `dist/TimestampFixer`     |
| macOS    | `sh build.sh`  | `dist/TimestampFixer.app` |

Install the build dependencies first (`.venv/bin/python` on Linux and macOS):

```
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

On Windows and Linux the result is a single self-contained file (~36 MB on
Windows) — copy it anywhere and run it. Being a one-file build it unpacks
itself to a temp folder on launch, so the first window takes a few seconds to
appear.

On macOS the result is an app bundle. It is not signed with a developer
certificate or notarized, so on another Mac the first launch is blocked: open
System Settings > Privacy & Security and press **Open Anyway**.

`build/` and `dist/` are build output and can be deleted at any time.

### Release builds

`.github/workflows/build.yml` makes all of these builds on GitHub, for both
amd64 and arm64. It runs when a release is published and attaches the results
to that release:

| File                               | Runs on                                |
|------------------------------------|----------------------------------------|
| `TimestampFixer-windows-amd64.exe` | Windows, Intel/AMD                     |
| `TimestampFixer-windows-arm64.exe` | Windows on Arm                         |
| `TimestampFixer-macos-amd64.zip`   | Intel Macs                             |
| `TimestampFixer-macos-arm64.zip`   | Apple silicon Macs                     |
| `TimestampFixer-linux-amd64.tar.gz`| glibc 2.35+ (Ubuntu 22.04, Debian 12)  |
| `TimestampFixer-linux-arm64.tar.gz`| glibc 2.39+ (Ubuntu 24.04, Debian 13)  |

It can also be started by hand from the repository's **Actions** tab (**Build**
> **Run workflow**). A manual run does not touch any release; the builds are
downloadable from the run's page as artifacts instead.

## Tests

```
.venv\Scripts\python.exe -m unittest test_timestamp_parser
```

On Linux and macOS use `.venv/bin/python` instead.

`sample_files/` holds a few files to try the app on.
