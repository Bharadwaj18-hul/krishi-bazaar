/* ============================================================
   KRISHI BAZAAR — LUXURY ANIMATION & INTERACTION ENGINE
   ============================================================ */

/* ── Page Fade-In on Load ────────────────────────────────── */
(function () {
  document.body.style.opacity = "0";
  document.body.style.transition = "opacity 0.4s ease";
  window.addEventListener("load", () => {
    document.body.style.opacity = "1";
  });
})();

document.addEventListener("DOMContentLoaded", () => {

  /* ── 1. Auto-add form-control class ─────────────────────── */
  document.querySelectorAll("input, select, textarea").forEach(el => {
    if (!el.classList.contains("form-control") && el.type !== "checkbox" && el.type !== "file") {
      el.classList.add("form-control");
    }
  });

  /* ── 2. Scroll-reveal: elements slide up + fade in ──────── */
  const revealEls = document.querySelectorAll(
    ".lux-card, .lux-pillar, .lux-metric-card, .lux-filter-card, .lux-table-card, .lux-pillar-strip, .lux-auth-card, .lux-detail-card"
  );

  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting) {
          e.target.classList.add("lux-revealed");
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.08 });

    revealEls.forEach(el => {
      el.classList.add("lux-will-reveal");
      io.observe(el);
    });
  } else {
    revealEls.forEach(el => el.classList.add("lux-revealed"));
  }

  /* ── 3. Stagger product cards on load ─────────────────────*/
  document.querySelectorAll(".lux-card").forEach((card, i) => {
    card.style.animationDelay = `${i * 80}ms`;
  });

  /* ── 4. Navbar shrink on scroll ────────────────────────── */
  const navbar = document.querySelector(".lux-navbar");
  const progressBar = document.getElementById("lux-scroll-progress");
  if (navbar || progressBar) {
    const onScroll = () => {
      // Navbar shrink
      if (navbar) {
        navbar.classList.toggle("lux-navbar-shrunk", window.scrollY > 60);
      }
      // Scroll progress bar
      if (progressBar) {
        const scrolled = window.scrollY;
        const docH = document.documentElement.scrollHeight - window.innerHeight;
        progressBar.style.width = docH > 0 ? (scrolled / docH * 100) + "%" : "0%";
      }
    };
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  /* ── 5. Gold button ripple effect ──────────────────────── */
  document.querySelectorAll(".btn-gold, .btn-gold-outline, .btn-forest").forEach(btn => {
    btn.addEventListener("click", function (e) {
      const ripple = document.createElement("span");
      ripple.classList.add("lux-ripple");
      const rect = this.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height);
      ripple.style.cssText = `
        width: ${size}px; height: ${size}px;
        left: ${e.clientX - rect.left - size / 2}px;
        top: ${e.clientY - rect.top - size / 2}px;
      `;
      this.style.position = "relative";
      this.style.overflow = "hidden";
      this.appendChild(ripple);
      setTimeout(() => ripple.remove(), 620);
    });
  });

  /* ── 6. Hero text typewriter on homepage ───────────────── */
  const heroTitle = document.querySelector(".lux-hero-title");
  if (heroTitle) {
    heroTitle.classList.add("lux-hero-animate");
  }

  /* ── 7. Category chip scroll indicator (mobile) ─────────── */
  const catScroll = document.querySelector(".lux-category-scroll");
  if (catScroll) {
    catScroll.addEventListener("scroll", () => {
      const atEnd = catScroll.scrollLeft + catScroll.clientWidth >= catScroll.scrollWidth - 10;
      catScroll.classList.toggle("lux-scroll-end", atEnd);
    }, { passive: true });
  }

  /* ── 8. Smooth anchor scrolling ───────────────────────── */
  document.querySelectorAll("a[href^='#']").forEach(a => {
    a.addEventListener("click", e => {
      const target = document.querySelector(a.getAttribute("href"));
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });

  /* ── 9. Auto-dismiss alerts after 5 seconds ───────────── */
  document.querySelectorAll(".alert.fade.show").forEach(alert => {
    setTimeout(() => {
      alert.classList.remove("show");
      setTimeout(() => alert.remove(), 300);
    }, 5000);
  });

  /* ── 10. Number count-up animation for metric values ───── */
  document.querySelectorAll(".lux-metric-val").forEach(el => {
    const raw = el.textContent.trim();
    const num = parseFloat(raw.replace(/[^0-9.]/g, ""));
    const prefix = raw.match(/^[^\d]*/)?.[0] || "";
    const suffix = raw.replace(/^[^\d]*[\d,.]+/, "");
    if (!isNaN(num) && num > 0) {
      let current = 0;
      const steps = 40;
      const increment = num / steps;
      const timer = setInterval(() => {
        current = Math.min(current + increment, num);
        el.textContent = prefix + (Number.isInteger(num) ? Math.round(current) : current.toFixed(0)) + suffix;
        if (current >= num) clearInterval(timer);
      }, 30);
    }
  });

  /* ── 11. Floating particle canvas for auth pages ──────── */
  const canvas = document.getElementById("lux-auth-particles");
  if (canvas) {
    initParticles(canvas);
  }
});


/* ── Particle System for Auth Pages ────────────────────────── */
function initParticles(canvas) {
  const ctx = canvas.getContext("2d");

  function resize() {
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;
  }
  resize();
  window.addEventListener("resize", resize, { passive: true });

  const particles = Array.from({ length: 38 }, () => ({
    x: Math.random() * canvas.width,
    y: Math.random() * canvas.height,
    r: Math.random() * 1.8 + 0.4,
    vx: (Math.random() - 0.5) * 0.35,
    vy: (Math.random() - 0.5) * 0.35,
    alpha: Math.random() * 0.5 + 0.15
  }));

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw connecting lines
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 110) {
          ctx.beginPath();
          ctx.strokeStyle = `rgba(212, 175, 55, ${0.12 * (1 - dist / 110)})`;
          ctx.lineWidth = 0.6;
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.stroke();
        }
      }
    }

    // Draw particles
    particles.forEach(p => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(212, 175, 55, ${p.alpha})`;
      ctx.fill();

      p.x += p.vx;
      p.y += p.vy;

      if (p.x < 0 || p.x > canvas.width) p.vx *= -1;
      if (p.y < 0 || p.y > canvas.height) p.vy *= -1;
    });

    requestAnimationFrame(draw);
  }

  draw();
}
