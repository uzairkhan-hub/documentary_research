import csv
import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

FIELDS = 'scene_id duration_sec chapter narration visual_direction asset_filename source_url license on_screen_text'.split()
STILLS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
VIDEOS = {'.mp4', '.mov', '.webm', '.mkv'}


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temporary = Path(temp.name)
        try:
            temp.write(content)
            temp.close()
            os.replace(temporary, path)
        finally:
            temp.close()
            temporary.unlink(missing_ok=True)


def load(project):
    data = json.loads((project / 'project.json').read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or not isinstance(data.get('title'), str):
        raise ValueError('Project metadata needs a title.')
    return data


def save(project, data):
    atomic_write(project / 'project.json', json.dumps(data, ensure_ascii=False, indent=2).encode())


def filename(name):
    if (
        not name or name != name.strip() or name.endswith('.')
        or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
        or name in {'.', '..'}
        or re.fullmatch(r'CON|PRN|AUX|NUL|COM[0-9¹²³]|LPT[0-9¹²³]', name.split('.')[0], re.I)
    ):
        raise ValueError(f'Invalid local filename: {name!r}.')
    return name


def store_upload(folder, name, content):
    target = folder / filename(name)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with target.open('xb') as file:
            try:
                file.write(content)
            except OSError:
                file.close()
                target.unlink(missing_ok=True)
                raise
    except FileExistsError:
        raise ValueError(f'{name} already exists. Rename the new file before uploading.') from None


def decode_text(content):
    try:
        return content.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ValueError('Save the file as UTF-8 and try again.') from None


def validate_storyboard(rows):
    if not rows:
        raise ValueError('Add at least one scene.')
    result, ids = [], set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f'Scene {index}: expected a row with named columns.')
        clean = {field: str(row.get(field) or '').strip() for field in FIELDS}
        scene = clean['scene_id']
        if not scene or scene.casefold() in ids:
            raise ValueError(f'Scene {index}: supply a unique scene_id.')
        ids.add(scene.casefold())
        try:
            duration = float(clean['duration_sec'])
        except ValueError:
            duration = 0
        if not math.isfinite(duration) or not 0.5 <= duration <= 900:
            raise ValueError(f'Scene {scene}: duration_sec must be between 0.5 and 900.')
        if clean['asset_filename']:
            try:
                filename(clean['asset_filename'])
            except ValueError as error:
                raise ValueError(f'Scene {scene}: {error}') from error
        result.append(clean)
    return result


def read_storyboard(content):
    try:
        reader = csv.DictReader(io.StringIO(decode_text(content), newline=''), strict=True)
        headers = reader.fieldnames or []
        missing = [field for field in FIELDS if field not in headers]
        if missing:
            raise ValueError('Missing CSV columns: ' + ', '.join(missing))
        if len(headers) != len(set(headers)):
            raise ValueError('CSV contains duplicate column names.')
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'CSV line {reader.line_num}: check the column count and quoting.')
            rows.append(row)
    except csv.Error as error:
        raise ValueError(f'Invalid CSV: {error}') from error
    return validate_storyboard(rows)


def csv_bytes(rows, fields=FIELDS):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode('utf-8-sig')


def prompt(data):
    return f"""Prepare three files for my Enable Pakistan documentary.
Title: {data['title']}
Target duration: {data.get('minutes', 20)} minutes
Brief: {data.get('notes', '')}

1. research_dossier.md: Search the web and consult any references I attach. Give an as-of date, a timeline, and a claim-to-source register with IDs, publisher, date and direct URL. Separate verified, disputed and unconfirmed claims. Prefer primary sources and corroborate material claims independently. Identify gaps rather than inventing citations.
2. script.md: Write Urdu narration with chapter headings and source IDs for factual claims. Keep production notes and source IDs separate from spoken lines.
3. storyboard.csv: Return valid UTF-8 CSV with exactly these headers:
{','.join(FIELDS)}
Use unique scene IDs and durations in seconds (0.5–900 per scene), aiming for the target length. Quote cells containing commas, quotes or newlines. Include the corresponding narration and a practical visual direction or image-generation prompt per scene. Suggest archive, self-created or reusable visuals. Label any AI reconstruction in the visual direction and on_screen_text. Leave asset_filename empty until I choose local files. Fill source_url and license only when the actual asset and its terms can be verified. Do not invent permissions.

Return each file separately. If attachments are unavailable, give three separate code blocks with the complete file contents."""


def asset_path(project, name):
    if not name:
        return None
    folder = project / 'assets'
    path = folder / filename(name)
    if path.is_file() and not path.is_symlink() and path.resolve().parent == folder.resolve():
        return path
    return None


def attribution_rows(project, rows, reviews):
    for row in rows:
        name = row['asset_filename']
        review = reviews.get(name, {})
        yield {
            'scene_id': row['scene_id'],
            'asset_filename': name,
            'availability': 'Available' if asset_path(project, name) else 'Placeholder',
            'status': review.get('status', 'Pending'),
            'creator': review.get('creator', ''),
            'source_url': review.get('source_url') or row['source_url'],
            'license': review.get('license') or row['license'],
            'credit': review.get('credit', ''),
            'notes': review.get('notes', ''),
        }


def render(project, rows, progress=lambda done, total, message: None):
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    rows = validate_storyboard(rows)
    ffmpeg = shutil.which('ffmpeg')
    ffprobe = shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise RuntimeError('Install FFmpeg and make ffmpeg and ffprobe available on PATH, then restart Studio.')

    def run(command, label, timeout):
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                                    errors='replace', timeout=timeout, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f'{label} timed out.') from None
        if result.returncode:
            raise RuntimeError(f'{label} failed. {result.stderr.strip()[-1400:]}')
        return result.stdout

    exports = project / 'exports'
    exports.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.render-', dir=exports) as folder:
        work = Path(folder)
        parts = []
        for index, row in enumerate(rows):
            scene = row['scene_id']
            progress(index, len(rows) + 1, f'Rendering scene {scene}')
            source = asset_path(project, row['asset_filename'])
            still = source is None or source.suffix.lower() in STILLS
            if still:
                image_path = work / 'still.png'
                if source:
                    try:
                        with Image.open(source) as image:
                            ImageOps.exif_transpose(image).convert('RGB').save(image_path)
                    except (OSError, ValueError, Image.DecompressionBombError) as error:
                        raise RuntimeError(f'Scene {scene}: cannot read image {source.name}. {error}') from error
                else:
                    image = Image.new('RGB', (1920, 1080), (14, 18, 27))
                    draw = ImageDraw.Draw(image)
                    font = ImageFont.load_default(size=54)
                    draw.text((100, 450), f'SCENE {index + 1}  |  ADD VISUAL', font=font, fill='white')
                    image.save(image_path)
                source = image_path
                input_args = ['-loop', '1', '-framerate', '25']
            else:
                if source.suffix.lower() not in VIDEOS:
                    raise RuntimeError(f'Scene {scene}: unsupported media type {source.suffix}.')
                stream = json.loads(run([ffprobe, '-v', 'error', '-select_streams', 'V:0',
                                         '-show_entries', 'stream=index', '-of', 'json', str(source)],
                                        f'Scene {scene} video inspection', 30))
                if not stream.get('streams'):
                    raise RuntimeError(f'Scene {scene}: {source.name} has no video stream.')
                input_args = ['-stream_loop', '-1']

            part = f'scene_{index:04d}.mp4'
            frames = max(1, round(float(row['duration_sec']) * 25))
            run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', *input_args,
                 '-i', str(source), '-map', '0:v:0' if still else '0:V:0',
                 '-filter_threads', '2', '-vf',
                 'scale=1920:1080:force_original_aspect_ratio=decrease:force_divisible_by=2,'
                 'pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25,format=yuv420p',
                 '-frames:v', str(frames), '-an', '-sn', '-dn', '-map_metadata', '-1',
                 '-c:v', 'libx264', '-threads', '4', '-preset', 'veryfast', '-crf', '23',
                 str(work / part)], f'Scene {scene} render', max(120, frames / 25 * 12))
            parts.append(part)

        progress(len(rows), len(rows) + 1, 'Joining the silent video')
        playlist = work / 'scenes.txt'
        playlist.write_text(''.join(f"file '{part}'\n" for part in parts), encoding='ascii')
        staged = work / 'rough_cut.mp4'
        run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-f', 'concat',
             '-safe', '1', '-i', str(playlist), '-c', 'copy', '-movflags', '+faststart',
             str(staged)], 'Joining scenes', max(120, sum(float(row['duration_sec']) for row in rows)))
        output = exports / 'silent_rough_cut.mp4'
        os.replace(staged, output)
        progress(len(rows) + 1, len(rows) + 1, 'Silent rough cut ready')
        return output
