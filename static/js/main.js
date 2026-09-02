/* Поведение интерфейса: меню, анимации, фильтры, форма, события аналитики. */

(function () {
  "use strict";

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function track(eventName, payload) {
    const detail = Object.assign({ event: eventName }, payload || {});
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push(detail);
    if (typeof window.st8domAnalytics === "function") {
      window.st8domAnalytics(eventName, payload || {});
    }
  }
  window.st8domTrack = track;

  document.querySelectorAll("[data-track]").forEach(function (el) {
    el.addEventListener("click", function () {
      track(el.getAttribute("data-track"), {
        href: el.getAttribute("href") || "",
        id: el.id || "",
      });
    });
  });

  const toggle = document.querySelector(".nav-toggle");
  const links = document.querySelector(".nav-links");
  if (toggle && links) {
    toggle.addEventListener("click", function () {
      const open = links.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    links.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () {
        links.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
      });
    });
  }

  if (!reduced) {
    const els = document.querySelectorAll(".reveal");
    if ("IntersectionObserver" in window) {
      const io = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (e) {
            if (e.isIntersecting) {
              const d = +(e.target.dataset.d || 0);
              setTimeout(function () {
                e.target.classList.add("visible");
              }, d * 80);
              io.unobserve(e.target);
            }
          });
        },
        { threshold: 0.12 }
      );
      els.forEach(function (el) {
        io.observe(el);
      });
    } else {
      els.forEach(function (el) {
        el.classList.add("visible");
      });
    }
  } else {
    document.querySelectorAll(".reveal").forEach(function (el) {
      el.classList.add("visible");
    });
  }

  document.querySelectorAll(".faq details").forEach(function (item) {
    item.addEventListener("toggle", function () {
      if (item.open) {
        const q = item.querySelector("summary");
        track("faq_open", { question: q ? q.textContent.trim() : "" });
      }
    });
  });

  const filters = document.querySelectorAll("[data-filter]");
  const cards = document.querySelectorAll("[data-tags]");
  filters.forEach(function (btn) {
    btn.addEventListener("click", function () {
      filters.forEach(function (b) {
        b.classList.remove("is-active");
        b.setAttribute("aria-pressed", "false");
      });
      btn.classList.add("is-active");
      btn.setAttribute("aria-pressed", "true");
      const value = btn.getAttribute("data-filter");
      cards.forEach(function (card) {
        const tags = (card.getAttribute("data-tags") || "").split(/\s+/);
        const show = value === "all" || tags.indexOf(value) !== -1;
        card.classList.toggle("case-hidden", !show);
      });
    });
  });

  const form = document.querySelector("#inquiry-form");
  if (form) {
    let started = false;
    form.addEventListener(
      "input",
      function () {
        if (!started) {
          started = true;
          track("contact_form_start");
        }
      },
      { once: false }
    );
    form.addEventListener("submit", function () {
      const btn = form.querySelector("[type=submit]");
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Отправляю…";
      }
      const status = form.querySelector(".form-status");
      if (status) status.textContent = "Отправляю заявку…";
      track("contact_form_submit");
    });
  }

  document.querySelectorAll(".case-video video").forEach(function (video) {
    video.addEventListener("play", function onFirstPlay() {
      if (video.muted) video.muted = false;
      if (video.volume === 0) video.volume = 1;
      video.removeEventListener("play", onFirstPlay);
    });
  });

  const canvas = document.getElementById("avatarCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width;
  const H = canvas.height;
  const img = new Image();
  img.crossOrigin = "anonymous";
  img.src = canvas.getAttribute("data-src") || "";

  img.onload = function () {
    const aspect = img.naturalWidth / img.naturalHeight;
    let sx = 0,
      sy = 0,
      sw = img.naturalWidth,
      sh = img.naturalHeight;
    if (aspect > 1) {
      sw = img.naturalHeight;
      sx = (img.naturalWidth - sw) / 2;
    } else if (aspect < 1) {
      sh = img.naturalWidth;
      sy = (img.naturalHeight - sh) / 2;
    }
    ctx.drawImage(img, sx, sy, sw, sh, 0, 0, W, H);
    const data = ctx.getImageData(0, 0, W, H);
    const d = data.data;
    const mask = new Uint8Array(W * H);

    function isBg(r, g, b) {
      const mx = Math.max(r, g, b),
        mn = Math.min(r, g, b),
        l = (mx + mn) / 2;
      const s =
        mx === mn ? 0 : l > 127 ? (mx - mn) / (510 - mx - mn) : (mx - mn) / (mx + mn);
      return (l > 160 && s < 0.18) || (l > 130 && s < 0.1);
    }
    const queue = [];
    function enq(x, y) {
      const i = y * W + x;
      if (!mask[i]) {
        mask[i] = 1;
        queue.push(i);
      }
    }
    for (let x = 0; x < W; x++) {
      enq(x, 0);
      enq(x, H - 1);
    }
    for (let y = 0; y < H; y++) {
      enq(0, y);
      enq(W - 1, y);
    }
    let qi = 0;
    while (qi < queue.length) {
      const idx = queue[qi++];
      const x = idx % W;
      const y = (idx / W) | 0;
      const p = idx * 4;
      if (!isBg(d[p], d[p + 1], d[p + 2])) {
        mask[idx] = 0;
        continue;
      }
      [
        [x - 1, y],
        [x + 1, y],
        [x, y - 1],
        [x, y + 1],
      ].forEach(function (n) {
        if (n[0] >= 0 && n[0] < W && n[1] >= 0 && n[1] < H) enq(n[0], n[1]);
      });
    }
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const idx = y * W + x;
        const p = idx * 4;
        if (mask[idx]) d[p + 3] = 0;
        else {
          const e = Math.min(x, W - 1 - x, y, H - 1 - y, 8) / 8;
          d[p + 3] = Math.round(d[p + 3] * e);
        }
      }
    }
    for (let i = 0; i < d.length; i += 4) {
      if (d[i + 3] > 0) {
        d[i] = Math.min(255, d[i] * 0.88);
        d[i + 1] = Math.min(255, d[i + 1] * 0.93);
        d[i + 2] = Math.min(255, d[i + 2] * 1.08);
      }
    }
    ctx.putImageData(data, 0, 0);
  };

  img.onerror = function () {
    ctx.fillStyle = "#1a2235";
    ctx.beginPath();
    ctx.arc(W / 2, H / 2, W / 2 - 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#818CF8";
    ctx.font = "bold 80px Inter,sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("ДС", W / 2, H / 2);
  };
})();
