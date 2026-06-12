# 🚀 CareerBoost AI

CareerBoost AI is an AI-powered career preparation platform designed to help students and job seekers improve their resumes, identify skill gaps, prepare for interviews, and build personalized learning roadmaps.

The platform combines Natural Language Processing (NLP), Large Language Models (LLMs), and resume analytics to provide actionable career guidance.

---

## ✨ Features

### 📄 Resume Analysis

* Upload PDF resumes
* Extract resume content automatically
* Analyze strengths and weaknesses
* Identify missing skills

### 🎯 ATS Score Evaluation

* Generate Applicant Tracking System (ATS) scores
* Match resumes against industry requirements
* Provide optimization recommendations

### 🗺️ Personalized Learning Roadmaps

* Generate custom learning paths
* Recommend skills and technologies
* Create structured career growth plans

### 🤖 AI Career Coach

* Interactive career guidance chatbot
* Career planning assistance
* Resume improvement suggestions
* Technical learning recommendations

### 🎤 Interview Intelligence

* Company-specific interview preparation
* Frequently asked interview questions
* Technical and HR interview guidance

---

## 🛠️ Technology Stack

### Backend

* Python
* Flask

### Artificial Intelligence

* OpenAI GPT-4o-mini
* Google Gemini 1.5 Flash
* NLP Processing

### NLP Libraries

* spaCy
* NLTK

### Resume Processing

* pdfplumber

### Frontend

* HTML5
* CSS3
* JavaScript
* Jinja2 Templates

### Data Storage

* JSON-based datasets

---

## 🔄 AI Fallback Architecture

The application uses a multi-layer AI architecture:

OpenAI GPT-4o-mini
↓
Google Gemini 1.5 Flash
↓
Local Offline Heuristics

This ensures the platform continues functioning even when external AI services are unavailable.

---

## 📂 Project Structure

careerboost-ai/

├── static/

│ ├── style.css

│ └── script.js

├── templates/

│ ├── base.html

│ ├── index.html

│ ├── dashboard.html

│ ├── roadmap.html

│ ├── chat.html

│ └── interview.html

├── data/

│ ├── skills.json

│ ├── roadmap.json

│ └── interview_questions.json

├── app.py

├── requirements.txt

└── README.md

---

## 🚀 Installation

### Clone Repository

git clone https://github.com/FredKom7/CareerBoost-AI.git

cd CareerBoost-AI

### Create Virtual Environment

python -m venv venv

### Activate Environment

Windows:

venv\Scripts\activate

Linux/macOS:

source venv/bin/activate

### Install Dependencies

pip install -r requirements.txt

### Run Application

python app.py

---

## 🎯 Future Enhancements

* AI Mock Interviews
* Resume Builder
* Job Recommendation System
* Career Analytics Dashboard
* Resume Version Tracking
* Placement Prediction Engine

---

⭐ If you find this project useful, consider giving it a star.
