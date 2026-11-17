import hashlib
import os
import re
import shutil
import uuid
from pathlib import Path

import streamlit as st

from studio import (
    FIELDS, STILLS, VIDEOS, atomic_write, attribution_rows, csv_bytes, decode_text,
    load, prompt, read_storyboard, render, save, store_upload, validate_storyboard,
)

ROOT = Path(__file__).resolve().parent
PROJECTS = Path(os.environ.get('DOCUMENTARY_STUDIO_PROJECTS') or ROOT / 'projects').resolve()
STEPS = ('1. Brief and ChatGPT', '2. Import results', '3. Visuals and rights', '4. Render and export')
DOCUMENTS = {'research_dossier': 'Research dossier', 'script': 'Narration script'}
REVIEW_STATES = ('Pending', 'Cleared', 'Restricted')
FILE_ERRORS = (OSError, ValueError, RuntimeError)


def notify(message):
    st.session_state['notice'] = message
    st.rerun()


def update(project, message, **changes):
    latest = load(project)
    latest.update(changes)
    save(project, latest)
    notify(message)


def upload_files(label, folder, key, types=None):
    uploads = st.file_uploader(label, type=types, accept_multiple_files=True, key=key)
    if st.button('Save uploads', key=f'{key}:save', disabled=not uploads):
        saved = 0
        for upload in uploads:
            try:
                store_upload(folder, upload.name, upload.getbuffer())
                saved += 1
            except FILE_ERRORS as error:
                st.error(str(error))
        if saved:
            st.success(f'Saved {saved} file(s).')
    return sorted(path.name for path in folder.iterdir() if path.is_file()) if folder.is_dir() else []


def brief_step(project, data):
    with st.form(f'{project}:brief'):
        minutes = st.number_input('Target length in minutes', min_value=1, max_value=60,
                                  value=data.get('minutes', 20))
        notes = st.text_area('Topic description, angle and research notes', data.get('notes', ''), height=140)
        if st.form_submit_button('Save brief'):
            update(project, 'Brief saved.', notes=notes, minutes=minutes)

    references = upload_files('Attach local reference files', project / 'references', f'{project}:references')
    if references:
        st.write('Saved references · ' + ', '.join(references))

    st.subheader('Take your brief to ChatGPT')
    st.write('Open ChatGPT, paste the prompt, and attach the relevant reference files there. Bring the three results back in step 2.')
    text = prompt(data)
    st.code(text, language=None, wrap_lines=True)
    st.download_button('Download ChatGPT prompt', text, 'chatgpt_documentary_prompt.txt', 'text/plain')
    st.link_button('Open ChatGPT', 'https://chatgpt.com/')


def import_documents(project):
    for name, label in DOCUMENTS.items():
        path = project / 'research' / f'{name}.md'
        saved = decode_text(path.read_bytes()) if path.is_file() else ''
        revision = hashlib.sha256(saved.encode()).hexdigest()[:12]
        with st.expander(label, expanded=not saved):
            with st.form(f'{project}:{name}:{revision}'):
                upload = st.file_uploader(f'Upload {label.lower()}', type=['md', 'txt'])
                pasted = st.text_area('Or paste or edit the text', saved, height=170,
                                      key=f'{project}:{name}:text:{revision}')
                if st.form_submit_button(f'Save {label.lower()}'):
                    text = (decode_text(upload.getvalue()) if upload else pasted).strip()
                    if not text:
                        st.error('Add text or upload a non-empty UTF-8 file.')
                    else:
                        atomic_write(path, (text + '\n').encode())
                        notify(f'{label} saved.')
            if saved:
                st.download_button(f'Download {label.lower()}', saved, path.name, 'text/markdown')


def storyboard_step(project, raw_rows):
    import_documents(project)
    st.subheader('Storyboard')
    example = dict.fromkeys(FIELDS, '')
    example.update(scene_id='001', duration_sec='8', chapter='Opening',
                   narration='Opening narration', visual_direction='Wide establishing shot')
    st.download_button('Download CSV template', csv_bytes([example]), 'storyboard_template.csv', 'text/csv')
    with st.form(f'{project}:csv'):
        upload = st.file_uploader('Upload storyboard CSV', type=['csv'])
        pasted = st.text_area('Or paste CSV', placeholder=','.join(FIELDS))
        if st.form_submit_button('Import storyboard'):
            if not upload and not pasted.strip():
                st.error('Upload or paste the storyboard CSV.')
            else:
                rows = read_storyboard(upload.getvalue() if upload else pasted.strip().encode())
                update(project, f'Imported {len(rows)} scenes.', storyboard=rows)

    if raw_rows:
        revision = hashlib.sha256(repr(raw_rows).encode()).hexdigest()[:12]
        with st.form(f'{project}:scene-edit:{revision}'):
            edited = st.data_editor(
                [{field: str(row.get(field) or '') for field in FIELDS} for row in raw_rows],
                num_rows='dynamic', hide_index=True,
                column_config={field: st.column_config.TextColumn(field) for field in FIELDS},
            )
            if st.form_submit_button('Save storyboard edits'):
                rows = validate_storyboard(edited)
                update(project, 'Storyboard updated.', storyboard=rows)
        st.download_button('Export saved storyboard', csv_bytes(raw_rows), 'storyboard.csv', 'text/csv')


def visuals_step(project, rows, reviews):
    assets = upload_files('Upload still images or video clips', project / 'assets', f'{project}:assets',
                          sorted(extension[1:] for extension in STILLS | VIDEOS))
    if not assets:
        st.info('Upload a local file before assigning or reviewing it.')
        return

    if rows:
        with st.expander('Assign a visual to a scene', expanded=True):
            scene = st.selectbox('Scene', rows, format_func=lambda row: f"{row['scene_id']} · {row['chapter']}",
                                 key=f'{project}:scene')
            if scene['visual_direction']:
                st.caption('Visual direction from the storyboard')
                st.code(scene['visual_direction'], language=None, wrap_lines=True)
            current = scene['asset_filename']
            choices = list(dict.fromkeys(['', *assets, current]))
            with st.form(f"{project}:assign:{scene['scene_id']}:{current}"):
                asset = st.selectbox('Local file', choices, index=choices.index(current),
                                     format_func=lambda name: name or 'Placeholder')
                if st.form_submit_button('Save scene assignment'):
                    updated = [{**row, 'asset_filename': asset} if row == scene else row for row in rows]
                    # Legacy scene URLs and licences refer to the previous visual.
                    if asset != current:
                        updated[rows.index(scene)].update(source_url='', license='')
                    update(project, 'Scene assignment saved.', storyboard=updated)

    st.subheader('Attribution and licence review')
    asset = st.selectbox('Visual to review', assets, key=f'{project}:review-asset')
    review = reviews.get(asset, {})
    scene = next((row for row in rows if row['asset_filename'] == asset), {})
    with st.form(f'{project}:review:{asset}'):
        source = st.text_input('Source URL or origin', review.get('source_url') or scene.get('source_url', ''))
        creator = st.text_input('Creator or rights holder', review.get('creator', ''))
        license_text = st.text_input('Licence or permission terms', review.get('license') or scene.get('license', ''))
        credit = st.text_input('Required attribution', review.get('credit', ''))
        notes = st.text_area('Restrictions or review notes', review.get('notes', ''))
        status = st.selectbox('Review status', REVIEW_STATES, index=REVIEW_STATES.index(review.get('status', 'Pending')))
        if st.form_submit_button('Save licence review'):
            if status == 'Cleared' and not all(value.strip() for value in (source, creator, license_text)):
                st.error('To clear an asset, record its origin, creator and licence or permission terms.')
            else:
                entry = dict(source_url=source.strip(), creator=creator.strip(), license=license_text.strip(),
                             credit=credit.strip(), notes=notes.strip(), status=status)
                latest = load(project).get('media_reviews', {})
                update(project, 'Licence review saved.', media_reviews={**latest, asset: entry})


def render_step(project, rows, register, output):
    tools_ready = bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))
    if not tools_ready:
        st.warning('FFmpeg and FFprobe are required for rendering. Install them, add them to PATH and restart Studio.')
    if not rows:
        st.info('Import or repair the storyboard to enable rendering.')

    available = [row for row in register if row['availability'] == 'Available']
    pending = [row for row in available if row['status'] == 'Pending']
    restricted = [row for row in available if row['status'] == 'Restricted']
    placeholders = len(register) - len(available)
    if placeholders:
        st.warning(f'{placeholders} scene(s) will use labelled placeholders.')
    if restricted:
        st.error('Resolve the licence review or replace these restricted visuals before rendering: '
                 + ', '.join(sorted({row['asset_filename'] for row in restricted})))
    allow_preview = not pending or st.checkbox(
        f'Include {len(pending)} scene(s) with pending rights in a private preview',
        key=f'{project}:pending-preview',
    )

    if register:
        st.subheader('Current storyboard attribution')
        st.dataframe(register, hide_index=True)
        st.download_button('Export attribution register', csv_bytes(register, list(register[0])),
                           'visual_attribution.csv', 'text/csv')
    st.caption('Renders a 1080p, 25 fps MP4 without an audio track. Narration and on-screen text stay in the storyboard for finishing.')
    if st.button('Render silent MP4', type='primary',
                 disabled=not (rows and tools_ready and not restricted and allow_preview)):
        bar = st.progress(0, 'Preparing render')

        def update_progress(done, total, message):
            bar.progress(done / total, message)

        try:
            render(project, rows, update_progress)
            st.success('Silent MP4 saved.')
        except FILE_ERRORS as error:
            st.error(str(error))

    if output.is_file():
        st.subheader('Last successful render')
        st.caption(str(output))
        if st.checkbox('Load video preview and download', key=f'{project}:load-video'):
            st.video(str(output))
            with output.open('rb') as video:
                st.download_button('Download MP4', video, output.name, 'video/mp4', on_click='ignore')


def main():
    st.set_page_config(page_title='Enable Pakistan Documentary Studio', page_icon='🎬', layout='wide')
    st.title('Enable Pakistan Documentary Studio')
    st.caption('Research and draft in ChatGPT. Assemble and render the silent rough cut on this computer.')
    PROJECTS.mkdir(parents=True, exist_ok=True)
    projects = {}
    for path in sorted(PROJECTS.iterdir()):
        if (path / 'project.json').is_file():
            try:
                projects[path] = load(path)
            except FILE_ERRORS as error:
                st.warning(f'Could not open {path.name}. {error}')

    with st.sidebar:
        with st.expander('Create a project', expanded=not projects):
            with st.form('new_project'):
                title = st.text_input('Documentary title')
                minutes = st.number_input('Target length (minutes)', min_value=1, max_value=60, value=20)
                notes = st.text_area('Topic description')
                if st.form_submit_button('Create project'):
                    if not title.strip():
                        st.error('Enter a documentary title.')
                    else:
                        slug = re.sub(r'[^a-z0-9-]+', '-', title.lower()).strip('-')[:55] or 'documentary'
                        path = PROJECTS / f'{slug}-{uuid.uuid4().hex[:8]}'
                        save(path, dict(title=title.strip(), minutes=minutes, notes=notes, storyboard=[]))
                        st.session_state['project'] = path
                        notify('Project created.')
        if not projects:
            return
        project = st.selectbox('Project', list(projects),
                               format_func=lambda path: projects[path]['title'], key='project')
        step = st.radio('Workflow', STEPS, key=f'{project}:step')

    data = projects[project]
    notice = st.session_state.pop('notice', None)
    if notice:
        st.success(notice)
    st.header(data['title'])
    raw_rows = data.get('storyboard', [])
    try:
        rows = validate_storyboard(raw_rows) if raw_rows else []
    except ValueError as error:
        rows = []
        st.warning(f'Open step 2 to repair the saved storyboard. {error}')
    reviews = data.get('media_reviews', {})
    register = list(attribution_rows(project, rows, reviews))
    ready = sum(row['availability'] == 'Available' and row['status'] == 'Cleared' for row in register)
    dossier = (project / 'research' / 'research_dossier.md').is_file()
    script = (project / 'research' / 'script.md').is_file()
    output = project / 'exports' / 'silent_rough_cut.mp4'
    st.caption(
        f"Research {'saved' if dossier else 'needed'} · Script {'saved' if script else 'needed'}"
        f" · {len(rows)} scenes · {ready}/{len(rows)} scenes with cleared visuals"
        f" · {'Prior MP4 available' if output.is_file() else 'Awaiting first render'}"
    )
    if rows:
        total = sum(float(row['duration_sec']) for row in rows) / 60
        st.caption(f"Storyboard {total:.1f} min · Project target {data.get('minutes', 20)} min")

    if step == STEPS[0]:
        brief_step(project, data)
    elif step == STEPS[1]:
        storyboard_step(project, raw_rows)
    elif step == STEPS[2]:
        visuals_step(project, rows, reviews)
    else:
        render_step(project, rows, register, output)


if __name__ == '__main__':
    try:
        main()
    except FILE_ERRORS as error:
        st.error(str(error))
