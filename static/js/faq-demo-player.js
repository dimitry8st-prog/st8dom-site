/* Демо-ролик FAQ-ассистента: сцены, голос диктора и субтитры по его речи. */

(function () {
  "use strict";

  const root = document.querySelector("[data-faq-reel]");
  if (!root) return;

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const duration = Number(root.getAttribute("data-duration") || 40);
  const videoSrc = root.getAttribute("data-video-src") || "";
  const videoVerticalSrc = root.getAttribute("data-video-vertical-src") || "";
  const audioSrc = root.getAttribute("data-audio-src") || "";
  const voiceSrc = root.getAttribute("data-voice-src") || "";
  const captionsSrc = root.getAttribute("data-captions-src") || "";

  const poster = root.querySelector(".faq-reel__poster");
  const storyboard = root.querySelector(".faq-reel__storyboard");
  const scenes = Array.prototype.slice.call(root.querySelectorAll(".faq-scene"));
  const video = root.querySelector(".faq-reel__video");
  const captionBox = root.querySelector("[data-captions]");
  const timeBox = root.querySelector("[data-time]");
  const progressBar = root.querySelector(".faq-reel__progress");
  const progressFill = root.querySelector("[data-progress]");
  const playBtn = root.querySelector('[data-action="play"]');
  const stopBtn = root.querySelector('[data-action="stop"]');
  const muteBtn = root.querySelector('[data-action="mute"]');
  const captionBtn = root.querySelector('[data-action="captions"]');

  let cues = [];

  let music = null;
  let voice = null;
  let playing = false;
  let muted = false;
  let captionsOn = true;
  let startedAt = 0;
  let elapsed = 0;
  let raf = 0;
  let useVideo = false;
  let videoReady = false;

  function track(name, payload) {
    if (typeof window.st8domTrack === "function") {
      window.st8domTrack(name, payload || {});
      return;
    }
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push(Object.assign({ event: name }, payload || {}));
  }

  function parseTimestamp(stamp) {
    const clean = stamp.trim().split(/\s+/)[0];
    const bits = clean.split(":");
    if (bits.length === 3) {
      return Number(bits[0]) * 3600 + Number(bits[1]) * 60 + parseFloat(bits[2]);
    }
    if (bits.length === 2) {
      return Number(bits[0]) * 60 + parseFloat(bits[1]);
    }
    return parseFloat(clean) || 0;
  }

  function parseVtt(text) {
    const parsed = [];
    const blocks = text.replace(/\r/g, "").split(/\n\n+/);
    blocks.forEach(function (block) {
      const lines = block.split("\n").filter(function (line) {
        return line && line !== "WEBVTT" && line.indexOf("NOTE") !== 0;
      });
      const timeIndex = lines.findIndex(function (line) {
        return line.indexOf("-->") !== -1;
      });
      if (timeIndex === -1) return;
      const parts = lines[timeIndex].split("-->");
      const body = lines.slice(timeIndex + 1).join(" ").trim();
      if (!body) return;
      parsed.push({
        start: parseTimestamp(parts[0]),
        end: parseTimestamp(parts[1]),
        text: body,
      });
    });
    return parsed;
  }

  function formatTime(sec) {
    const total = Math.max(0, Math.min(duration, Math.floor(sec)));
    const m = Math.floor(total / 60);
    const s = total % 60;
    return m + ":" + String(s).padStart(2, "0");
  }

  function chooseVideoSrc() {
    const portrait =
      window.matchMedia("(max-width: 720px)").matches &&
      window.matchMedia("(orientation: portrait)").matches;
    if (portrait && videoVerticalSrc) return videoVerticalSrc;
    return videoSrc;
  }

  function nowTime() {
    if (voice && playing && !voice.paused && !voice.ended) {
      return voice.currentTime;
    }
    if (useVideo && video && playing && !video.paused) {
      return video.currentTime;
    }
    if (playing) {
      return (performance.now() - startedAt) / 1000;
    }
    return elapsed;
  }

  function activeCue(time) {
    let found = null;
    for (let i = 0; i < cues.length; i += 1) {
      if (time >= cues[i].start && time < cues[i].end) {
        found = cues[i];
      }
    }
    return found;
  }

  function setCaption(time) {
    if (!captionBox) return;
    if (!captionsOn) {
      captionBox.textContent = "";
      captionBox.hidden = true;
      return;
    }
    const cue = activeCue(time);
    captionBox.hidden = !cue;
    captionBox.textContent = cue ? cue.text : "";
  }

  function showScene(time) {
    scenes.forEach(function (scene) {
      const start = Number(scene.getAttribute("data-start"));
      const end = Number(scene.getAttribute("data-end"));
      scene.classList.toggle("is-active", time >= start && time < end);
    });
  }

  function musicGain(time) {
    if (!music) return;
    const speaking = Boolean(activeCue(time));
    let volume = speaking ? 0.07 : 0.1;
    const fadeIn = Math.min(1, time / 1);
    const fadeOut = time > duration - 2 ? Math.max(0, (duration - time) / 2) : 1;
    music.volume = muted ? 0 : volume * fadeIn * fadeOut;
  }

  function render(time) {
    elapsed = Math.max(0, Math.min(duration, time));
    if (timeBox) timeBox.textContent = formatTime(elapsed) + " / " + formatTime(duration);
    if (progressFill) progressFill.style.width = (elapsed / duration) * 100 + "%";
    if (progressBar) progressBar.setAttribute("aria-valuenow", String(Math.floor(elapsed)));
    setCaption(elapsed);
    if (!useVideo) showScene(elapsed);
    musicGain(elapsed);
  }

  function pauseMedia() {
    if (video) video.pause();
    if (music) music.pause();
    if (voice) voice.pause();
  }

  function playMediaFrom(time) {
    if (music) {
      music.currentTime = Math.min(time, isFinite(music.duration) ? music.duration : time);
      if (!muted) {
        const start = music.play();
        if (start && typeof start.catch === "function") start.catch(function () {});
      }
    }
    if (voice) {
      voice.currentTime = Math.min(time, isFinite(voice.duration) ? voice.duration : time);
      voice.muted = muted;
      if (!muted) {
        const start = voice.play();
        if (start && typeof start.catch === "function") start.catch(function () {});
      }
    }
  }

  function stopPlayback(reset) {
    playing = false;
    if (raf) {
      cancelAnimationFrame(raf);
      raf = 0;
    }
    if (!reset && voice) elapsed = voice.currentTime || elapsed;
    pauseMedia();
    if (reset) {
      if (video) video.currentTime = 0;
      if (music) {
        music.currentTime = 0;
        music.volume = 0;
      }
      if (voice) voice.currentTime = 0;
    }
    if (playBtn) playBtn.textContent = "Воспроизвести";
    if (reset) {
      elapsed = 0;
      render(0);
      if (poster) poster.hidden = false;
      if (storyboard) storyboard.hidden = true;
      if (video && !useVideo) video.hidden = true;
    }
  }

  function tick() {
    if (!playing) return;
    const time = nowTime();
    if (time >= duration) {
      render(duration);
      stopPlayback(false);
      track("faq_demo_complete");
      return;
    }
    render(time);
    raf = requestAnimationFrame(tick);
  }

  function startStoryboard() {
    useVideo = false;
    if (poster) poster.hidden = true;
    if (storyboard) storyboard.hidden = false;
    if (video) video.hidden = true;
    if (reduced) showScene(elapsed || 0);
    startedAt = performance.now() - elapsed * 1000;
    playing = true;
    if (playBtn) playBtn.textContent = "Пауза";
    playMediaFrom(elapsed);
    raf = requestAnimationFrame(tick);
  }

  function startVideo() {
    useVideo = true;
    if (poster) poster.hidden = true;
    if (storyboard) storyboard.hidden = true;
    video.hidden = false;
    video.muted = true;
    video.currentTime = elapsed;
    playMediaFrom(elapsed);
    const playPromise = video.play();
    function running() {
      playing = true;
      startedAt = performance.now() - elapsed * 1000;
      if (playBtn) playBtn.textContent = "Пауза";
      raf = requestAnimationFrame(tick);
    }
    if (playPromise && typeof playPromise.then === "function") {
      playPromise.then(running).catch(function () {
        startStoryboard();
      });
    } else {
      running();
    }
  }

  function prepareVideo() {
    if (!video || !(videoSrc || videoVerticalSrc)) return Promise.resolve(false);
    const src = chooseVideoSrc();
    if (!src) return Promise.resolve(false);
    if (videoReady && video.currentSrc) return Promise.resolve(true);
    return new Promise(function (resolve) {
      let settled = false;
      function done(ok) {
        if (settled) return;
        settled = true;
        videoReady = ok;
        resolve(ok);
      }
      video.addEventListener("loadeddata", function () { done(true); }, { once: true });
      video.addEventListener("error", function () { done(false); }, { once: true });
      if (!video.getAttribute("src") && !video.querySelector("source[src]")) {
        video.src = src;
      }
      video.preload = "metadata";
      video.load();
      setTimeout(function () { done(video.readyState >= 1); }, 2500);
    });
  }

  function togglePlay() {
    if (playing) {
      elapsed = nowTime();
      stopPlayback(false);
      if (playBtn) playBtn.textContent = "Продолжить";
      track("faq_demo_pause");
      return;
    }
    track("faq_demo_play", { mode: videoSrc ? "video-or-fallback" : "storyboard" });
    if (videoSrc || videoVerticalSrc) {
      prepareVideo().then(function (ok) {
        if (ok) startVideo();
        else startStoryboard();
      });
      return;
    }
    startStoryboard();
  }

  function stopAll() {
    stopPlayback(true);
    if (playBtn) playBtn.textContent = "Воспроизвести";
    track("faq_demo_stop");
  }

  function toggleMute() {
    muted = !muted;
    if (video) video.muted = true;
    if (voice) voice.muted = muted;
    if (muted) {
      if (music) music.pause();
      if (voice) voice.pause();
    } else if (playing) {
      playMediaFrom(nowTime());
    }
    musicGain(elapsed);
    if (muteBtn) {
      muteBtn.setAttribute("aria-pressed", muted ? "true" : "false");
      muteBtn.setAttribute("aria-label", muted ? "Включить звук" : "Выключить звук");
      muteBtn.textContent = muted ? "Без звука" : "Звук";
    }
    track("faq_demo_mute", { muted: muted });
  }

  function toggleCaptions() {
    captionsOn = !captionsOn;
    if (captionBtn) {
      captionBtn.classList.toggle("is-active", captionsOn);
      captionBtn.setAttribute("aria-pressed", captionsOn ? "true" : "false");
    }
    if (video && video.textTracks && video.textTracks[0]) {
      video.textTracks[0].mode = captionsOn ? "showing" : "hidden";
    }
    setCaption(elapsed);
  }

  function attachAudio(src, onError) {
    const el = new Audio();
    el.preload = "metadata";
    el.src = src;
    el.addEventListener("error", onError);
    return el;
  }

  if (audioSrc) {
    music = attachAudio(audioSrc, function () {
      music = null;
    });
  }
  if (voiceSrc) {
    voice = attachAudio(voiceSrc, function () {
      voice = null;
    });
  }

  if (playBtn) playBtn.addEventListener("click", togglePlay);
  if (stopBtn) stopBtn.addEventListener("click", stopAll);
  if (muteBtn) muteBtn.addEventListener("click", toggleMute);
  if (captionBtn) captionBtn.addEventListener("click", toggleCaptions);

  root.setAttribute("tabindex", "0");
  root.addEventListener("keydown", function (event) {
    if (event.target !== root && event.target.tagName === "A") return;
    if (event.code === "Space") {
      event.preventDefault();
      togglePlay();
    } else if (event.key === "Escape" || event.key === "s" || event.key === "S") {
      event.preventDefault();
      stopAll();
    } else if (event.key === "m" || event.key === "M") {
      event.preventDefault();
      toggleMute();
    } else if (event.key === "c" || event.key === "C") {
      event.preventDefault();
      toggleCaptions();
    }
  });

  function ready() {
    render(0);
  }

  if (captionsSrc) {
    fetch(captionsSrc, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) throw new Error("vtt");
        return response.text();
      })
      .then(function (text) {
        const parsed = parseVtt(text);
        if (parsed.length) cues = parsed;
      })
      .catch(function () {})
      .then(ready);
  } else {
    ready();
  }
})();
