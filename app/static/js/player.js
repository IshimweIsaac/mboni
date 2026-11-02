/* Custom video player: keyboard, touch, quality switch, subtitles, resume, trailer cut-off. */
(() => {
  const $ = (s) => document.querySelector(s);
  const root = $("#player");
  const video = $("#video");
  if (!root || !video) return;
  const N = window.MBONI || {};
  const slug = root.dataset.slug;
  const trailer = root.dataset.trailer === "true";
  const TRAILER_SECONDS = 30;
  const INTRO_END = 12;
  const icons = {
    play: '<path d="M7 4.5v15a1 1 0 0 0 1.5.86l12.5-7.5a1 1 0 0 0 0-1.72L8.5 3.64A1 1 0 0 0 7 4.5Z" fill="currentColor" stroke="none"/>',
    pause: '<rect x="6" y="4" width="4" height="16" rx="1" fill="currentColor" stroke="none"/><rect x="14" y="4" width="4" height="16" rx="1" fill="currentColor" stroke="none"/>',
    volume: '<path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/>',
    mute: '<path d="M11 5 6 9H2v6h4l5 4zM23 9l-6 6M17 9l6 6"/>',
  };
  const fmt = (t) => {
    if (!isFinite(t)) return "0:00";
    const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = Math.floor(t % 60);
    return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
  };

  // On-screen display for keyboard / gesture feedback
  let osdTimer;
  const osd = (text) => {
    const el = $("#osd");
    el.textContent = text;
    el.classList.add("show");
    clearTimeout(osdTimer);
    osdTimer = setTimeout(() => el.classList.remove("show"), 700);
  };

  // Hide controls when idle
  let idleTimer;
  const wake = () => {
    root.classList.remove("idle");
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => { if (!video.paused && !$("#sheet").classList.contains("open")) root.classList.add("idle"); }, 2800);
  };
  ["mousemove", "touchstart", "keydown"].forEach((ev) => root.addEventListener(ev, wake, { passive: true }));

  // Play / pause
  const setPlayIcon = () => {
    const playing = !video.paused;
    [$("#play"), $("#play-sm")].forEach((b) => {
      b.querySelector("svg").innerHTML = playing ? icons.pause : icons.play;
      b.setAttribute("aria-label", playing ? "Pause" : "Play");
    });
  };
  const toggle = () => (video.paused ? video.play() : video.pause());
  $("#play").addEventListener("click", toggle);
  $("#play-sm").addEventListener("click", toggle);
  video.addEventListener("click", toggle);
  video.addEventListener("play", () => { setPlayIcon(); wake(); });
  video.addEventListener("pause", () => { setPlayIcon(); root.classList.remove("idle"); save(); });

  // Seeking
  const skip = (s) => { video.currentTime = Math.max(0, Math.min(video.duration || 0, video.currentTime + s)); osd(`${s > 0 ? "+" : "−"}${Math.abs(s)}s`); };
  document.querySelectorAll("[data-skip]").forEach((b) => b.addEventListener("click", () => skip(Number(b.dataset.skip))));
  const seek = $("#seek");
  const pctAt = (x) => { const r = seek.getBoundingClientRect(); return Math.max(0, Math.min(1, (x - r.left) / r.width)); };
  let dragging = false;
  const seekTo = (x) => { if (video.duration) video.currentTime = pctAt(x) * video.duration; };
  seek.addEventListener("pointerdown", (e) => { dragging = true; seek.setPointerCapture(e.pointerId); seekTo(e.clientX); });
  seek.addEventListener("pointermove", (e) => {
    const p = pctAt(e.clientX);
    $("#tip").style.left = `${p * 100}%`;
    $("#tip").textContent = fmt(p * (video.duration || 0));
    if (dragging) seekTo(e.clientX);
  });
  seek.addEventListener("pointerup", () => (dragging = false));
  seek.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") { e.preventDefault(); e.stopPropagation(); skip(5); }
    if (e.key === "ArrowLeft") { e.preventDefault(); e.stopPropagation(); skip(-5); }
  });

  const update = () => {
    const d = video.duration || 0, t = video.currentTime;
    const p = d ? (t / d) * 100 : 0;
    $("#done").style.width = `${p}%`;
    $("#knob").style.left = `${p}%`;
    seek.setAttribute("aria-valuenow", Math.round(p));
    seek.setAttribute("aria-valuetext", `${fmt(t)} of ${fmt(d)}`);
    $("#time").textContent = `${fmt(t)} / ${fmt(d)}`;
    if (video.buffered.length && d) $("#buf").style.width = `${(video.buffered.end(video.buffered.length - 1) / d) * 100}%`;
    $("#skip-intro").classList.toggle("show", !trailer && t > 2 && t < INTRO_END);
    if (trailer && t >= TRAILER_SECONDS) {
      video.pause();
      video.currentTime = TRAILER_SECONDS;
      $("#trailer-end").classList.add("show");
    }
    const next = $("#up-next");
    if (next && d && d - t < 12 && !next.dataset.cancelled) startNext();
  };
  video.addEventListener("timeupdate", update);
  video.addEventListener("progress", update);
  video.addEventListener("loadedmetadata", update);
  $("#skip-intro").addEventListener("click", () => { video.currentTime = INTRO_END; osd("Intro skipped"); });

  // Up next countdown
  let nextTimer;
  function startNext() {
    const card = $("#up-next");
    if (nextTimer || !card) return;
    card.classList.add("show");
    let n = 10;
    nextTimer = setInterval(() => {
      n -= 1;
      $("#next-count").textContent = n;
      if (n <= 0) { clearInterval(nextTimer); location.href = $("#next-go").href; }
    }, 1000);
    $("#next-cancel").addEventListener("click", () => { clearInterval(nextTimer); card.classList.remove("show"); card.dataset.cancelled = "1"; });
  }

  // Volume
  const vol = $("#vol");
  const setVolIcon = () => { $("#mute").querySelector("svg").innerHTML = video.muted || video.volume === 0 ? icons.mute : icons.volume; };
  vol.addEventListener("input", () => { video.volume = Number(vol.value); video.muted = video.volume === 0; setVolIcon(); });
  $("#mute").addEventListener("click", () => { video.muted = !video.muted; setVolIcon(); osd(video.muted ? "Muted" : "Sound on"); });

  // Full screen + picture in picture
  const fs = () => (document.fullscreenElement ? document.exitFullscreen() : root.requestFullscreen && root.requestFullscreen().catch(() => {}));
  $("#fs-btn").addEventListener("click", fs);
  root.addEventListener("dblclick", (e) => { if (e.target === video) fs(); });
  if (document.pictureInPictureEnabled) {
    $("#pip-btn").hidden = false;
    $("#pip-btn").addEventListener("click", () => (document.pictureInPictureElement ? document.exitPictureInPicture() : video.requestPictureInPicture()));
  }

  // Settings sheet: quality, subtitles, speed
  const sheet = $("#sheet");
  const settingsBtn = $("#settings-btn");
  settingsBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const open = !sheet.classList.contains("open");
    sheet.classList.toggle("open", open);
    settingsBtn.setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("click", (e) => { if (!sheet.contains(e.target)) { sheet.classList.remove("open"); settingsBtn.setAttribute("aria-expanded", "false"); } });
  const check = (attr, btn) => sheet.querySelectorAll(`[${attr}]`).forEach((b) => b.setAttribute("aria-checked", String(b === btn)));

  sheet.querySelectorAll("[data-q]").forEach((b) => b.addEventListener("click", () => {
    const t = video.currentTime, playing = !video.paused;
    video.src = b.dataset.src;
    video.currentTime = t;
    if (playing) video.play();
    check("data-q", b);
    $("#data-badge span").textContent = b.dataset.label;
    osd(b.dataset.q);
  }));

  const setSub = (lang) => {
    [...video.textTracks].forEach((tr) => (tr.mode = tr.language === lang ? "showing" : "disabled"));
    check("data-sub", sheet.querySelector(`[data-sub="${lang}"]`) || sheet.querySelector('[data-sub="off"]'));
    $("#cc-btn").setAttribute("aria-pressed", String(lang !== "off"));
    try { localStorage.setItem("mboni-subs", lang); } catch {}
  };
  sheet.querySelectorAll("[data-sub]").forEach((b) => b.addEventListener("click", () => setSub(b.dataset.sub)));
  let lastSub = "en";
  try { lastSub = localStorage.getItem("mboni-subs") || document.documentElement.lang || "en"; } catch {}
  $("#cc-btn").addEventListener("click", () => {
    const on = $("#cc-btn").getAttribute("aria-pressed") === "true";
    setSub(on ? "off" : lastSub === "off" ? "en" : lastSub);
    osd(on ? "Subtitles off" : "Subtitles on");
  });
  setSub((() => { try { return localStorage.getItem("mboni-subs") || "off"; } catch { return "off"; } })());

  sheet.querySelectorAll("[data-speed]").forEach((b) => b.addEventListener("click", () => {
    video.playbackRate = Number(b.dataset.speed);
    check("data-speed", b);
    osd(`${b.dataset.speed}×`);
  }));

  // Keyboard shortcuts
  document.addEventListener("keydown", (e) => {
    if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
    const k = e.key.toLowerCase();
    if (k === " " || k === "k") { e.preventDefault(); toggle(); }
    else if (k === "arrowright" || k === "l") skip(10);
    else if (k === "arrowleft" || k === "j") skip(-10);
    else if (k === "arrowup") { e.preventDefault(); video.volume = Math.min(1, video.volume + 0.1); vol.value = video.volume; osd(`Volume ${Math.round(video.volume * 100)}%`); }
    else if (k === "arrowdown") { e.preventDefault(); video.volume = Math.max(0, video.volume - 0.1); vol.value = video.volume; osd(`Volume ${Math.round(video.volume * 100)}%`); }
    else if (k === "f") fs();
    else if (k === "m") $("#mute").click();
    else if (k === "c") $("#cc-btn").click();
    else if (k === "escape" && !document.fullscreenElement) location.href = root.querySelector(".top a").href;
  });

  // Double-tap left / right side to skip on phones
  let lastTap = 0;
  video.addEventListener("touchend", (e) => {
    const now = Date.now();
    if (now - lastTap < 300) {
      const x = e.changedTouches[0].clientX;
      skip(x < innerWidth / 2 ? -10 : 10);
      e.preventDefault();
    }
    lastTap = now;
  });

  // Resume position and progress saving
  const start = Number(root.dataset.start || 0);
  video.addEventListener("loadedmetadata", () => {
    if (start > 0 && start < video.duration - 5) { video.currentTime = start; osd(`Resuming at ${fmt(start)}`); }
  }, { once: true });
  let lastSaved = 0;
  function save() {
    if (root.dataset.save !== "true" || !video.duration) return;
    fetch(root.dataset.progressUrl, {
      method: "POST",
      keepalive: true,
      headers: { "Content-Type": "application/json", "X-CSRF": N.csrf },
      body: JSON.stringify({ slug, position: video.currentTime, duration: video.duration }),
    }).catch(() => {});
  }
  video.addEventListener("timeupdate", () => {
    if (Math.abs(video.currentTime - lastSaved) > 10) { lastSaved = video.currentTime; save(); }
  });
  addEventListener("pagehide", save);

  video.play().catch(() => { root.classList.remove("idle"); });
  setPlayIcon();
  wake();
})();
