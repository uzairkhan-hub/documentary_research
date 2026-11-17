import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest

from studio import FIELDS, csv_bytes, load, read_storyboard, render, save, store_upload

APP = Path(__file__).with_name('app.py')


def scene(scene_id='001', duration='0.8', asset=''):
    return dict.fromkeys(FIELDS, '') | {
        'scene_id': scene_id, 'duration_sec': duration, 'asset_filename': asset,
        'narration': 'پاکستان، تاریخ\nA "quoted" line',
    }


class ProjectTests(unittest.TestCase):
    def test_storyboard_roundtrip_and_validation(self):
        row = scene()
        self.assertEqual(read_storyboard(csv_bytes([row])), [row])
        for rows in ([], [row, row], [scene(duration='NaN')], [scene(asset='../file.png')]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                read_storyboard(csv_bytes(rows))
        with self.assertRaisesRegex(ValueError, 'column count'):
            read_storyboard((','.join(FIELDS) + '\n001,5').encode())

    def test_uploads_preserve_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            store_upload(folder, 'cover.png', b'old')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                store_upload(folder, 'cover.png', b'new')
            self.assertEqual((folder / 'cover.png').read_bytes(), b'old')

    def test_guided_workflow_with_legacy_project(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            'DOCUMENTARY_STUDIO_PROJECTS': directory,
        }):
            legacy = Path(directory) / 'legacy'
            save(legacy, {'title': 'Existing project', 'minutes': 20, 'notes': 'Brief',
                          'storyboard': [scene()], 'legacy_key': 'keep'})
            app = AppTest.from_file(str(APP), default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.header[0].value, 'Existing project')
            self.assertIn('Existing project', app.code[0].value)

            app.radio[0].set_value(app.radio[0].options[1]).run()
            self.assertFalse(app.exception)
            next(area for area in app.text_area if ':research_dossier:text:' in (area.key or '')).set_value(
                'Research with source URLs'
            )
            next(button for button in app.button if button.label == 'Save research dossier').click().run()
            self.assertIn('Research with source URLs', (legacy / 'research' / 'research_dossier.md').read_text())
            next(area for area in app.text_area if ':script:text:' in (area.key or '')).set_value('پاکستان')
            next(button for button in app.button if button.label == 'Save narration script').click().run()
            self.assertEqual((legacy / 'research' / 'script.md').read_text(encoding='utf-8').strip(), 'پاکستان')
            next(area for area in app.text_area if area.label == 'Or paste CSV').set_value(
                csv_bytes([scene('001'), scene('002')]).decode('utf-8-sig')
            )
            next(button for button in app.button if button.label == 'Import storyboard').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(load(legacy)['storyboard']), 2)
            self.assertEqual(load(legacy)['legacy_key'], 'keep')

            image = legacy / 'assets' / 'cover.png'
            image.parent.mkdir()
            Image.new('RGB', (16, 16)).save(image)
            app.radio[0].set_value(app.radio[0].options[2]).run()
            next(widget for widget in app.selectbox if widget.label == 'Local file').set_value('cover.png')
            next(button for button in app.button if button.label == 'Save scene assignment').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(load(legacy)['storyboard'][0]['asset_filename'], 'cover.png')
            next(widget for widget in app.selectbox if widget.label == 'Review status').set_value('Restricted')
            next(button for button in app.button if button.label == 'Save licence review').click().run()
            app.radio[0].set_value(app.radio[0].options[3]).run()
            self.assertFalse(app.exception)
            self.assertTrue(next(button for button in app.button if button.label == 'Render silent MP4').disabled)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg/FFprobe required')
    def test_render_silent_and_preserve_previous_output_on_failure(self):
        with tempfile.TemporaryDirectory(prefix="studio's ") as directory:
            project = Path(directory)
            assets = project / 'assets'
            assets.mkdir()
            Image.new('RGB', (137, 71), 'green').save(assets / "still's.png")
            subprocess.run([
                'ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=blue:s=160x90:r=15',
                '-f', 'lavfi', '-i', 'sine=frequency=400', '-t', '0.3',
                '-c:v', 'libx264', '-c:a', 'aac', str(assets / 'clip.mp4'),
            ], check=True, timeout=30)
            rows = [scene(asset="still's.png"), scene('002', asset='clip.mp4'), scene('003')]
            progress = []
            output = render(project, rows, lambda done, total, _: progress.append((done, total)))
            probe = subprocess.run([
                'ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(output),
            ], check=True, capture_output=True, timeout=30)
            data = json.loads(probe.stdout)
            self.assertEqual([stream['codec_type'] for stream in data['streams']], ['video'])
            video = data['streams'][0]
            self.assertEqual((video['codec_name'], video['width'], video['height']), ('h264', 1920, 1080))
            self.assertAlmostEqual(float(data['format']['duration']), 2.4, delta=0.04)
            self.assertEqual(progress[-1], (4, 4))
            original = output.read_bytes()
            (assets / 'bad.png').write_bytes(b'invalid')
            with self.assertRaisesRegex(RuntimeError, 'Scene 001'):
                render(project, [scene(asset='bad.png')])
            self.assertEqual(output.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
