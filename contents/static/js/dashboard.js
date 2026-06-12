const pieCtx = document.getElementById("skillsPie");
const barCtx = document.getElementById("missingSkillsBar");
const dashboardDataNode = document.getElementById("dashboardData");
const dashboardPayload = dashboardDataNode ? JSON.parse(dashboardDataNode.textContent) : {};
const analysis = dashboardPayload.analysis || {};
const company = dashboardPayload.company || "target company";
const missingSkillWeights = analysis.missing_skill_weights || {};
const missingSkills = analysis.missing_skills || [];

Chart.defaults.color = "#a1a1aa";
Chart.defaults.font.family = "'Inter', sans-serif";

if (pieCtx) {
  const skillMatch = analysis.skill_match_pct || 0;
  const skillGap = Math.max(100 - skillMatch, 0);
  new Chart(pieCtx, {
    type: "doughnut",
    data: {
      labels: ["Matched", "Gap"],
      datasets: [{
        data: [skillMatch, skillGap],
        backgroundColor: ["#6366f1", "rgba(255, 255, 255, 0.05)"],
        hoverBackgroundColor: ["#818cf8", "rgba(255, 255, 255, 0.1)"],
        borderWidth: 0,
        weight: 0.5
      }]
    },
    options: {
      cutout: "80%",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { padding: 20, usePointStyle: true } }
      }
    }
  });
}

if (barCtx) {
  const missingLabels = Object.keys(missingSkillWeights).slice(0, 6);
  const missingValues = missingLabels.map((label) => missingSkillWeights[label]);
  
  new Chart(barCtx, {
    type: "bar",
    data: {
      labels: missingLabels.length ? missingLabels.map(l => l.toUpperCase()) : ["READY"],
      datasets: [{
        label: "Impact Score",
        data: missingValues.length ? missingValues : [0],
        backgroundColor: "rgba(168, 85, 247, 0.6)",
        hoverBackgroundColor: "#a855f7",
        borderRadius: 10,
        barThickness: 20
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { 
          beginAtZero: true, 
          max: 100,
          grid: { color: "rgba(255,255,255,0.05)", drawBorder: false },
          ticks: { stepSize: 20 }
        },
        x: { grid: { display: false, drawBorder: false } }
      },
      plugins: { legend: { display: false } }
    }
  });
}

async function appendChatBubble(text, type) {
  const wrap = document.getElementById("assistantChat");
  if (!wrap) return;
  
  const bubble = document.createElement("div");
  bubble.className = `bubble ${type}`;
  wrap.appendChild(bubble);
  
  if (type === "ai") {
    bubble.classList.add("typing");
    let i = 0;
    const speed = 15;
    function typeWriter() {
      if (i < text.length) {
        bubble.textContent += text.charAt(i);
        i++;
        wrap.scrollTop = wrap.scrollHeight;
        setTimeout(typeWriter, speed);
      } else {
        bubble.classList.remove("typing");
      }
    }
    typeWriter();
  } else {
    bubble.textContent = text;
    wrap.scrollTop = wrap.scrollHeight;
  }
}

const assistantInput = document.getElementById("assistantInput");
const assistantSend = document.getElementById("assistantSend");
if (assistantInput && assistantSend) {
  const sendMessage = async () => {
    const message = assistantInput.value.trim();
    if (!message) return;
    appendChatBubble(message, "user");
    assistantInput.value = "";
    try {
      const response = await fetch("/api/assistant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, company, missing_skills: missingSkills })
      });
      const data = await response.json();
      setTimeout(() => appendChatBubble(data.reply || "I'm processing that information...", "ai"), 500);
    } catch {
      appendChatBubble("My neural links are down. Please try again in a moment.", "ai");
    }
  };
  assistantSend.addEventListener("click", sendMessage);
  assistantInput.addEventListener("keypress", (e) => { if(e.key === "Enter") sendMessage(); });

  document.querySelectorAll('.prompt-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      assistantInput.value = chip.textContent;
      sendMessage();
    });
  });
}

// Interview Logic
let questionIndex = 0;
const nextQuestionBtn = document.getElementById("nextQuestionBtn");
const evaluateAnswerBtn = document.getElementById("evaluateAnswerBtn");
const mockQuestionEl = document.getElementById("mockQuestion");
const questionTypeEl = document.getElementById("questionType");
const mockAnswerEl = document.getElementById("mockAnswer");

if (nextQuestionBtn) {
  nextQuestionBtn.addEventListener("click", async () => {
    nextQuestionBtn.disabled = true;
    nextQuestionBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    try {
      const response = await fetch("/api/mock-interviewer/question", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category: questionTypeEl.value, index: questionIndex })
      });
      const data = await response.json();
      mockQuestionEl.style.opacity = 0;
      setTimeout(() => {
        mockQuestionEl.textContent = data.question;
        mockQuestionEl.style.opacity = 1;
        nextQuestionBtn.disabled = false;
        nextQuestionBtn.textContent = "Next Question";
      }, 300);
      questionIndex = data.index || 0;
    } catch {
      nextQuestionBtn.disabled = false;
      nextQuestionBtn.textContent = "Try Again";
    }
  });
}

if (evaluateAnswerBtn) {
  evaluateAnswerBtn.addEventListener("click", async () => {
    const answer = mockAnswerEl.value.trim();
    const question = mockQuestionEl.textContent.trim();
    if (!answer || question.includes("Click")) return;

    evaluateAnswerBtn.disabled = true;
    evaluateAnswerBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Evaluating...';

    try {
      const response = await fetch("/api/mock-interviewer/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, answer })
      });
      const data = await response.json();
      const evalBox = document.getElementById("mockEvaluation");
      evalBox.style.display = "block";
      document.getElementById("confidenceScore").textContent = `${data.confidence_score}%`;
      document.getElementById("communicationLevel").textContent = data.communication_level;
      document.getElementById("technicalScore").textContent = `${data.technical_score}%`;
      
      const feedbackEl = document.getElementById("evaluationFeedback");
      feedbackEl.innerHTML = "";
      (data.feedback || []).forEach((item) => {
        const li = document.createElement("li");
        li.textContent = item;
        feedbackEl.appendChild(li);
      });
      evaluateAnswerBtn.disabled = false;
      evaluateAnswerBtn.textContent = "Analyze Answer";
    } catch {
      evaluateAnswerBtn.disabled = false;
      evaluateAnswerBtn.textContent = "Retry Analysis";
    }
  });
}
