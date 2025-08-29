import os, sqlite3, re, json
from typing import List, Dict
from pdfminer.high_level import extract_text as pdf_extract_text
import docx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# A small, editable set of skills to look for
AVAILABLE_SKILLS = ['python','django','flask','java','c++','c','javascript','react','angular','html','css','mysql','mongodb','sql','aws','docker','kubernetes','linux','machine learning','data science','tensorflow','pytorch','nlp','php','.net']

def init_db(db_path='data/resumes.db'):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS resumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            filepath TEXT,
            text TEXT
        )
    ''')
    conn.commit()
    # If empty, insert sample resumes for demo
    cur.execute('SELECT COUNT(*) FROM resumes')
    count = cur.fetchone()[0]
    if count == 0:
        samples = [
            ('rahul_sharma.pdf', 'samples/rahul_sharma.txt', '''Rahul Sharma\nEmail: rahul.sharma@example.com\nSkills: Python, Java, C++, HTML, CSS, JavaScript, React, MySQL, Machine Learning, Data Analysis\nProjects: Online Bookstore (MERN), Fake News Detection (ML)'''),
            ('anita_verma.pdf', 'samples/anita_verma.txt', '''Anita Verma\nEmail: anita.verma@example.com\nSkills: Python, Flask, SQL, AWS, Docker, NLP, TensorFlow\nProjects: Chatbot with NLP, Sentiment Analysis'''),
            ('vikram_patel.pdf', 'samples/vikram_patel.txt', '''Vikram Patel\nEmail: vikram.patel@example.com\nSkills: Java, Spring Boot, MySQL, Kubernetes, Linux\nProjects: E-commerce Backend, Order Management System''')
        ]
        for fn, path, text in samples:
            cur.execute('INSERT INTO resumes(filename, filepath, text) VALUES (?,?,?)', (fn, path, text))
        conn.commit()
    conn.close()

def extract_text_from_file(path: str) -> str:
    path = str(path)
    ext = path.rsplit('.',1)[1].lower() if '.' in path else ''
    try:
        if ext == 'pdf':
            text = pdf_extract_text(path)
        elif ext == 'docx':
            doc = docx.Document(path)
            paragraphs = [p.text for p in doc.paragraphs]
            text = '\n'.join(paragraphs)
        elif ext == 'txt':
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        else:
            text = ''
    except Exception as e:
        text = ''
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_skills_from_text(text: str) -> List[str]:
    text = (text or '').lower()
    found = []
    for skill in AVAILABLE_SKILLS:
        if skill in text:
            found.append(skill)
    return found

def highlight_skills_in_text(text: str, skills: List[str]) -> str:
    if not text:
        return ''
    highlighted = text
    for s in skills:
        # simple case-insensitive replace with <mark>
        regex = re.compile(re.escape(s), re.IGNORECASE)
        highlighted = regex.sub(lambda m: f"<mark>{m.group(0)}</mark>", highlighted)
    # preserve line breaks
    highlighted = highlighted.replace('\n','<br>')
    return highlighted

def compute_top_matches_with_skills(job_text: str, resumes: List[Dict], top_k: int=5):
    docs = [job_text] + [r['text'] for r in resumes]
    if len(resumes) == 0:
        return []
    vectorizer = TfidfVectorizer(stop_words='english', max_features=5000)
    X = vectorizer.fit_transform(docs)
    job_vec = X[0]
    resume_vecs = X[1:]
    sims = cosine_similarity(job_vec, resume_vecs)[0]
    results = []
    for idx, score in enumerate(sims):
        r = resumes[idx]
        skills = extract_skills_from_text(r['text'])
        results.append({
            'id': r['id'],
            'filename': r['filename'],
            'score': float(score),
            'percent': round(float(score)*100,2),
            'skills': skills
        })
    results = sorted(results, key=lambda x: x['score'], reverse=True)[:top_k]
    # add category labels
    for r in results:
        p = r['percent']
        if p >= 80:
            r['category'] = 'Strong'
        elif p >= 50:
            r['category'] = 'Medium'
        else:
            r['category'] = 'Low'
    return results

def categorize_scores_and_stats(job_text: str, resumes: List[Dict]):
    # compute scores for all resumes to provide distribution stats
    docs = [job_text] + [r['text'] for r in resumes]
    vectorizer = TfidfVectorizer(stop_words='english', max_features=5000)
    X = vectorizer.fit_transform(docs)
    job_vec = X[0]
    resume_vecs = X[1:]
    sims = cosine_similarity(job_vec, resume_vecs)[0]
    cats = {'Strong':0, 'Medium':0, 'Low':0}
    percents = []
    for score in sims:
        p = round(float(score)*100,2)
        percents.append(p)
        if p >= 80:
            cats['Strong'] += 1
        elif p >=50:
            cats['Medium'] += 1
        else:
            cats['Low'] += 1
    # skill coverage
    skill_counts = {}
    for s in AVAILABLE_SKILLS:
        count = 0
        for r in resumes:
            if s in (r['text'] or '').lower():
                count += 1
        skill_counts[s] = count
    return {'categories':cats, 'percents':percents, 'skill_counts':skill_counts}
