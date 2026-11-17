import csv, io, json, re, shutil, subprocess, tempfile, uuid
from pathlib import Path
import streamlit as st

ROOT=Path(__file__).resolve().parent
PROJECTS=ROOT/'projects'; PROJECTS.mkdir(exist_ok=True)
FIELDS=['scene_id','duration_sec','chapter','narration','visual_direction','asset_filename','source_url','license','on_screen_text']

def slugify(s):
    return re.sub(r'[^a-z0-9-]+','-',s.lower().strip().replace(' ','-')).strip('-')[:55] or 'documentary'

def load(p): return json.loads((p/'project.json').read_text(encoding='utf-8'))
def save(p,obj): (p/'project.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def safe_name(n): return Path(n).name.replace('\\','_')
def csv_bytes(rows):
    out=io.StringIO(); w=csv.DictWriter(out,fieldnames=FIELDS); w.writeheader(); w.writerows([{k:r.get(k,'') for k in FIELDS} for r in rows]); return out.getvalue().encode('utf-8-sig')
def make_placeholder(path, text):
    from PIL import Image, ImageDraw, ImageFont
    im=Image.new('RGB',(1920,1080),(14,18,27)); d=ImageDraw.Draw(im)
    font=ImageFont.truetype('arial.ttf',55) if Path('C:/Windows/Fonts/arial.ttf').exists() else ImageFont.load_default()
    d.text((100,420),'ENABLE PAKISTAN',fill=(245,245,245),font=font)
    d.text((100,520),text[:55],fill=(210,195,150),font=font)
    im.save(path)
def render(p, rows):
    ffmpeg=shutil.which('ffmpeg'); ffprobe=shutil.which('ffprobe')
    if not ffmpeg or not ffprobe: raise RuntimeError('FFmpeg/ffprobe missing from PATH. Install FFmpeg and restart Studio.')
    if not rows: raise RuntimeError('Import a storyboard first.')
    outputs=p/'exports'; outputs.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ep_render_') as tmp:
        tmp=Path(tmp); parts=[]
        for i,row in enumerate(rows):
            try: duration=float(row['duration_sec'])
            except (ValueError,KeyError): raise RuntimeError(f'Invalid duration in scene {i+1}')
            if not 0.5 <= duration <= 900: raise RuntimeError(f'Scene {i+1}: duration must be 0.5–900 seconds')
            name=safe_name(row.get('asset_filename','')) if row.get('asset_filename') else ''
            asset=p/'assets'/name if name else None
            if not asset or not asset.is_file():
                asset=tmp/f'placeholder_{i:03d}.png'; make_placeholder(asset,f'SCENE {i+1} - ADD VISUAL')
            target=tmp/f'scene_{i:04d}.mp4'
            still=asset.suffix.lower() in {'.png','.jpg','.jpeg','.webp','.bmp'}
            if still:
                cmd=[ffmpeg,'-y','-loop','1','-framerate','25','-i',str(asset)]
            else:
                cmd=[ffmpeg,'-y','-stream_loop','-1','-i',str(asset)]
            cmd+=['-t',str(duration),'-vf','scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25,format=yuv420p','-an','-c:v','libx264','-preset','veryfast','-crf','23','-movflags','+faststart',str(target)]
            result=subprocess.run(cmd,capture_output=True,text=True)
            if result.returncode: raise RuntimeError(f'Scene {i+1} render failed: {result.stderr[-1000:]}')
            parts.append(target)
        concat=tmp/'list.txt'
        concat.write_text(''.join("file '"+str(part).replace('\\','/')+"'\n" for part in parts),encoding='utf-8')
        output=outputs/'silent_rough_cut.mp4'
        result=subprocess.run([ffmpeg,'-y','-f','concat','-safe','0','-i',str(concat),'-c','copy','-movflags','+faststart',str(output)],capture_output=True,text=True)
        if result.returncode: raise RuntimeError('Concatenation failed: '+result.stderr[-1000:])
        return output

st.set_page_config(page_title='Enable Pakistan Documentary Studio',page_icon='🎬',layout='wide')
st.title('🎬 Enable Pakistan Documentary Studio')
st.caption('Free local project manager + silent rough-cut renderer. Research and AI image creation happen in ChatGPT, not automatically inside this app.')
with st.expander('1 · Create a documentary project',expanded=not any(PROJECTS.iterdir())):
    with st.form('new_project'):
        title=st.text_input('Documentary title',placeholder='The Story of Tarbela Dam')
        minutes=st.number_input('Target length (minutes)',min_value=1,max_value=60,value=20)
        notes=st.text_area('Your research notes / topic brief')
        if st.form_submit_button('Create project'):
            if not title.strip(): st.error('Enter a title.')
            else:
                p=PROJECTS/(slugify(title)+'-'+uuid.uuid4().hex[:6]); (p/'assets').mkdir(parents=True)
                (p/'references').mkdir(); (p/'exports').mkdir()
                save(p,{'title':title,'minutes':minutes,'notes':notes,'storyboard':[]})
                st.success('Project created. Select it below.')
options=sorted([x for x in PROJECTS.iterdir() if (x/'project.json').is_file()])
if not options: st.info('Create a project to begin.'); st.stop()
selected=st.selectbox('Project',options,format_func=lambda p:load(p)['title']); data=load(selected)
tabs=st.tabs(['Research materials','Script & storyboard','Visual assets','Render & export'])
with tabs[0]:
    st.subheader('Research intake')
    notes=st.text_area('Topic and research notes',value=data.get('notes',''),height=180)
    if st.button('Save research notes'):
        data['notes']=notes; save(selected,data); st.success('Saved locally.')
    files=st.file_uploader('Attach documents and source material',accept_multiple_files=True,key='refs')
    if st.button('Save reference uploads'):
        for f in files or []:
            (selected/'references'/safe_name(f.name)).write_bytes(f.getbuffer())
        st.success(f'Saved {len(files or [])} files.')
    st.write('Stored references:',*[p.name for p in sorted((selected/'references').iterdir())])
    prompt=f'''Research this documentary thoroughly using authoritative primary and independent sources. Topic: {data['title']}. Target duration: {data['minutes']} minutes. User notes: {data.get('notes','')}. Distinguish verified, disputed and unconfirmed claims. Provide source URLs, a dated research dossier, a compelling Urdu narration script, and a scene-by-scene storyboard CSV with these exact columns: {', '.join(FIELDS)}. Use seconds for duration_sec; asset_filename should initially be blank. Do not invent archival footage or copyright permissions. I will attach additional source documents separately.'''
    st.text_area('Copy this into ChatGPT with your source files',prompt,height=220)
with tabs[1]:
    st.subheader('Import your ChatGPT storyboard')
    example=[{'scene_id':'001','duration_sec':'8','chapter':'Opening','narration':'Narration will be recorded later','visual_direction':'Aerial establishing shot','asset_filename':'','source_url':'','license':'','on_screen_text':''}]
    st.download_button('Download storyboard CSV template',csv_bytes(example),'storyboard_template.csv','text/csv')
    uploaded=st.file_uploader('Upload storyboard CSV',type=['csv'])
    if uploaded and st.button('Import storyboard'):
        content=uploaded.getvalue().decode('utf-8-sig')
        reader=csv.DictReader(io.StringIO(content))
        if not set(FIELDS).issubset(set(reader.fieldnames or [])): st.error('Missing required columns: '+', '.join(set(FIELDS)-set(reader.fieldnames or [])))
        else:
            rows=list(reader)
            try:
                for row in rows:
                    d=float(row['duration_sec']); assert 0.5<=d<=900
                data['storyboard']=[{k:r.get(k,'') for k in FIELDS} for r in rows];save(selected,data);st.success(f'Imported {len(rows)} scenes.');st.rerun()
            except (ValueError,AssertionError,TypeError): st.error('All scene durations must be numbers between 0.5 and 900 seconds.')
    rows=data.get('storyboard',[])
    if rows:
        st.write(f"**{len(rows)} scenes · {sum(float(r['duration_sec']) for r in rows)/60:.1f} minutes**")
        edited=st.data_editor(rows,num_rows='dynamic',use_container_width=True)
        if st.button('Save storyboard changes'):
            data['storyboard']=edited;save(selected,data);st.success('Saved.')
        st.download_button('Export current saved storyboard',csv_bytes(rows),'storyboard.csv','text/csv')
with tabs[2]:
    st.subheader('Visual library')
    assets=st.file_uploader('Upload approved visuals (JPG, PNG, MP4, MOV, WEBM)',accept_multiple_files=True,type=['jpg','jpeg','png','webp','bmp','mp4','mov','webm'],key='assets')
    if st.button('Save visual assets'):
        for f in assets or []: (selected/'assets'/safe_name(f.name)).write_bytes(f.getbuffer())
        st.success(f'Saved {len(assets or [])} assets.')
    st.write('Available assets:',*[p.name for p in sorted((selected/'assets').iterdir())])
    st.info('Set each scene’s asset_filename in the storyboard to exactly match an uploaded filename. Record the source URL and licence for every asset.')
with tabs[3]:
    st.subheader('Silent documentary preview')
    st.write('Render is CPU-compatible and uses FFmpeg. Missing footage appears as labelled placeholders. No narration or music is added.')
    st.write('FFmpeg status:', 'Available' if shutil.which('ffmpeg') else 'Not found — install FFmpeg and restart')
    if st.button('Render silent 1080p MP4',type='primary'):
        with st.spinner('Rendering scenes — longer projects can take considerable time...'):
            try:
                path=render(selected,data.get('storyboard',[])); st.success(f'Rendered: {path}')
            except Exception as e: st.error(str(e))
    output=selected/'exports'/'silent_rough_cut.mp4'
    if output.exists():
        st.video(str(output))
        st.caption(f'Output saved locally: {output}')
        st.download_button('Download MP4',output.read_bytes(),'enable_pakistan_silent_rough_cut.mp4','video/mp4')
