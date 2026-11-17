# Enable Pakistan Documentary Studio (voice-free starter)

This is a **local, free, CPU-friendly** documentary project organiser and silent visual rough-cut renderer. It does **not** connect directly to your ChatGPT Plus account, conduct automatic web research, generate unlimited AI visuals, or install software on your behalf.

## Windows setup
1. Install Python 3.11 or 3.12 from https://www.python.org/downloads/windows/ (enable PATH).
2. Install FFmpeg from https://ffmpeg.org/download.html if you want MP4 rendering. Ensure `ffmpeg` and `ffprobe` work in Command Prompt (`ffmpeg -version`). The studio works without FFmpeg for project planning.
3. Extract the ZIP to a normal writable folder, e.g. Documents\EnablePakistanStudio.
4. Double-click `setup_windows.bat`, then `start_studio.bat`.
5. The dashboard opens at http://localhost:8501.

## Workflow
- Create a project with a title, target duration, and research notes.
- Upload reference documents and footage. Documents are saved locally; use ChatGPT to read and research them. No content is automatically sent to ChatGPT.
- Ask ChatGPT for a fact-checked documentary script, a source register, and a `storyboard.csv` using the template downloadable from the dashboard.
- Import the CSV, attach visual files to each scene, then render a **silent 1920x1080 MP4 rough cut** with FFmpeg.
- A missing scene asset produces a labelled placeholder; this is deliberate so you can identify gaps. Uploaded still images are held for scene duration. Videos are trimmed/looped to the duration. Audio is removed.
- Add voice-over later using a separate audio integration and timing revisions.

## Important limitations
- No direct ChatGPT Plus API access is included; OpenAI API billing is separate.
- The app does not verify copyright or accuracy. Maintain source and licence details for each visual.
- Rendering can be slow on CPU. Longer videos need substantial free disk space.
- Do not upload sensitive material to third-party services without permission.
- For reproducibility, scene duration is explicit in the storyboard, not estimated from script text.
