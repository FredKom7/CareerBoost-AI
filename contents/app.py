import json
import os
import pdfplumber
from google import genai
from google.genai import types
from openai import OpenAI
from flask import Flask, render_template, request, session, flash, redirect, url_for, Response

app = Flask(__name__)
app.secret_key = 'career_boost_secret_key' # For session management

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
            with pdfplumber.open(file) as pdf:
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
                
                response_text = response.choices[0].message.content.strip()
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
                
                response_text = response.text.strip()
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
                    response_text = response.choices[0].message.content.strip()
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
                    response_text = response.text.strip()
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

# AI CHATBOT ROUTE
@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')
    
    # Retrieve chat history from session or initialize
    chat_history = session.get('chat_history', [])
    
    # Keep history bounded to avoid session size limits (e.g., last 10 turns)
    if len(chat_history) > 20:
        chat_history = chat_history[-20:]
    
    company = session.get('company', 'target companies')
    missing_skills = session.get('missing_skills', [])
    score = session.get('score')
    
    context_prefix = ""
    if score is not None:
        context_prefix = (
            f"[Context: Target Company: {company}, "
            f"ATS Score: {score}%, Missing Skills: {', '.join(missing_skills) if missing_skills else 'None'}]\n"
        )
    
    chat_success = False

    # 1. OPENAI CHAT completions
    openai_client = get_openai_client()
    if openai_client:
        try:
            messages = [
                {"role": "system", "content": (
                    "You are Career Coach AI, a helpful, encouraging, and highly professional career mentor. "
                    "You assist users in improving their ATS resume score, preparing for interviews, bridging skill gaps, "
                    "and landing their dream jobs. Keep your answers concise, structured, and action-oriented."
                )}
            ]
            for msg in chat_history:
                role = "user" if msg['role'] == "user" else "assistant"
                messages.append({"role": role, "content": msg['text']})
            
            send_text = context_prefix + user_message if len(chat_history) == 0 else user_message
            messages.append({"role": "user", "content": send_text})
            
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages
            )
            reply_text = response.choices[0].message.content
            
            chat_history.append({'role': 'user', 'text': user_message})
            chat_history.append({'role': 'assistant', 'text': reply_text})
            session['chat_history'] = chat_history
            
            return Response(json.dumps({'response': reply_text}), content_type='application/json')
        except Exception as e:
            print(f"[ERROR] OpenAI Chat completions failed: {str(e)}. Falling back to Gemini.")
            chat_success = False

    # 2. GEMINI CHAT fallback
    client = get_gemini_client()
    if not chat_success and client:
        try:
            # Build list of Content objects from session history
            history_contents = []
            for msg in chat_history:
                role = "user" if msg['role'] == "user" else "model"
                history_contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg['text'])]
                    )
                )
            
            # Start chat session
            chat_session = client.chats.create(
                model='gemini-1.5-flash',
                config=types.GenerateContentConfig(
                    system_instruction=(
                        "You are Career Coach AI, a helpful, encouraging, and highly professional career mentor. "
                        "You assist users in improving their ATS resume score, preparing for interviews, bridging skill gaps, "
                        "and landing their dream jobs. Keep your answers concise, structured, and action-oriented."
                    )
                ),
                history=history_contents
            )
            
            # Send message with context prefix for the first message
            send_text = context_prefix + user_message if len(chat_history) == 0 else user_message
            response = chat_session.send_message(send_text)
            reply_text = response.text
            
            # Save message pair to session
            chat_history.append({'role': 'user', 'text': user_message})
            chat_history.append({'role': 'assistant', 'text': reply_text})
            session['chat_history'] = chat_history
            
            return Response(json.dumps({'response': reply_text}), content_type='application/json')
        except Exception as e:
            print(f"[ERROR] Gemini Chat API failed: {str(e)}. Falling back to offline heuristics.")

    # ---- INTELLIGENT OFFLINE CAREER COACH ----
    m = user_message.lower()

    # --- RESUME TOPICS ---
    if any(k in m for k in ['linkedin', 'linked in']):
        reply_text = (
            "**Crafting a High-Impact LinkedIn Summary**\n\n"
            "Your LinkedIn summary is your digital elevator pitch — here's a proven formula:\n\n"
            "**1. Hook (First 2 lines)** — These show before 'See more', so make them count.\n"
            "Example: *'Software engineer who has shipped products used by 2M+ users. I thrive at the intersection of clean code and business impact.'*\n\n"
            "**2. Your Story** — Briefly explain your journey: where you've been, what you've mastered, and what drives you.\n\n"
            "**3. Key Wins (Quantified)** — Add 3–5 bullet achievements:\n"
            "- Reduced API response time by 60% using Redis caching\n"
            "- Led a team of 4 engineers to deliver a $2M product on schedule\n\n"
            "**4. Skills Keywords** — Include your top 10 tech skills naturally in the text (this boosts recruiter search visibility).\n\n"
            "**5. Call to Action** — End with: *'Open to senior engineering roles in fintech or SaaS. Let's connect!'*\n\n"
            "**Pro tip:** Use the first-person voice and keep it between 200–300 words. Avoid buzzwords like 'passionate' and 'guru'."
        )
    elif any(k in m for k in ['ats', 'applicant tracking', 'ats score', 'keyword']):
        reply_text = (
            "**ATS Optimization — How to Beat the Bots**\n\n"
            "75% of resumes are rejected by ATS before a human ever reads them. Here's how to pass:\n\n"
            "**Format Rules:**\n"
            "- Use a single-column layout (no tables, text boxes, or headers/footers)\n"
            "- Stick to standard section headings: *Experience*, *Education*, *Skills*, *Projects*\n"
            "- Use common fonts: Calibri, Arial, or Times New Roman\n"
            "- Save as .docx or .pdf (check the job posting — some ATS prefer .docx)\n\n"
            "**Keyword Strategy:**\n"
            "- Copy the exact job description and paste it into a word cloud tool\n"
            "- Mirror the top keywords verbatim in your resume (e.g., if they say 'REST APIs', don't write 'RESTful services')\n"
            "- Include both acronyms and full forms: *ML (Machine Learning)*, *CI/CD (Continuous Integration)*\n\n"
            "**Content Rules:**\n"
            "- Put your strongest keywords in the first half of the resume\n"
            "- Include a dedicated **Technical Skills** section near the top\n"
            "- Quantify every achievement: *'Improved deployment speed by 40%'* beats *'Improved deployment speed'*\n\n"
            "**Quick Win:** Run your resume through jobscan.co — it scores your resume against any job description instantly."
        )
    elif any(k in m for k in ['resume summary', 'professional summary', 'objective', 'profile section']):
        reply_text = (
            "**Writing a Powerful Resume Summary**\n\n"
            "A strong summary is 3–4 sentences that instantly tell a recruiter: who you are, what you've done, and what value you bring.\n\n"
            "**Template:**\n"
            "*[Job title] with [X] years of experience in [domain]. Skilled in [top 3 skills]. Delivered [key achievement]. Seeking to [goal] at [type of company].*\n\n"
            "**Example (Software Engineer):**\n"
            "*Full-stack software engineer with 3 years of experience building scalable web applications. Proficient in React, Node.js, and PostgreSQL. Reduced customer churn by 18% by redesigning the onboarding flow at my previous company. Looking to join a product-driven team where I can own end-to-end features.*\n\n"
            "**What to Avoid:**\n"
            "- Generic phrases: 'hardworking', 'team player', 'passionate about technology'\n"
            "- Objective statements (outdated — they focus on what YOU want, not what you offer)\n"
            "- Using 'I' — write in third-person fragments\n\n"
            "Tailor this section for every application by matching the exact role title and top required skills."
        )
    elif any(k in m for k in ['resume', 'cv', 'curriculum vitae']):
        reply_text = (
            "**Resume Improvement — Complete Checklist**\n\n"
            "**Structure (5 key sections in order):**\n"
            "1. Contact info + LinkedIn URL\n"
            "2. Professional Summary (3–4 lines)\n"
            "3. Technical Skills (grouped by category)\n"
            "4. Work Experience (reverse chronological)\n"
            "5. Projects, Education, Certifications\n\n"
            "**For each Experience bullet, use the formula:**\n"
            "*Action Verb + What you did + Impact/Result*\n"
            "✓ *'Optimized database queries, reducing page load time by 52%'*\n"
            "✗ *'Responsible for database maintenance'*\n\n"
            "**Strong action verbs to use:** Architected, Engineered, Spearheaded, Automated, Reduced, Scaled, Shipped, Led\n\n"
            "**Common Mistakes to Fix:**\n"
            "- No measurable results (add %, $, time saved)\n"
            "- Using passive voice ('was responsible for')\n"
            "- Including irrelevant hobbies\n"
            "- Resume longer than 1 page (for < 5 years experience)\n"
            "- Inconsistent date formats\n\n"
            "Tailor every resume to the specific job description — one generic resume won't get you far."
        )

    # --- COMPANY-SPECIFIC ---
    elif 'google' in m:
        reply_text = (
            "**Cracking the Google Interview**\n\n"
            "Google has a highly structured hiring process. Here's what to focus on:\n\n"
            "**Coding Rounds (2–3 rounds, 45 min each):**\n"
            "- Focus: Arrays, Strings, Trees, Graphs, Dynamic Programming, Heap\n"
            "- Practice 150+ LeetCode problems (Medium and Hard)\n"
            "- Recommended list: Blind 75, NeetCode 150\n"
            "- Always explain your thought process before coding\n\n"
            "**System Design (for SDE-2 and above):**\n"
            "- Topics: Load balancers, CDN, Databases (SQL vs NoSQL), Caching (Redis), Kafka, Microservices\n"
            "- Practice designing: URL shortener, Instagram, Google Maps, WhatsApp\n"
            "- Resource: *Designing Data-Intensive Applications* by Martin Kleppmann\n\n"
            "**Behavioural (Googleyness round):**\n"
            "- Google looks for: Cognitive ability, Leadership, Googleyness (collaboration, openness)\n"
            "- Prepare 8–10 STAR stories covering: failure, conflict, ambiguity, impact\n\n"
            "**Timeline:** Plan for 8–12 weeks of dedicated preparation. Don't rush it."
        )
    elif 'amazon' in m:
        reply_text = (
            "**Cracking the Amazon Interview**\n\n"
            "Amazon is unique — the Leadership Principles (LPs) are at the heart of *every* interview.\n\n"
            "**The 16 Leadership Principles you MUST know:**\n"
            "Customer Obsession, Ownership, Invent & Simplify, Are Right A Lot, Learn & Be Curious, Hire & Develop the Best, Insist on Highest Standards, Think Big, Bias for Action, Frugality, Earn Trust, Dive Deep, Have Backbone, Deliver Results, Strive to be Earth's Best Employer, Success & Scale Bring Responsibility\n\n"
            "**Interview Structure:**\n"
            "- OA (Online Assessment): Coding + Work Simulation\n"
            "- Loop: 4–5 rounds, each grilling both LP stories and coding/design\n\n"
            "**For LP Questions — use the STAR-L method:**\n"
            "Situation → Task → Action → Result → **Learnings**\n\n"
            "**Key tip:** Every answer must demonstrate Ownership and Customer Obsession. Amazon interviewers take notes and score each LP separately.\n\n"
            "Prepare at least 2 stories for each of the top 8 LPs. Quality of stories matters more than quantity."
        )
    elif 'microsoft' in m:
        reply_text = (
            "**Cracking the Microsoft Interview**\n\n"
            "Microsoft focuses on problem-solving, collaboration, and growth mindset.\n\n"
            "**Coding Rounds:**\n"
            "- Difficulty: LeetCode Medium — focus on Trees, Arrays, Graphs, Dynamic Programming\n"
            "- They often ask about edge cases and test coverage\n"
            "- Be prepared to write full, clean, compilable code\n\n"
            "**Behavioural (Core competencies):**\n"
            "- Growth Mindset: How do you learn from failure?\n"
            "- Collaboration: Describe working with a difficult teammate\n"
            "- Customer focus: Tell me about a time you put the user first\n\n"
            "**System Design:**\n"
            "- Focus on Azure-native architectures, microservices, REST APIs\n"
            "- Design: Collaborative document editor (like Office 365), notification system\n\n"
            "**Culture fit tip:** Microsoft interviewers genuinely want you to succeed. Ask clarifying questions, think aloud, and if you're stuck — say so and propose partial solutions."
        )
    elif any(k in m for k in ['meta', 'facebook']):
        reply_text = (
            "**Cracking the Meta (Facebook) Interview**\n\n"
            "Meta has some of the most algorithmic-heavy interviews in the industry.\n\n"
            "**Coding (2 rounds, hardest in FAANG):**\n"
            "- Heavy on: Dynamic Programming, Graph traversal (BFS/DFS), Trees, Sliding Window\n"
            "- They expect optimal O(n log n) or O(n) solutions — brute force won't pass\n"
            "- LeetCode: Focus on Meta-tagged problems (filter by Meta on LeetCode)\n\n"
            "**Behavioural (Uses a rubric):**\n"
            "- Core values: Move Fast, Be Bold, Focus on Long-Term Impact, Be Open\n"
            "- Prepare stories about: taking initiative, moving fast despite ambiguity, cross-functional work\n\n"
            "**System Design:**\n"
            "- Focus areas: News Feed, Messenger, Graph systems, Ad targeting infrastructure\n"
            "- Scale matters: Design for billions of users\n\n"
            "**Preparation tip:** Meta interviewers are very direct. If your solution is suboptimal, they'll tell you. Respond gracefully and optimize iteratively."
        )
    elif any(k in m for k in ['tcs', 'infosys', 'wipro', 'accenture', 'hcl', 'cognizant', 'capgemini']):
        reply_text = (
            "**Cracking Service-Based Company Interviews (TCS, Infosys, Wipro, etc.)**\n\n"
            "These companies have structured mass-hiring processes. Here's how to stand out:\n\n"
            "**Aptitude Round:**\n"
            "- Topics: Quantitative Aptitude, Logical Reasoning, Verbal Ability\n"
            "- Practice: IndiaBix, PrepInsta, company-specific mock tests\n"
            "- Cutoff is typically around 60–70% — speed matters as much as accuracy\n\n"
            "**Technical Round:**\n"
            "- Focus on: C, C++, Java basics, OOPS concepts, DBMS (SQL), OS fundamentals\n"
            "- Know your final year project inside-out — they WILL ask about it\n"
            "- Be ready to write basic programs (swapping, fibonacci, pattern printing)\n\n"
            "**HR Round:**\n"
            "- *'Tell me about yourself'* — prepare a crisp 90-second pitch\n"
            "- *'Why do you want to join TCS/Infosys?'* — research their recent projects and mention them\n"
            "- Show willingness to relocate and work in any technology domain\n\n"
            "**Key differentiator:** Most candidates are equally qualified. Your communication clarity and confidence will set you apart."
        )
    elif any(k in m for k in ['startup', 'product company', 'mnc']):
        reply_text = (
            "**Product Company vs Service Company vs Startup — What's Right for You?**\n\n"
            "**Product Companies (Google, Microsoft, Flipkart):**\n"
            "- Higher salaries (10–30% above market), better learning, you own products used by millions\n"
            "- Interview: Highly algorithmic, requires 2–3 months of solid preparation\n"
            "- Career growth is skill-based, not time-based\n\n"
            "**Service Companies (TCS, Infosys, Accenture):**\n"
            "- Easier to get into, good for freshers, exposure to diverse client domains\n"
            "- Growth can be slower, work is often maintenance-heavy\n"
            "- Great for building foundational experience before moving to product\n\n"
            "**Startups:**\n"
            "- High ownership, fast learning, direct business impact\n"
            "- Interview: Often a practical task (take-home project) + culture fit chat\n"
            "- Risk: Unstable if early stage; check funding status and runway before joining\n\n"
            "**Recommendation for freshers:** Start anywhere, but after 1–2 years, aggressively upskill and move to a product company or well-funded startup."
        )

    # --- INTERVIEW PREP ---
    elif any(k in m for k in ['star method', 'star format', 'behavioral', 'behavioural', 'tell me about yourself', 'tell me about a time']):
        reply_text = (
            "**Mastering the STAR Method for Behavioral Interviews**\n\n"
            "STAR = **S**ituation → **T**ask → **A**ction → **R**esult\n\n"
            "**Example Question:** *'Tell me about a time you resolved a conflict in your team.'*\n\n"
            "**S — Situation:** *'During my internship at XYZ, two developers disagreed on the database architecture for our new feature, causing a 3-day delay.'*\n\n"
            "**T — Task:** *'As the technical lead, it was my responsibility to align the team and unblock the sprint.'*\n\n"
            "**A — Action:** *'I organized a 1-hour whiteboard session, presented benchmarks for both approaches, and proposed a hybrid solution. I gave each developer ownership of one module to reduce ego friction.'*\n\n"
            "**R — Result:** *'We shipped the feature on time. The hybrid approach also improved query performance by 30%, which became our standard going forward.'*\n\n"
            "**Key tips:**\n"
            "- Always quantify the result (%, time saved, users impacted)\n"
            "- Keep answers to 2–3 minutes\n"
            "- Prepare 8–10 versatile stories that can be adapted to multiple questions\n"
            "- Avoid blaming teammates — always show what *you* did personally"
        )
    elif any(k in m for k in ['system design', 'hld', 'lld', 'design system', 'architecture']):
        reply_text = (
            "**System Design Interview — A Step-by-Step Framework**\n\n"
            "Use this structured approach in every system design round:\n\n"
            "**Step 1 — Clarify Requirements (5 min)**\n"
            "- Functional: What must the system do? (e.g., upload, view, search)\n"
            "- Non-functional: Scale, latency, availability, consistency\n"
            "- *'How many daily active users are we designing for?'*\n\n"
            "**Step 2 — Capacity Estimation (3 min)**\n"
            "- Storage: e.g., 10M users × 1KB profile = 10GB\n"
            "- Traffic: reads/writes per second\n\n"
            "**Step 3 — High-Level Design (15 min)**\n"
            "- Draw: Client → CDN → Load Balancer → API Servers → Cache → DB\n"
            "- Choose: SQL vs NoSQL, monolith vs microservices\n\n"
            "**Step 4 — Deep Dive into Key Components (15 min)**\n"
            "- Pick 2–3 components to go deep on (DB schema, caching strategy, message queue)\n\n"
            "**Step 5 — Address Bottlenecks (5 min)**\n"
            "- Single points of failure, horizontal scaling, replication, sharding\n\n"
            "**Must-know topics:** Consistent Hashing, CAP Theorem, Redis, Kafka, CDN, SQL vs NoSQL, Load Balancing, Database Indexing"
        )
    elif any(k in m for k in ['salary', 'negotiate', 'negotiation', 'offer', 'ctc', 'package', 'compensation']):
        reply_text = (
            "**Salary Negotiation — How to Get What You Deserve**\n\n"
            "Most candidates leave money on the table by not negotiating. Here's how to do it confidently:\n\n"
            "**Before the Offer:**\n"
            "- Research market rates: Glassdoor, Levels.fyi, LinkedIn Salary, AmbitionBox (India)\n"
            "- Know your BATNA (Best Alternative To Negotiated Agreement) — other offers or current salary\n\n"
            "**When They Ask 'What are your salary expectations?':**\n"
            "- Redirect: *'I'm flexible and would love to understand the full compensation structure first.'*\n"
            "- Or give a range: *'Based on my research and experience, I'm targeting ₹18–22 LPA.'*\n\n"
            "**When You Receive the Offer:**\n"
            "- Never accept on the spot — *'Thank you! Can I have 2 days to review?'*\n"
            "- Counter with data: *'I've done market research and similar roles at [Company X] pay ₹22L. Given my experience with [specific skill], I'd like to discuss ₹21L.'*\n\n"
            "**What You Can Negotiate Beyond Base Pay:**\n"
            "Joining bonus, remote flexibility, stock options (ESOPs), learning stipend, notice period buyout\n\n"
            "**Golden rule:** The person who speaks a number first often loses. Stay patient."
        )
    elif any(k in m for k in ['fresher', 'entry level', 'no experience', 'fresh graduate', 'first job', 'campus']):
        reply_text = (
            "**Getting Your First Tech Job — A Fresher's Complete Roadmap**\n\n"
            "**Build a portfolio that replaces experience:**\n"
            "1. **3 Solid Projects** — Each should solve a real problem. Ideas: job board scraper, expense tracker, chat app with WebSockets\n"
            "2. **GitHub Activity** — Keep your contribution graph green. Recruiters check this.\n"
            "3. **Certifications** — AWS Cloud Practitioner, Google Data Analytics, Meta Front-End Developer (Coursera) add credibility\n\n"
            "**Optimizing Your Applications:**\n"
            "- Apply to 15–20 companies per week (not just the top ones)\n"
            "- Target: service companies, well-funded Series A/B startups, product MNCs with fresher programs\n"
            "- Use: LinkedIn Easy Apply, Naukri, Internshala, Unstop (for competitions and hackathons)\n\n"
            "**Interview Prep (4-week plan):**\n"
            "- Week 1–2: DSA basics (arrays, strings, recursion, sorting) — LeetCode Easy\n"
            "- Week 3: OOPS, DBMS, OS, Networking fundamentals\n"
            "- Week 4: Mock interviews, behavioral stories, company research\n\n"
            "**Your biggest advantage as a fresher:** You're a blank canvas — show hunger, adaptability, and a strong learning attitude."
        )
    elif any(k in m for k in ['machine learning', 'ml', 'artificial intelligence', 'ai engineer', 'data science', 'data scientist']):
        reply_text = (
            "**Breaking into ML/Data Science — Your Career Roadmap**\n\n"
            "**Core Skills to Build (in order):**\n"
            "1. **Python** — pandas, NumPy, matplotlib (2–3 weeks)\n"
            "2. **Statistics** — Probability, distributions, hypothesis testing, p-values\n"
            "3. **Machine Learning** — scikit-learn: regression, classification, clustering, evaluation metrics\n"
            "4. **Deep Learning** — TensorFlow or PyTorch: CNNs, RNNs, Transformers\n"
            "5. **MLOps** — Model deployment with FastAPI/Flask, Docker, MLflow\n\n"
            "**Portfolio Projects:**\n"
            "- Sentiment analysis API (NLP)\n"
            "- Customer churn prediction (tabular ML)\n"
            "- Image classifier with fine-tuned ResNet (CV)\n"
            "- LLM-powered chatbot (GenAI)\n\n"
            "**Interview Prep:**\n"
            "- Conceptual: Bias-variance tradeoff, overfitting, regularization, evaluation metrics (F1, AUC-ROC)\n"
            "- SQL is mandatory — practice aggregations, window functions, joins\n"
            "- Case studies: A/B testing, recommendation systems\n\n"
            "**Resources:** Kaggle (hands-on), fast.ai (deep learning), StatQuest (YouTube for statistics)"
        )
    elif any(k in m for k in ['python', 'java', 'javascript', 'react', 'node', 'backend', 'frontend', 'full stack', 'fullstack', 'web dev', 'software engineer', 'developer']):
        reply_text = (
            "**Software Engineering Career — How to Accelerate Your Growth**\n\n"
            "**To be a competitive candidate in 2025, you need:**\n\n"
            "**Core CS Fundamentals (non-negotiable):**\n"
            "- Data Structures & Algorithms — LeetCode 150+ problems\n"
            "- System Design — both HLD and LLD\n"
            "- OOPS, DBMS, OS, Computer Networks basics\n\n"
            "**For Frontend Roles:**\n"
            "- React/Next.js, TypeScript, REST/GraphQL\n"
            "- CSS mastery: Flexbox, Grid, responsive design\n"
            "- Performance: Lighthouse scores, lazy loading, code splitting\n\n"
            "**For Backend Roles:**\n"
            "- Strong in one language: Node.js, Python (Django/FastAPI), Java (Spring Boot), or Go\n"
            "- Databases: PostgreSQL + Redis (caching)\n"
            "- APIs: REST design, authentication (JWT, OAuth2)\n"
            "- Infrastructure: Docker, basic Kubernetes, CI/CD pipelines\n\n"
            "**For Full Stack:**\n"
            "- Combine both, plus cloud deployment (AWS/GCP/Vercel)\n\n"
            "**Career tip:** Depth in one area is more valuable than superficial knowledge of many. Pick your stack and go deep before going broad."
        )
    elif any(k in m for k in ['dsa', 'data structures', 'algorithms', 'leetcode', 'competitive programming', 'coding']):
        reply_text = (
            "**Mastering DSA for Coding Interviews**\n\n"
            "**The 8 Essential Topics (in priority order):**\n"
            "1. Arrays & Strings — two pointers, sliding window\n"
            "2. Hash Maps & Sets — frequency counting, lookup optimization\n"
            "3. Linked Lists — slow/fast pointers, reversal\n"
            "4. Trees & Binary Search Trees — DFS, BFS, level order\n"
            "5. Graphs — DFS/BFS, Dijkstra, Union-Find\n"
            "6. Dynamic Programming — memoization, tabulation, classic patterns\n"
            "7. Binary Search — on sorted arrays and on answer space\n"
            "8. Heaps — top-K problems, priority queues\n\n"
            "**Study Plan (8 weeks):**\n"
            "- Weeks 1–2: Arrays, Strings, Hashmaps (LeetCode Easy)\n"
            "- Weeks 3–4: Trees, Linked Lists, Stacks/Queues (Easy-Medium)\n"
            "- Weeks 5–6: Graphs, Binary Search, Greedy (Medium)\n"
            "- Weeks 7–8: DP, Heaps, Mock Interviews (Medium-Hard)\n\n"
            "**Best Resources:**\n"
            "- NeetCode.io (structured roadmap + video explanations)\n"
            "- LeetCode (filter by company + topic)\n"
            "- *Cracking the Coding Interview* by Gayle Laakmann McDowell\n\n"
            "**Daily target:** 2–3 problems per day consistently beats cramming."
        )
    elif any(k in m for k in ['switch', 'career change', 'transition', 'change job', 'job change', 'changing career']):
        reply_text = (
            "**Making a Successful Career Transition into Tech**\n\n"
            "Whether you're switching from a non-tech background or changing your tech specialization, here's the proven path:\n\n"
            "**Step 1 — Identify your transferable skills**\n"
            "- Domain knowledge (finance → fintech, healthcare → healthtech) is extremely valuable\n"
            "- Analytical skills, project management, client communication all translate\n\n"
            "**Step 2 — Fill the technical gap (3–6 months)**\n"
            "- Choose one focused learning path: Full Stack, Data Science, Cloud, or QA/Testing\n"
            "- Avoid learning everything — one solid skill beats five mediocre ones\n\n"
            "**Step 3 — Build a portfolio fast**\n"
            "- 2 domain-specific projects (use your previous industry knowledge)\n"
            "- 1 open source contribution (even documentation counts)\n\n"
            "**Step 4 — Target the right companies**\n"
            "- Startups and SMEs are more open to career changers than large MNCs\n"
            "- Look for roles like 'Associate Engineer', 'Junior Developer', 'Technology Analyst'\n\n"
            "**Step 5 — Own your story**\n"
            "- Frame your career change as an asset: *'My 3 years in banking gives me unique insight into the problems our product solves'*\n\n"
            "Timeline: Most people successfully transition in 6–12 months with consistent effort."
        )
    elif any(k in m for k in ['remote', 'work from home', 'wfh', 'remote job', 'remote work']):
        reply_text = (
            "**Landing a Remote Software Job**\n\n"
            "The remote job market is highly competitive but winnable with the right strategy:\n\n"
            "**Best Platforms to Find Remote Jobs:**\n"
            "- Remote.co, We Work Remotely, RemoteOK, Himalayas.app\n"
            "- LinkedIn (filter: Remote) — apply within the first hour of posting for best results\n"
            "- Toptal and Upwork for freelance-to-fulltime transitions\n\n"
            "**What Remote Employers Look For:**\n"
            "- **Asynchronous communication** skills (clear writing > meetings)\n"
            "- **Self-management** — ability to deliver without micromanagement\n"
            "- **Documentation habits** — do you write things down?\n"
            "- A GitHub profile with consistent activity\n\n"
            "**Resume/LinkedIn adjustments:**\n"
            "- Add 'Open to remote work' in your LinkedIn headline\n"
            "- Include timezone and location clearly\n"
            "- Mention any prior remote/async work experience explicitly\n\n"
            "**Interview tip:** Remote interviews often include a take-home assignment. Treat it professionally — it's your main differentiator."
        )
    elif any(k in m for k in ['portfolio', 'project', 'github', 'side project', 'open source']):
        reply_text = (
            "**Building a Portfolio That Gets You Hired**\n\n"
            "Your portfolio is your proof of competence. Here's how to make it stand out:\n\n"
            "**3 Projects That Actually Impress Recruiters:**\n"
            "1. **A Full-Stack App** — End-to-end: Auth, database, REST API, deployed live (Vercel + Railway/Render)\n"
            "2. **A Real Problem Solved** — Automate something painful (e.g., a resume screener, price tracker bot, meeting scheduler)\n"
            "3. **A Clone with a Twist** — Build a simplified Spotify, Notion, or Twitter — but add one unique feature\n\n"
            "**GitHub Best Practices:**\n"
            "- Write a detailed README with: what it does, tech stack, setup instructions, screenshots\n"
            "- Keep commit messages meaningful: *'Add Redis caching to product endpoint'* not *'update'*\n"
            "- Pin your 4 best repos on your profile\n\n"
            "**Deployment is non-negotiable:** A live URL shows you can ship, not just code.\n\n"
            "**Open Source Contributions:** Start with 'good first issue' tags on GitHub. Even a documentation fix is credible contribution."
        )
    elif any(k in m for k in ['interview tips', 'interview advice', 'prepare for interview', 'crack interview', 'interview']):
        reply_text = (
            "**Complete Interview Preparation Strategy**\n\n"
            "**4–6 Weeks Before the Interview:**\n"
            "- Revise DSA fundamentals — aim for 2 LeetCode problems/day\n"
            "- Prepare 8–10 STAR behavioral stories\n"
            "- Do 2 mock interviews per week (Pramp, Interviewing.io, or with a friend)\n\n"
            "**1 Week Before:**\n"
            "- Research the company deeply: products, recent news, engineering blog, tech stack\n"
            "- Review your own resume line by line — expect questions on every bullet\n"
            "- Prepare 5 thoughtful questions to ask the interviewer\n\n"
            "**Day of the Interview:**\n"
            "- Test your audio/video 30 min before (for virtual)\n"
            "- Keep water, pen, and paper ready\n"
            "- Arrive/log in 5–10 minutes early\n\n"
            "**During the Interview:**\n"
            "- For coding: Think out loud → state approach → get approval → code → test edge cases\n"
            "- For behavioral: Take 10 seconds to structure your answer before speaking\n"
            "- Ask clarifying questions — it shows analytical thinking\n\n"
            "**After the Interview:**\n"
            "- Send a follow-up thank-you email within 24 hours\n"
            "- Note down every question asked — it'll help you improve for the next round"
        )
    elif any(k in m for k in ['networking', 'referral', 'connection', 'reach out', 'cold message', 'cold email']):
        reply_text = (
            "**Professional Networking That Actually Works**\n\n"
            "85% of jobs are filled through networking. Here's how to do it without feeling awkward:\n\n"
            "**LinkedIn Outreach Formula:**\n"
            "Personalized note (< 300 characters):\n"
            "*'Hi [Name], I came across your post on [topic] and found it incredibly insightful. I'm a software engineer preparing to apply at [Company]. Would you be open to a 15-min chat to hear about your experience there?'*\n\n"
            "**Rules for Cold Outreach:**\n"
            "- Lead with a genuine compliment or shared interest\n"
            "- Have a very specific ask (15-min call, not 'any advice')\n"
            "- Follow up once after 5–7 days if no response (then let it go)\n\n"
            "**Getting a Referral:**\n"
            "- Find employees at your target company on LinkedIn\n"
            "- Engage with their content for 1–2 weeks before asking\n"
            "- Make their job easy: send your resume + a specific role link + a 3-line pitch\n\n"
            "**Where to Network Beyond LinkedIn:**\n"
            "- Local meetups (Meetup.com)\n"
            "- Twitter/X tech communities\n"
            "- Discord servers (Reactiflux, CS Career Hub)\n"
            "- Alumni networks from your college"
        )
    elif any(k in m for k in ['cloud', 'aws', 'gcp', 'azure', 'devops', 'docker', 'kubernetes', 'ci/cd', 'devsecops']):
        reply_text = (
            "**Cloud & DevOps Career Path**\n\n"
            "Cloud and DevOps are among the highest-paying tech specializations right now.\n\n"
            "**Certification Roadmap (in order):**\n"
            "1. **AWS Cloud Practitioner** (CLF-C02) — 1 month, entry-level, $300+ salary bump\n"
            "2. **AWS Solutions Architect Associate** (SAA-C03) — 2 months, most popular cert\n"
            "3. **CKA (Certified Kubernetes Administrator)** — for DevOps/Platform engineers\n"
            "4. **Terraform Associate** — Infrastructure as Code is a must-have skill\n\n"
            "**Core Skills to Master:**\n"
            "- **Containers:** Docker → Docker Compose → Kubernetes\n"
            "- **CI/CD:** GitHub Actions or GitLab CI, Jenkins basics\n"
            "- **IaC:** Terraform (industry standard), Ansible for config management\n"
            "- **Monitoring:** Prometheus + Grafana, CloudWatch\n"
            "- **Networking:** VPC, subnets, security groups, load balancers\n\n"
            "**Interview Topics:**\n"
            "- Difference between containers and VMs\n"
            "- How to design a blue-green deployment pipeline\n"
            "- Kubernetes pod scheduling and resource limits\n\n"
            "Start with AWS Free Tier — build real projects to reinforce every concept you learn."
        )
    elif any(k in m for k in ['promotion', 'raise', 'grow', 'career growth', 'senior', 'seniority', 'level up']):
        reply_text = (
            "**Getting Promoted Faster — A Strategic Career Growth Guide**\n\n"
            "Promotions don't just go to the best technical performers — they go to those who demonstrate the *next level's* behaviors.\n\n"
            "**What separates Senior from Mid-level:**\n"
            "- Senior engineers solve ambiguous problems independently\n"
            "- They improve team processes, not just their own code\n"
            "- They think about business impact, not just task completion\n"
            "- They mentor junior engineers proactively\n\n"
            "**Tactical Steps to Get Promoted:**\n"
            "1. **Have the conversation early** — *'What does the promotion criteria look like for my next level?'*\n"
            "2. **Track your impact** — Keep a running *brag document* of achievements with metrics\n"
            "3. **Increase your visibility** — Present in team meetings, write internal tech docs, lead initiatives\n"
            "4. **Find a sponsor** (not just a mentor) — A senior leader who actively advocates for you in promotion discussions\n"
            "5. **Take on stretch assignments** — Volunteer for high-visibility projects even if they're slightly outside your comfort zone\n\n"
            "**Timeline:** Most engineers can move up a level every 18–24 months with intentional effort."
        )
    else:
        # Smart general fallback based on context
        company = session.get('company', '')
        missing = session.get('missing_skills', [])
        score = session.get('score')
        
        if score is not None and missing:
            reply_text = (
                f"**Here's My Career Advice Based on Your Profile**\n\n"
                f"Your current ATS score is **{score}%** for **{company}**, with **{len(missing)} skill gap(s)**: {', '.join(missing[:4])}{'...' if len(missing) > 4 else ''}.\n\n"
                f"**Your 3 Priority Actions Right Now:**\n\n"
                f"**1. Bridge Your Skill Gaps** — Focus on *{missing[0] if missing else 'your missing skills'}* first since it likely has the highest job market demand. Use structured resources like Coursera, Udemy, or the Learning Roadmap in this app.\n\n"
                f"**2. Strengthen Your Resume** — Add 2–3 quantified achievements to each job/project entry. Recruiters spend 7 seconds on a resume — make each bullet count.\n\n"
                f"**3. Start Interview Prep for {company}** — Begin practicing company-specific questions in the Mock Interview section. Aim for 30 minutes of focused practice per day.\n\n"
                f"Feel free to ask me anything specific — resume writing, salary negotiation, system design, DSA, or any company-specific guidance!"
            )
        else:
            reply_text = (
                "**Welcome! Here's How I Can Help You**\n\n"
                "I'm your AI Career Coach, specialized in tech careers. Here are the topics I can give you detailed guidance on:\n\n"
                "- 📄 **Resume Writing** — STAR bullets, ATS optimization, summary sections\n"
                "- 🏢 **Company Prep** — Google, Amazon, Microsoft, Meta, TCS, Infosys and more\n"
                "- 💻 **Technical Interviews** — DSA, System Design, LLD patterns\n"
                "- 🎤 **Behavioral Interviews** — STAR method, company-specific values\n"
                "- 💰 **Salary Negotiation** — How to counter-offer and get what you're worth\n"
                "- 🚀 **Career Transitions** — Fresher advice, switching domains, promotions\n"
                "- ☁️ **Tech Specializations** — Cloud, ML, Full Stack, DevOps career paths\n"
                "- 🤝 **Networking & Referrals** — LinkedIn outreach, getting referrals\n\n"
                "Try asking something specific like: *'How do I prepare for a Google system design interview?'* or *'Help me write a resume summary for a data science role.'*"
            )

    chat_history.append({'role': 'user', 'text': user_message})
    chat_history.append({'role': 'assistant', 'text': reply_text})
    session['chat_history'] = chat_history

    return Response(json.dumps({'response': reply_text}), content_type='application/json')


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
            
            response_text = response.choices[0].message.content.strip()
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
            
            response_text = response.text.strip()
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