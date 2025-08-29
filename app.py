import os, sqlite3, uuid, json
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, g, jsonify
from werkzeug.utils import secure_filename
from pathlib import Path
from utils import extract_text_from_file, compute_top_matches_with_skills, init_db, AVAILABLE_SKILLS

UPLOAD_FOLDER = 'uploads'
DB_PATH = 'data/resumes.db'
ALLOWED_EXT = {'pdf','docx','txt'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
Path('data').mkdir(exist_ok=True)

# Initialize DB and sample resumes
init_db(DB_PATH)

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.route('/', methods=['GET','POST'])
def index():
    if request.method == 'POST':
        file = request.files.get('resume')
        if not file or file.filename == '':
            return render_template('index.html', error='Please select a resume file (PDF/DOCX/TXT).')
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.',1)[1].lower() if '.' in filename else ''
        if ext not in ALLOWED_EXT:
            return render_template('index.html', error='Only PDF, DOCX and TXT files are allowed.')
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        file.save(path)
        # extract text
        text = extract_text_from_file(path)
        # save to DB
        db = get_db()
        cur = db.cursor()
        cur.execute('INSERT INTO resumes(filename, filepath, text) VALUES (?,?,?)', (filename, path, text))
        db.commit()
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    skill_filter = request.args.get('skill','').strip().lower()
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT id, filename, filepath, text FROM resumes ORDER BY id DESC')
    rows = cur.fetchall()
    resumes = [{'id':r[0], 'filename':r[1], 'path':r[2], 'text': r[3] or ''} for r in rows]
    # prepare simple skill counts for dashboard
    skill_counts = {s:0 for s in AVAILABLE_SKILLS}
    for r in resumes:
        text = r['text'].lower()
        for s in AVAILABLE_SKILLS:
            if s in text:
                skill_counts[s] += 1
    # apply skill filter if provided
    if skill_filter:
        resumes = [r for r in resumes if skill_filter in (r['text'] or '').lower()]
    return render_template('dashboard.html', resumes=resumes, skill_counts=skill_counts, skills=AVAILABLE_SKILLS, selected_skill=skill_filter)

@app.route('/match', methods=['GET','POST'])
def match():
    results = []
    stats = {}
    if request.method == 'POST':
        job_text = request.form.get('job_text','').strip()
        if not job_text:
            return render_template('match.html', error='Please enter a job description.')
        # load resumes from DB
        db = get_db()
        cur = db.cursor()
        cur.execute('SELECT id, filename, text FROM resumes')
        rows = cur.fetchall()
        resumes = [{'id':r[0], 'filename':r[1], 'text': r[2] or ''} for r in rows]
        results = compute_top_matches_with_skills(job_text, resumes, top_k=5)
        # build stats for charts
        scores = [r['percent'] for r in results] if results else []
        # category counts for distribution (all resumes)
        cur.execute('SELECT id, text, filename FROM resumes')
        all_rows = cur.fetchall()
        all_res = [{'id':r[0], 'text':r[1] or '', 'filename': r[2]} for r in all_rows]
        from utils import categorize_scores_and_stats
        stats = categorize_scores_and_stats(job_text, all_res)
    return render_template('match.html', results=results, stats=stats)

@app.route('/view/<int:resume_id>')
def view_resume(resume_id):
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT id, filename, text FROM resumes WHERE id=?', (resume_id,))
    row = cur.fetchone()
    if not row:
        return 'Not found', 404
    resume = {'id':row[0], 'filename':row[1], 'text': row[2] or ''}
    # get job_text from query to highlight skills
    job_text = request.args.get('job','').strip()
    from utils import highlight_skills_in_text, extract_skills_from_text
    highlighted = resume['text']
    matched_skills = []
    if job_text:
        jd_skills = extract_skills_from_text(job_text)
        highlighted = highlight_skills_in_text(resume['text'], jd_skills)
        matched_skills = jd_skills
    return render_template('view.html', resume=resume, highlighted=highlighted, matched_skills=matched_skills)

@app.route('/download/<int:resume_id>')
def download(resume_id):
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT filepath, filename FROM resumes WHERE id=?', (resume_id,))
    row = cur.fetchone()
    if not row:
        return 'File not found', 404
    path, filename = row
    directory = os.path.dirname(path)
    return send_from_directory(directory, os.path.basename(path), as_attachment=True, download_name=filename)

if __name__ == '__main__':
    app.run(debug=True)
