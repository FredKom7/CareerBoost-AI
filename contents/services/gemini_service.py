"""
services/gemini_service.py

Encapsulates all Gemini 2.5 Flash interactions for CareerBoost AI.
Handles client creation, system prompts, context injection, and chat sessions.
"""

import os
from google import genai
from google.genai import types


# ─────────────────────────────────────────────
# CLIENT
# ─────────────────────────────────────────────

def get_gemini_client(session=None):
    """
    Returns a Gemini genai.Client, preferring session key → env var.
    Returns None if no key is available.
    """
    # 1. Session key (set via UI settings page)
    if session:
        try:
            session_key = session.get('gemini_api_key')
            if session_key:
                return genai.Client(api_key=session_key)
        except Exception:
            pass

    # 2. Environment variable (loaded from .env by python-dotenv)
    env_key = os.environ.get('GEMINI_API_KEY')
    if env_key:
        try:
            return genai.Client(api_key=env_key)
        except Exception:
            pass

    return None


# ─────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────

CAREER_COACH_SYSTEM_PROMPT = """You are CareerBoost AI Coach — a world-class, highly experienced career mentor specializing in tech careers.

Your job is to help students and job seekers with:
- Resume writing and ATS optimization
- Interview preparation (technical + behavioral)
- Career guidance and goal setting
- Skill gap analysis and learning plans
- Learning roadmaps with timelines and resources
- Company-specific preparation (Google, Amazon, Microsoft, Meta, TCS, Infosys, etc.)
- Placement and internship guidance
- Salary negotiation strategies
- Career transitions and switching domains

Always provide:
- Professional, encouraging, and actionable advice
- Clear explanations with concrete examples
- Structured responses using markdown (bold headers, bullet points)
- Specific resources, tools, and next steps
- Honest assessments without being discouraging

Keep all answers relevant to careers and education. Be concise yet comprehensive.
If context about the user's resume, ATS score, or skills is provided, use it to give personalized, specific advice.
"""


# ─────────────────────────────────────────────
# CONTEXT BUILDER
# ─────────────────────────────────────────────

def build_context_message(message: str, ats_score=None, resume_text=None, skills=None, missing_skills=None, company=None) -> str:
    """
    Enriches the user message with available session context so the AI
    can give personalized, resume-aware responses.
    """
    context_parts = []

    if ats_score is not None:
        context_parts.append(f"ATS Score: {ats_score}%")

    if company:
        context_parts.append(f"Target Company: {company}")

    if skills:
        skills_str = ', '.join(skills[:15]) if isinstance(skills, list) else str(skills)
        context_parts.append(f"Detected Skills: {skills_str}")

    if missing_skills:
        missing_str = ', '.join(missing_skills[:10]) if isinstance(missing_skills, list) else str(missing_skills)
        context_parts.append(f"Missing Skills (Skill Gaps): {missing_str}")

    if resume_text and len(resume_text.strip()) > 50:
        # Truncate resume to avoid token overflow (first 3000 chars is sufficient for context)
        truncated = resume_text.strip()[:3000]
        if len(resume_text.strip()) > 3000:
            truncated += "\n[Resume truncated for brevity...]"
        context_parts.append(f"Resume Content:\n{truncated}")

    if context_parts:
        context_block = "\n".join(context_parts)
        return (
            f"[USER PROFILE CONTEXT]\n{context_block}\n\n"
            f"[USER QUESTION]\n{message}"
        )

    return message


# ─────────────────────────────────────────────
# CHAT
# ─────────────────────────────────────────────

def chat_with_gemini(client, chat_history: list, message: str, context_message: str) -> str:
    """
    Sends a message to Gemini 2.5 Flash using a stateful chat session with history.

    Args:
        client:          genai.Client instance
        chat_history:    List of {'role': 'user'|'assistant', 'text': str} dicts (from session)
        message:         The raw user message (stored in history)
        context_message: The enriched message with context (sent to AI)

    Returns:
        The AI response string.

    Raises:
        Exception on API failure (caller handles fallback).
    """
    # Convert session history to Gemini Content objects
    history_contents = []
    for msg in chat_history:
        role = 'user' if msg['role'] == 'user' else 'model'
        history_contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg['text'])]
            )
        )

    # Create chat session with system instruction and history
    chat_session = client.chats.create(
        model='gemini-2.5-flash',
        config=types.GenerateContentConfig(
            system_instruction=CAREER_COACH_SYSTEM_PROMPT,
            temperature=0.7,
            max_output_tokens=2048,
        ),
        history=history_contents
    )

    # Send enriched context message (first turn gets full context; subsequent turns get plain message)
    send_text = context_message if len(chat_history) == 0 else message
    response = chat_session.send_message(send_text)
    return response.text


# ─────────────────────────────────────────────
# MOCK INTERVIEW HELPER
# ─────────────────────────────────────────────

def generate_interview_question(client, company: str, role: str = 'Software Engineer') -> str:
    """
    Generates a single targeted interview question for mock interview mode.
    """
    prompt = (
        f"You are conducting a mock interview for a {role} role at {company}. "
        f"Ask ONE specific, realistic interview question. "
        f"Make it either technical (DSA/System Design) or behavioral depending on what's more relevant. "
        f"Just ask the question — no preamble, no explanation."
    )
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.8, max_output_tokens=256)
    )
    return response.text.strip()
