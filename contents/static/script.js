// Smoothly scroll to anchors for better UX.
document.querySelectorAll('a[href^="#"]').forEach((link) => {
  link.addEventListener("click", (event) => {
    const id = link.getAttribute("href");
    const target = id ? document.querySelector(id) : null;
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
});

// Show selected file name under the input.
const resumeInput = document.getElementById("resume");
const preview = document.getElementById("filePreview");
if (resumeInput && preview) {
  resumeInput.addEventListener("change", () => {
    if (!resumeInput.files || resumeInput.files.length === 0) {
      preview.textContent = "No file selected.";
      return;
    }
    preview.textContent = `Selected: ${resumeInput.files[0].name}`;
  });
}

// Add loading state when user submits the upload form.
const form = document.getElementById("resumeForm");
const analyzeBtn = document.getElementById("analyzeBtn");
if (form && analyzeBtn) {
  form.addEventListener("submit", () => {
    analyzeBtn.classList.add("loading");
    analyzeBtn.disabled = true;
  });
}

// Reveal cards/sections as they enter viewport.
const revealEls = document.querySelectorAll(".reveal");
const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("show");
      }
    });
  },
  { threshold: 0.2 }
);
revealEls.forEach((el) => observer.observe(el));

// Tiny hover glow movement for cards.
document.querySelectorAll(".card").forEach((card) => {
  card.addEventListener("mousemove", (event) => {
    const rect = card.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    card.style.background = `radial-gradient(circle at ${x}px ${y}px, rgba(255,255,255,0.06), rgba(255,255,255,0.02))`;
  });
  card.addEventListener("mouseleave", () => {
    card.style.background = "rgba(255, 255, 255, 0.02)";
  });
});

// Initialize particles.js if the container exists
if (document.getElementById('particles-js')) {
  particlesJS("particles-js", {
    "particles": {
      "number": {
        "value": 50,
        "density": {
          "enable": true,
          "value_area": 800
        }
      },
      "color": {
        "value": ["#6366f1", "#a855f7", "#ec4899"]
      },
      "shape": {
        "type": "circle"
      },
      "opacity": {
        "value": 0.3,
        "random": true,
        "anim": {
          "enable": true,
          "speed": 1,
          "opacity_min": 0.1,
          "sync": false
        }
      },
      "size": {
        "value": 3,
        "random": true,
        "anim": {
          "enable": true,
          "speed": 1,
          "size_min": 0.1,
          "sync": false
        }
      },
      "line_linked": {
        "enable": true,
        "distance": 150,
        "color": "#6366f1",
        "opacity": 0.1,
        "width": 1
      },
      "move": {
        "enable": true,
        "speed": 1,
        "direction": "none",
        "random": true,
        "straight": false,
        "out_mode": "out",
        "bounce": false
      }
    },
    "interactivity": {
      "detect_on": "canvas",
      "events": {
        "onhover": {
          "enable": true,
          "mode": "grab"
        },
        "onclick": {
          "enable": true,
          "mode": "push"
        },
        "resize": true
      },
      "modes": {
        "grab": {
          "distance": 140,
          "line_linked": {
            "opacity": 0.3
          }
        },
        "push": {
          "particles_nb": 3
        }
      }
    },
    "retina_detect": true
  });
}
