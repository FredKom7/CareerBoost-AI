import json
import io
import os
import pdfplumber
from google import genai
from google.genai import types
from openai import OpenAI
from flask import Flask, render_template, request, session, flash, redirect, url_for, Response
from dotenv import load_dotenv

# Load environment variables from .env file (if present)
load_dotenv()

app = Flask(__name__)
app.secret_key = 'career_boost_secret_key' # For session management

# Register Blueprints
from routes.chatbot import chatbot_bp
app.register_blueprint(chatbot_bp)

# --- OPENAI & GEMINI DYNAMIC CLIENT RETRIEVALS ---

def get_openai_client():
    # 1. Check session first
    try:
        session_key = session.get('openai_api_key')
        if session_key:
            return OpenAI(api_key=session_key)
    except Exception:
        pass
    # 2. Check environment variable
    env_key = os.environ.get("OPENAI_API_KEY")
    if env_key:
        try:
            return OpenAI(api_key=env_key)
        except Exception:
            pass
    return None

def get_gemini_client():
    # 1. Check session first
    try:
        session_key = session.get('gemini_api_key')
        if session_key:
            return genai.Client(api_key=session_key)
    except Exception:
        pass
    # 2. Check environment variable
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key:
        try:
            return genai.Client(api_key=env_key)
        except Exception:
            pass
    return None

# --- OFFLINE/FALLBACK SYNONYMS DICTIONARY ---
SKILL_ALIASES = {
    "Python": ["python", "py"],
    "Data Structures": ["data structure", "data structures", "ds", "array", "linked list", "tree", "graph", "stack", "queue"],
    "Algorithms": ["algorithm", "algorithms", "sorting", "searching", "dp", "dynamic programming", "recursion"],
    "System Design": ["system design", "hld", "lld", "scalability", "architecture", "microservices", "distributed systems"],
    "Java": ["java", "jvm", "spring", "springboot"],
    "AWS": ["aws", "amazon web services", "cloud", "ec2", "s3", "rds", "lambda"],
    "SQL": ["sql", "mysql", "postgresql", "database", "rdbms", "queries"],
    "Communication": ["communication", "teamwork", "leadership", "collaboration", "presentation"],
    "React": ["react", "reactjs", "react.js", "frontend", "javascript", "js", "html", "css"],
    "Machine Learning": ["machine learning", "ml", "ai", "deep learning", "nlp", "pytorch", "tensorflow"]
}

# HOME PAGE
@app.route('/')
def home():
    return render_template('index.html')


# UPLOAD + ANALYSIS
@app.route('/upload', methods=['POST'])
def upload():
    try:
        if 'resume' not in request.files:
            flash("No resume file uploaded.")
            return redirect(url_for('home'))
            
        file = request.files['resume']
        company = request.form.get('company', 'Google')

        if file.filename == '':
            flash("No selected file.")
            return redirect(url_for('home'))

        text = ""
        # EXTRACT PDF TEXT SAFELY
        try:
            pdf_bytes = io.BytesIO(file.read())
            with pdfplumber.open(pdf_bytes) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            flash(f"Error reading PDF: {str(e)}")
            return redirect(url_for('home'))

        if not text.strip():
            flash("Could not extract text from the PDF. It might be empty or scanned.")
            return redirect(url_for('home'))

        text_lower = text.lower()

        # LOAD DATA SAFELY
        try:
            with open('data/companies.json', 'r', encoding='utf-8') as f:
                companies = json.load(f)
            with open('data/interview_questions.json', 'r', encoding='utf-8') as f:
                interview_data = json.load(f)
        except Exception as e:
            flash(f"Data configuration error: {str(e)}")
            return redirect(url_for('home'))

        # GET COMPANY SKILLS
        company_skills = companies.get(company, {}).get('skills', [])
        
        matched_skills = []
        missing_skills = []
        score = 0
        strengths = []
        weaknesses = []
        
        ai_success = False
        
        # 1. OPENAI INTEGRATION
        openai_client = get_openai_client()
        if openai_client:
            try:
                # Prompt OpenAI for semantic evaluation, strengths, weaknesses, and structured JSON output
                prompt = (
                    f"Evaluate this resume text against the required skills for target company '{company}'.\n"
                    f"Required skills list: {json.dumps(company_skills)}\n\n"
                    f"Resume Text:\n{text}\n\n"
                    f"Analyze whether the candidate demonstrates proficiency in each required skill. "
                    f"Be intelligent: recognize synonyms, acronyms, abbreviations, and related technology context "
                    f"(e.g., 'PostgreSQL' matches 'SQL' or 'Databases', 'ReactJS' matches 'React').\n"
                    f"Also analyze the resume text to identify key strengths (e.g. quantifiable impact, strong formatting) and weaknesses (e.g. spelling issues, missing keywords).\n\n"
                    f"Return ONLY a valid JSON object matching this schema:\n"
                    f"{{\n"
                    f"  \"matched_skills\": [\"Skill1\", \"Skill2\"],\n"
                    f"  \"missing_skills\": [\"Skill3\", \"Skill4\"],\n"
                    f"  \"ats_score\": 75,\n"
                    f"  \"strengths\": [\"Strength 1\", \"Strength 2\"],\n"
                    f"  \"weaknesses\": [\"Weakness 1\", \"Weakness 2\"]\n"
                    f"}}\n"
                    f"Do not include any markdown styling like ```json, other text, or explanation."
                )
                
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    response_format={ "type": "json_object" },
                    messages=[
                        {"role": "system", "content": "You are a resume analyzer that outputs structured JSON."},
                        {"role": "user", "content": prompt}
                    ]
                )
                
                response_text = (response.choices[0].message.content or "").strip()
                res_data = json.loads(response_text)
                matched_skills = res_data.get("matched_skills", [])
                missing_skills = res_data.get("missing_skills", [])
                score = int(res_data.get("ats_score", 0))
                strengths = res_data.get("strengths", [])
                weaknesses = res_data.get("weaknesses", [])
                ai_success = True
                print("[INFO] Semantic skill matching completed via OpenAI ChatGPT.")
            except Exception as e:
                print(f"[ERROR] OpenAI skill matching failed: {str(e)}. Falling back to Gemini.")
                ai_success = False

        # 2. GEMINI FALLBACK
        client = get_gemini_client()
        if not ai_success and client:
            try:
                # Prompt Gemini for semantic evaluation, strengths, weaknesses, and structured JSON output
                prompt = (
                    f"Evaluate this resume text against the required skills for target company '{company}'.\n"
                    f"Required skills list: {json.dumps(company_skills)}\n\n"
                    f"Resume Text:\n{text}\n\n"
                    f"Analyze whether the candidate demonstrates proficiency in each required skill. "
                    f"Be intelligent: recognize synonyms, acronyms, abbreviations, and related technology context "
                    f"(e.g., 'PostgreSQL' matches 'SQL' or 'Databases', 'ReactJS' matches 'React').\n"
                    f"Also analyze the resume text to identify key strengths (e.g. quantifiable impact, strong formatting) and weaknesses (e.g. spelling issues, missing keywords).\n\n"
                    f"Return ONLY a valid JSON object matching this schema:\n"
                    f"{{\n"
                    f"  \"matched_skills\": [\"Skill1\", \"Skill2\"],\n"
                    f"  \"missing_skills\": [\"Skill3\", \"Skill4\"],\n"
                    f"  \"ats_score\": 75,\n"
                    f"  \"strengths\": [\"Strength 1\", \"Strength 2\"],\n"
                    f"  \"weaknesses\": [\"Weakness 1\", \"Weakness 2\"]\n"
                    f"}}\n"
                    f"Do not include any markdown styling like ```json, other text, or explanation."
                )
                
                response = client.models.generate_content(
                    model='gemini-1.5-flash',
                    contents=prompt
                )
                
                response_text = (response.text or "").strip()
                # Clean up any potential markdown code blocks
                if response_text.startswith("```"):
                    lines = response_text.splitlines()
                    if len(lines) >= 2:
                        start = 1 if "json" in lines[0] or "JSON" in lines[0] else 0
                        end = -1 if lines[-1].startswith("```") else len(lines)
                        response_text = "\n".join(lines[start:end]).strip()
                
                res_data = json.loads(response_text)
                matched_skills = res_data.get("matched_skills", [])
                missing_skills = res_data.get("missing_skills", [])
                score = int(res_data.get("ats_score", 0))
                strengths = res_data.get("strengths", [])
                weaknesses = res_data.get("weaknesses", [])
                ai_success = True
                print("[INFO] Semantic skill matching completed via Gemini.")
            except Exception as e:
                print(f"[ERROR] Gemini skill matching failed: {str(e)}. Falling back to character-substring matcher.")
                ai_success = False

        # 3. LOCAL SYNONYMS FALLBACK
        if not ai_success:
            matched_skills = []
            missing_skills = []
            for skill in company_skills:
                aliases = SKILL_ALIASES.get(skill, [skill])
                matched = False
                for alias in aliases:
                    if alias.lower() in text_lower:
                        matched = True
                        break
                if matched:
                    matched_skills.append(skill)
                else:
                    missing_skills.append(skill)
            
            score = 0
            if company_skills:
                score = int((len(matched_skills) / len(company_skills)) * 100)
            
            strengths = [
                "The resume has a clean structure and is easily readable by parsing engines.",
                "Primary contact information and profile headings are clearly formatted."
            ]
            weaknesses = [
                "Quantifiable metrics or KPIs are sparse; consider adding percentages or business impact figures.",
                "Target keywords matching the target company profile could be more prominent.",
                "Ensure standard, industry-recognized terms are used for all technical skills to improve ATS indexing."
            ]


        # INTERVIEW QUESTIONS
        company_info = interview_data.get(company, {})
        questions = company_info.get('technical', [])

        # STORE DATA IN SESSION
        session['missing_skills'] = missing_skills
        session['matched_skills'] = matched_skills
        session['score'] = score
        session['company'] = company
        session['matched_count'] = len(matched_skills)
        session['missing_count'] = len(missing_skills)
        session['questions'] = questions
        session['company_info'] = company_info
        session['strengths'] = strengths
        session['weaknesses'] = weaknesses
        session['chat_history'] = [] # Reset history on new upload
        # Store resume text for AI-powered resume-aware chat
        session['resume_text'] = text[:5000]  # cap at 5000 chars to keep session size reasonable

        return render_template(
            'dashboard.html',
            score=score,
            skills=matched_skills,
            missing=missing_skills,
            questions=questions,
            matched_count=len(matched_skills),
            missing_count=len(missing_skills),
            company_info=company_info,
            strengths=strengths,
            weaknesses=weaknesses
        )
    except Exception as e:
        flash(f"An unexpected error occurred: {str(e)}")
        return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    if 'score' not in session:
        return render_template('index.html')
    
    return render_template(
        'dashboard.html',
        score=session.get('score'),
        skills=session.get('matched_skills'),
        missing=session.get('missing_skills'),
        questions=session.get('questions'),
        matched_count=session.get('matched_count'),
        missing_count=session.get('missing_count'),
        company_info=session.get('company_info', {}),
        strengths=session.get('strengths', []),
        weaknesses=session.get('weaknesses', [])
    )


# LEARNING ROADMAP ROUTE
@app.route('/roadmap')
def roadmap():
    missing_skills = session.get('missing_skills')
    matched_skills = session.get('matched_skills', [])
    company = session.get('company', 'Target Company')
    
    is_perfect_match = False
    
    if missing_skills is None:
        missing_skills = ["Python", "React", "SQL"]
    elif len(missing_skills) == 0:
        is_perfect_match = True
        missing_skills = matched_skills if matched_skills else ["Python", "Data Structures", "Algorithms", "System Design"]

    try:
        with open('data/roadmap.json', 'r', encoding='utf-8') as f:
            roadmap_data = json.load(f)
    except Exception as e:
        roadmap_data = {}
        print(f"[ERROR] Failed to load roadmap.json: {str(e)}")
    
    # Filter roadmap for skills
    user_roadmap = {}
    for skill in missing_skills:
        if skill in roadmap_data:
            user_roadmap[skill] = roadmap_data[skill]
        else:
            # Try to dynamically generate roadmap with OpenAI first, then Gemini, then offline
            generated = False
            
            # 1. OpenAI Roadmap Generation
            openai_client = get_openai_client()
            if openai_client:
                try:
                    prompt = (
                        f"Generate a structured learning roadmap for the technology '{skill}'.\n"
                        f"Provide it in 3 phases: 'Beginner', 'Intermediate', and 'Advanced'.\n"
                        f"For each phase, provide:\n"
                        f"- 'steps': 3 key learning topics/steps.\n"
                        f"- 'youtube': A valid youtube search query URL (e.g. 'https://www.youtube.com/results?search_query=learn+{skill}+beginner').\n"
                        f"- 'duration': Estimated duration (e.g. '2 Weeks').\n"
                        f"- 'platforms': 1-2 coding platforms to practice.\n"
                        f"- 'books': A list of 1 recommended book containing 'title' and 'author'.\n"
                        f"- 'courses': A list of 1 recommended course containing 'title', 'platform', and 'url'.\n\n"
                        f"Return ONLY a valid JSON object matching this schema:\n"
                        f"{{\n"
                        f"  \"Beginner\": {{\n"
                        f"    \"steps\": [\"Step 1\", \"Step 2\"],\n"
                        f"    \"youtube\": \"https://www.youtube.com/results?search_query=...\",\n"
                        f"    \"duration\": \"2 Weeks\",\n"
                        f"    \"platforms\": [\"HackerRank\"],\n"
                        f"    \"books\": [{{\"title\": \"Book Title\", \"author\": \"Author Name\"}}],\n"
                        f"    \"courses\": [{{\"title\": \"Course Title\", \"platform\": \"Coursera\", \"url\": \"https://www.coursera.org\"}}]\n"
                        f"  }},\n"
                        f"  \"Intermediate\": ...,\n"
                        f"  \"Advanced\": ...\n"
                        f"}}\n"
                    )
                    
                    response = openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        response_format={ "type": "json_object" },
                        messages=[
                            {"role": "system", "content": "You are a learning roadmap generator that outputs structured JSON."},
                            {"role": "user", "content": prompt}
                        ]
                    )
                    response_text = (response.choices[0].message.content or "").strip()
                    user_roadmap[skill] = json.loads(response_text)
                    generated = True
                    print(f"[INFO] Dynamically generated roadmap for {skill} via OpenAI ChatGPT.")
                except Exception as e:
                    print(f"[ERROR] OpenAI roadmap generation failed for {skill}: {str(e)}. Falling back to Gemini.")
                    generated = False

            # 2. Gemini Roadmap Generation Fallback
            client = get_gemini_client()
            if not generated and client:
                try:
                    prompt = (
                        f"Generate a structured learning roadmap for the technology '{skill}'.\n"
                        f"Provide it in 3 phases: 'Beginner', 'Intermediate', and 'Advanced'.\n"
                        f"For each phase, provide:\n"
                        f"- 'steps': 3 key learning topics/steps.\n"
                        f"- 'youtube': A valid youtube search query URL (e.g. 'https://www.youtube.com/results?search_query=learn+{skill}+beginner').\n"
                        f"- 'duration': Estimated duration (e.g. '2 Weeks').\n"
                        f"- 'platforms': 1-2 coding platforms to practice.\n"
                        f"- 'books': A list of 1 recommended book containing 'title' and 'author'.\n"
                        f"- 'courses': A list of 1 recommended course containing 'title', 'platform', and 'url'.\n\n"
                        f"Return ONLY a valid JSON object matching this schema:\n"
                        f"{{\n"
                        f"  \"Beginner\": {{\n"
                        f"    \"steps\": [\"Step 1\", \"Step 2\"],\n"
                        f"    \"youtube\": \"https://www.youtube.com/results?search_query=...\",\n"
                        f"    \"duration\": \"2 Weeks\",\n"
                        f"    \"platforms\": [\"HackerRank\"],\n"
                        f"    \"books\": [{{\"title\": \"Book Title\", \"author\": \"Author Name\"}}],\n"
                        f"    \"courses\": [{{\"title\": \"Course Title\", \"platform\": \"Coursera\", \"url\": \"https://www.coursera.org\"}}]\n"
                        f"  }},\n"
                        f"  \"Intermediate\": ...,\n"
                        f"  \"Advanced\": ...\n"
                        f"}}\n"
                        f"Do not include any markdown styling like ```json or other text."
                    )
                    
                    response = client.models.generate_content(
                        model='gemini-1.5-flash',
                        contents=prompt
                    )
                    response_text = (response.text or "").strip()
                    if response_text.startswith("```"):
                        lines = response_text.splitlines()
                        if len(lines) >= 2:
                            start = 1 if "json" in lines[0] or "JSON" in lines[0] else 0
                            end = -1 if lines[-1].startswith("```") else len(lines)
                            response_text = "\n".join(lines[start:end]).strip()
                    
                    user_roadmap[skill] = json.loads(response_text)
                    generated = True
                    print(f"[INFO] Dynamically generated roadmap for {skill} via Gemini.")
                except Exception as e:
                    print(f"[WARNING] Dynamic roadmap generation failed for {skill}: {str(e)}")
                    generated = False
            
            if not generated:
                # Fallback for skills not in our data
                user_roadmap[skill] = {
                    "Beginner": {
                        "steps": [f"Learn basic syntax of {skill}", f"Set up environment for {skill}", "Build first application"],
                        "youtube": f"https://www.youtube.com/results?search_query=learn+{skill}+beginner",
                        "duration": "2 Weeks",
                        "platforms": ["HackerRank"],
                        "books": [{"title": f"Beginning {skill}", "author": "Industry Experts"}],
                        "courses": [{"title": f"Intro to {skill}", "platform": "Coursera", "url": "https://www.coursera.org"}]
                    },
                    "Intermediate": {
                        "steps": ["Advanced logic configurations", "Work with libraries/packages", "Error handling and APIs"],
                        "youtube": f"https://www.youtube.com/results?search_query=learn+{skill}+intermediate",
                        "duration": "3 Weeks",
                        "platforms": ["LeetCode"],
                        "books": [{"title": f"Intermediate {skill}", "author": "Industry Experts"}],
                        "courses": [{"title": f"{skill} Intermediate Course", "platform": "Udemy", "url": "https://www.udemy.com"}]
                    },
                    "Advanced": {
                        "steps": ["Performance tuning & scale", "Architectural patterns", "Build full-scale dynamic project"],
                        "youtube": f"https://www.youtube.com/results?search_query=learn+{skill}+advanced",
                        "duration": "4 Weeks",
                        "platforms": ["GitHub Open Source"],
                        "books": [{"title": f"Mastering {skill}", "author": "Industry Experts"}],
                        "courses": [{"title": f"Advanced {skill} Masterclass", "platform": "Coursera", "url": "https://www.coursera.org"}]
                    }
                }

    return render_template('roadmap.html', roadmap=user_roadmap, is_perfect_match=is_perfect_match, company=company)


# INTERVIEW INTELLIGENCE ROUTE
@app.route('/interview-intelligence')
def interview_intelligence():
    try:
        with open('data/interview_questions.json', 'r', encoding='utf-8') as f:
            interview_data = json.load(f)
        return render_template('interview.html', companies=interview_data)
    except Exception as e:
        flash(f"Error loading interview data: {str(e)}")
        return redirect(url_for('dashboard'))

# DEDICATED CHAT PAGE
@app.route('/chatbot')
def chatbot_page():
    return render_template('chat.html')

# SESSION STATS FOR CHAT SIDEBAR
@app.route('/session_stats')
def session_stats():
    return json.dumps({
        'score': session.get('score'),
        'missing_count': session.get('missing_count'),
        'matched_count': session.get('matched_count'),
        'company': session.get('company')
    })

# CLEAR CHAT HISTORY
@app.route('/clear_chat', methods=['POST'])
def clear_chat():
    session.pop('chat_history', None)
    return json.dumps({'success': True})

# NOTE: /chat route is now handled by routes/chatbot.py (chatbot_bp Blueprint)
# It uses Gemini 2.5 Flash as primary AI with OpenAI fallback and offline heuristics.


# AI MOCK INTERVIEW EVALUATION
@app.route('/evaluate_interview', methods=['POST'])
def evaluate_interview():
    data = request.json
    answer = data.get('answer', '')
    question = data.get('question', 'Tell me about yourself.')
    category = data.get('category', 'Technical')
    company = session.get('company', 'target company')

    eval_success = False

    # 1. OPENAI EVALUATION
    openai_client = get_openai_client()
    if openai_client:
        try:
            prompt = (
                f"You are a Senior Technical Interviewer evaluating a candidate's answer for target company '{company}' under category '{category}'.\n\n"
                f"Interview Question:\n\"{question}\"\n\n"
                f"Candidate's Answer:\n\"{answer}\"\n\n"
                f"Provide a rigorous, constructive evaluation of this answer. Rate their confidence (authority and structure), "
                f"communication (clarity and articulation), and technical accuracy (technical correctness and principles) as integers from 0 to 100.\n\n"
                f"Provide concrete, bullet-point suggestions explaining:\n"
                f"1. What was done well.\n"
                f"2. Specific areas for improvement.\n"
                f"3. A concise exemplary 'model answer' showing how a senior engineer would respond to this question.\n\n"
                f"You MUST return ONLY a valid JSON object in this exact schema, with no markdown code block backticks (like ```json), other text, or explanation:\n"
                f"{{\n"
                f"  \"confidence\": 85,\n"
                f"  \"communication\": 78,\n"
                f"  \"technical\": 90,\n"
                f"  \"suggestions\": \"Feedback and recommendations...\"\n"
                f"}}\n"
            )
            
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={ "type": "json_object" },
                messages=[
                    {"role": "system", "content": "You are a technical interviewer that outputs structured JSON feedback."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            response_text = (response.choices[0].message.content or "").strip()
            res_data = json.loads(response_text)
            
            return json.dumps({
                'confidence': int(res_data.get('confidence', 80)),
                'communication': int(res_data.get('communication', 80)),
                'technical': int(res_data.get('technical', 80)),
                'suggestions': res_data.get('suggestions', 'Evaluation completed successfully.')
            })
        except Exception as e:
            print(f"[ERROR] OpenAI Interview Evaluator failed: {str(e)}. Falling back to Gemini.")
            eval_success = False

    # 2. GEMINI EVALUATION
    client = get_gemini_client()
    if not eval_success and client:
        try:
            prompt = (
                f"You are a Senior Technical Interviewer evaluating a candidate's answer for target company '{company}' under category '{category}'.\n\n"
                f"Interview Question:\n\"{question}\"\n\n"
                f"Candidate's Answer:\n\"{answer}\"\n\n"
                f"Provide a rigorous, constructive evaluation of this answer. Rate their confidence (authority and structure), "
                f"communication (clarity and articulation), and technical accuracy (technical correctness and principles) as integers from 0 to 100.\n\n"
                f"Provide concrete, bullet-point suggestions explaining:\n"
                f"1. What was done well.\n"
                f"2. Specific areas for improvement.\n"
                f"3. A concise exemplary 'model answer' showing how a senior engineer would respond to this question.\n\n"
                f"You MUST return ONLY a valid JSON object in this exact schema, with no markdown code block backticks (like ```json), other text, or explanation:\n"
                f"{{\n"
                f"  \"confidence\": 85,\n"
                f"  \"communication\": 78,\n"
                f"  \"technical\": 90,\n"
                f"  \"suggestions\": \"Feedback and recommendations...\"\n"
                f"}}\n"
            )
            
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt
            )
            
            response_text = (response.text or "").strip()
            # Clean up any potential markdown code blocks
            if response_text.startswith("```"):
                lines = response_text.splitlines()
                if len(lines) >= 2:
                    start = 1 if "json" in lines[0] or "JSON" in lines[0] else 0
                    end = -1 if lines[-1].startswith("```") else len(lines)
                    response_text = "\n".join(lines[start:end]).strip()
            
            res_data = json.loads(response_text)
            return json.dumps({
                'confidence': int(res_data.get('confidence', 80)),
                'communication': int(res_data.get('communication', 80)),
                'technical': int(res_data.get('technical', 80)),
                'suggestions': res_data.get('suggestions', 'Evaluation completed successfully.')
            })
        except Exception as e:
            print(f"[ERROR] Gemini Interview Evaluator failed: {str(e)}. Triggering smart fallback.")

    # Smart Fallback Evaluation Logic (Offline/Fallback Mode)
    confidence = 75
    communication = 70
    technical = 70
    
    length = len(answer.strip())
    if length < 30:
        confidence -= 35
        communication -= 25
        technical -= 30
        suggestions = "Your answer is extremely brief. A complete interview answer should explain your approach, technical reasoning, and provide a concrete example. Try using the STAR (Situation, Task, Action, Result) structure next time."
    elif length < 100:
        confidence -= 15
        communication -= 10
        technical -= 10
        suggestions = "This is a reasonable start, but it lacks depth. To stand out, elaborate on *why* you chose this approach, explain any architectural trade-offs, and use correct technical terminology (e.g. time/space complexity or design patterns)."
    else:
        # Check for technical buzzwords to award higher scores
        buzzwords = ["complexity", "scale", "performance", "design", "database", "cache", "system", "star", "experience", "team", "conflict", "result", "action"]
        found_buzzwords = [word for word in buzzwords if word in answer.lower()]
        
        confidence = min(95, confidence + len(found_buzzwords) * 3)
        communication = min(92, communication + len(found_buzzwords) * 2)
        technical = min(95, technical + len(found_buzzwords) * 4)
        
        suggestions = f"Strong structural effort! Your answer demonstrates solid elaboration. Crucial tips: 1) Explicitly state time/space complexity trade-offs if applicable. 2) Provide a clear quantifiable result of your past actions. (Detected industry keywords: {', '.join(found_buzzwords)})"

    return json.dumps({
        'confidence': confidence,
        'communication': communication,
        'technical': technical,
        'suggestions': suggestions
    })
# SETTINGS ROUTES FOR API KEYS
@app.route('/save_keys', methods=['POST'])
def save_keys():
    data = request.json
    openai_key = data.get('openai_api_key', '').strip()
    gemini_key = data.get('gemini_api_key', '').strip()
    
    if openai_key:
        session['openai_api_key'] = openai_key
    else:
        session.pop('openai_api_key', None)
        
    if gemini_key:
        session['gemini_api_key'] = gemini_key
    else:
        session.pop('gemini_api_key', None)
        
    return json.dumps({'success': True})

@app.route('/get_keys_status', methods=['GET'])
def get_keys_status():
    has_openai = bool(session.get('openai_api_key') or os.environ.get("OPENAI_API_KEY"))
    has_gemini = bool(session.get('gemini_api_key') or os.environ.get("GEMINI_API_KEY"))
    return json.dumps({
        'openai': has_openai,
        'gemini': has_gemini
    })

# RUN APP
if __name__ == '__main__':
    app.run(debug=True)