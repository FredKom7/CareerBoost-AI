"""
routes/chatbot.py

Flask Blueprint for the AI Career Coach chatbot.
Handles /chat POST endpoint with Gemini 2.5 Flash as primary AI,
OpenAI GPT-4o-mini as secondary, and offline keyword heuristics as final fallback.
"""

import json
import os
from flask import Blueprint, request, session, Response
from services.gemini_service import (
    get_gemini_client,
    build_context_message,
    chat_with_gemini,
)

chatbot_bp = Blueprint('chatbot', __name__)

# Maximum allowed message length (characters)
MAX_MESSAGE_LENGTH = 2000

# ─────────────────────────────────────────────
# OPENAI HELPER (optional secondary)
# ─────────────────────────────────────────────

def _get_openai_client():
    """Returns an OpenAI client if a key is available, else None."""
    try:
        from openai import OpenAI
        session_key = session.get('openai_api_key')
        if session_key:
            return OpenAI(api_key=session_key)
        env_key = os.environ.get('OPENAI_API_KEY')
        if env_key:
            return OpenAI(api_key=env_key)
    except Exception:
        pass
    return None


OPENAI_SYSTEM_PROMPT = (
    "You are CareerBoost AI Coach, a world-class career mentor specializing in tech careers. "
    "Help users with resume writing, ATS optimization, interview preparation, career guidance, "
    "skill gap analysis, learning roadmaps, and salary negotiation. "
    "Always provide professional, structured, actionable advice with concrete examples. "
    "Use markdown formatting (bold, bullet points) for clarity."
)


# ─────────────────────────────────────────────
# OFFLINE FALLBACK RESPONSES
# ─────────────────────────────────────────────

def _offline_response(user_message: str) -> str:
    """Keyword-based career advice when no AI is available."""
    m = user_message.lower()
    company = session.get('company', '')
    missing = session.get('missing_skills', [])
    score = session.get('score')

    if any(k in m for k in ['ats', 'applicant tracking', 'keyword']):
        return (
            "**ATS Optimization Tips**\n\n"
            "- Use a single-column layout with standard section headings\n"
            "- Mirror the exact keywords from the job description\n"
            "- Include both acronyms and full forms (e.g., ML / Machine Learning)\n"
            "- Add a dedicated Technical Skills section near the top\n"
            "- Quantify every achievement (e.g., 'Improved speed by 40%')\n\n"
            "**Quick Win:** Run your resume through jobscan.co for instant scoring."
        )
    elif any(k in m for k in ['resume', 'cv']):
        return (
            "**Resume Improvement Checklist**\n\n"
            "**Structure (5 key sections in order):**\n"
            "1. Contact info + LinkedIn URL\n2. Professional Summary (3–4 lines)\n"
            "3. Technical Skills (grouped by category)\n4. Work Experience (reverse chronological)\n"
            "5. Projects, Education, Certifications\n\n"
            "**For each bullet, use:** *Action Verb + What you did + Impact/Result*\n"
            "✓ *'Optimized database queries, reducing page load time by 52%'*"
        )
    elif any(k in m for k in ['interview', 'prepare', 'preparation']):
        return (
            "**Interview Preparation Strategy**\n\n"
            "- Revise DSA: aim for 2 LeetCode problems/day\n"
            "- Prepare 8–10 STAR behavioral stories\n"
            "- Do 2 mock interviews per week (Pramp, Interviewing.io)\n"
            "- Research the company: products, tech stack, recent news\n"
            "- Prepare 5 thoughtful questions to ask the interviewer"
        )
    elif any(k in m for k in ['salary', 'negotiate', 'offer', 'ctc']):
        return (
            "**Salary Negotiation Tips**\n\n"
            "- Research market rates on Glassdoor, Levels.fyi, AmbitionBox\n"
            "- Never accept on the spot — ask for 2 days to review\n"
            "- Counter with data: cite market research and your specific skills\n"
            "- Negotiate beyond base: joining bonus, ESOPs, remote flexibility\n"
            "- The person who speaks first often loses — stay patient"
        )
    elif any(k in m for k in ['roadmap', 'learn', 'skill', 'path']):
        return (
            "**Learning Roadmap Advice**\n\n"
            "- Pick one skill and go deep before expanding\n"
            "- Use the **Learning Roadmap** section in this app for a structured plan\n"
            "- Dedicate 1–2 hours daily to consistent practice\n"
            "- Build projects alongside — theory without practice won't stick\n"
            "- Certifications add credibility: AWS, Google, Meta courses on Coursera"
        )
    elif score is not None and missing:
        return (
            f"**Your Career Profile Summary**\n\n"
            f"Your ATS score is **{score}%** for **{company}** with **{len(missing)} skill gap(s)**: "
            f"{', '.join(missing[:4])}{'...' if len(missing) > 4 else ''}.\n\n"
            f"**Priority Actions:**\n"
            f"1. Bridge **{missing[0]}** first — it likely has the highest demand\n"
            f"2. Add 2–3 quantified achievements to each resume bullet\n"
            f"3. Start company-specific interview prep in the Mock Interview section"
        )
    else:
        return (
            "**Welcome! Here's How I Can Help**\n\n"
            "- 📄 **Resume Writing** — ATS optimization, STAR bullets, summaries\n"
            "- 🏢 **Company Prep** — Google, Amazon, Microsoft, Meta, TCS & more\n"
            "- 💻 **Technical Interviews** — DSA, System Design, LLD patterns\n"
            "- 🎤 **Behavioral Interviews** — STAR method, company values\n"
            "- 💰 **Salary Negotiation** — How to counter-offer effectively\n"
            "- 🚀 **Career Transitions** — Fresher advice, domain switching\n\n"
            "Try asking: *'How do I prepare for a Google system design interview?'*\n\n"
            "> ⚠️ **Note:** AI is currently in offline mode. Configure your Gemini API key in Settings for full AI responses."
        )


# ─────────────────────────────────────────────
# /chat ENDPOINT
# ─────────────────────────────────────────────

@chatbot_bp.route('/chat', methods=['POST'])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = data.get('message', '').strip()

    # --- Input validation ---
    if not user_message:
        return Response(
            json.dumps({'response': 'Please enter a message to continue.', 'error': 'empty_message'}),
            content_type='application/json',
            status=400
        )

    if len(user_message) > MAX_MESSAGE_LENGTH:
        return Response(
            json.dumps({'response': f'Message is too long. Please keep it under {MAX_MESSAGE_LENGTH} characters.', 'error': 'message_too_long'}),
            content_type='application/json',
            status=400
        )

    # --- Session context ---
    chat_history = session.get('chat_history', [])
    # Bound history to last 20 messages to avoid session bloat
    if len(chat_history) > 20:
        chat_history = chat_history[-20:]

    ats_score = session.get('score')
    resume_text = session.get('resume_text', '')
    skills = session.get('matched_skills', [])
    missing_skills = session.get('missing_skills', [])
    company = session.get('company', '')

    # Build the enriched context message (only for first turn to avoid repetition)
    context_message = build_context_message(
        message=user_message,
        ats_score=ats_score,
        resume_text=resume_text if len(chat_history) == 0 else None,  # only inject resume on first message
        skills=skills,
        missing_skills=missing_skills,
        company=company,
    )

    reply_text = None

    # ─── 1. GEMINI 2.5 FLASH (PRIMARY) ───
    gemini_client = get_gemini_client(session)
    if gemini_client:
        try:
            reply_text = chat_with_gemini(
                client=gemini_client,
                chat_history=chat_history,
                message=user_message,
                context_message=context_message,
            )
            print('[INFO] Chat response generated via Gemini 2.5 Flash.')
        except Exception as e:
            print(f'[ERROR] Gemini 2.5 Flash chat failed: {e}. Falling back to OpenAI.')
            reply_text = None

    # ─── 2. OPENAI GPT-4O-MINI (SECONDARY) ───
    if reply_text is None:
        openai_client = _get_openai_client()
        if openai_client:
            try:
                messages = [{'role': 'system', 'content': OPENAI_SYSTEM_PROMPT}]
                for msg in chat_history:
                    role = 'user' if msg['role'] == 'user' else 'assistant'
                    messages.append({'role': role, 'content': msg['text']})
                # First message gets context, subsequent messages don't
                send_text = context_message if len(chat_history) == 0 else user_message
                messages.append({'role': 'user', 'content': send_text})

                response = openai_client.chat.completions.create(
                    model='gpt-4o-mini',
                    messages=messages,
                    max_tokens=1500,
                )
                reply_text = response.choices[0].message.content
                print('[INFO] Chat response generated via OpenAI GPT-4o-mini.')
            except Exception as e:
                print(f'[ERROR] OpenAI chat failed: {e}. Falling back to offline.')
                reply_text = None

    # ─── 3. OFFLINE KEYWORD FALLBACK ───
    if reply_text is None:
        reply_text = _offline_response(user_message)
        print('[INFO] Chat response generated via offline keyword heuristics.')

    # --- Save to session history ---
    chat_history.append({'role': 'user', 'text': user_message})
    chat_history.append({'role': 'assistant', 'text': reply_text})
    session['chat_history'] = chat_history

    return Response(
        json.dumps({'response': reply_text}),
        content_type='application/json'
    )
