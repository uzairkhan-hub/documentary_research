# Enable Pakistan Documentary Studio

Use ChatGPT in your browser to research a topic, draft Urdu narration and plan or create visuals. Bring the results into the studio to review them and assemble a silent rough cut locally. The studio uses no OpenAI API key or ChatGPT account credentials.

## Update an existing Windows checkout

Close the running studio. From the repository root in PowerShell:

```powershell
git switch main
git pull --ff-only origin main
cd enable_pakistan_studio
.\setup_windows.bat
.\start_studio.bat
```

The studio uses its existing `enable_pakistan_studio/projects/` folder. Keep that folder when updating. If you're moving from the original ZIP to a fresh clone, close both copies and copy the old `projects` folder into the new app folder. Back up that folder before moving it. The studio also accepts an absolute project folder path in the optional `DOCUMENTARY_STUDIO_PROJECTS` environment variable.

## First-time setup

1. Install Python 3.11 or 3.12 with the Windows Python launcher (`py`).
2. Install an FFmpeg build with H.264 (`libx264`) and put `ffmpeg` and `ffprobe` on PATH. Open a new terminal and run `ffmpeg -version` and `ffprobe -version`. You can use the planning tools before installing FFmpeg.
3. Clone the repository to a short writable path to avoid Windows path-length issues. Run `setup_windows.bat`, then `start_studio.bat` from `enable_pakistan_studio`. The studio opens at [localhost:8501](http://localhost:8501).

## Make a documentary

1. **Brief and ChatGPT.** Create a project with a title, a short description and a target duration. Copy or download the project-specific prompt. Paste it into ChatGPT and attach any references you want ChatGPT to use.
2. **Import results.** Upload or paste `research_dossier.md`, `script.md` and `storyboard.csv`. The first two also accept plain UTF-8 text. Review claims against the linked sources. Edit scene order in the CSV and reimport, or edit individual scenes in the studio. The template documents the CSV column names. Scene IDs must be unique and durations must be 0.5–900 seconds.
3. **Visuals and rights.** Use each scene's visual direction to find footage or generate a labelled illustration in ChatGPT. Download the files and upload them to the project. Assign a file to each scene and record the origin, creator, licence and required credit. Review restrictions for your intended use. Imported storyboard licence text is a reference for review.
4. **Render and export.** Review missing files and licence statuses, then render. Missing visuals show labelled placeholders. Pending visuals require an explicit private-preview selection, and restricted visuals must be resolved or replaced. Export the storyboard and current attribution register as CSVs.

The studio trims or loops clips to the scene length, holds images for their assigned duration and exports H.264 at 1920×1080 and 25 fps without audio. Add narration, captions and any required on-screen credits or AI-reconstruction labels in your finishing editor. The last successful video stays in `projects/<project>/exports/silent_rough_cut.mp4` if a later render fails.

## Run the checks

From the studio folder with the environment installed:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

The render integration test runs when FFmpeg and FFprobe are available.
