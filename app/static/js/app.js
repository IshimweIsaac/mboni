/* Mboni front-end: progressive enhancement on top of server-rendered pages. */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const N = window.MBONI || {};
  const DOWNLOADS = "mboni-downloads";

  const post = (url, body) =>
    fetch(url, {
      method: "POST",
      headers: { "X-CSRF": N.csrf, "X-Requested-With": "fetch", "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : null,
    });

  // ---------- Toasts ----------
  const toast = (msg, kind = "info") => {
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.setAttribute("role", "status");
    el.innerHTML = `<span></span><button type="button" aria-label="Dismiss" data-dismiss>&times;</button>`;
    el.firstChild.textContent = msg;
    $("#toasts").append(el);
    setTimeout(() => el.remove(), 4500);
  };
  window.mboniToast = toast;
  $$(".toast").forEach((t) => setTimeout(() => t.remove(), 6000));
  document.addEventListener("click", (e) => {
    const d = e.target.closest("[data-dismiss]");
    if (d) d.closest(".toast").remove();
  });

  // ---------- Nav background on scroll ----------
  const nav = $("#nav");
  if (nav) {
    const onScroll = () => nav.classList.toggle("solid", scrollY > 40);
    addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // ---------- Dropdown menus ----------
  $$("[data-menu]").forEach((menu) => {
    const btn = menu.querySelector("button");
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const open = !menu.classList.contains("open");
      $$("[data-menu].open").forEach((m) => { m.classList.remove("open"); m.querySelector("button").setAttribute("aria-expanded", "false"); });
      menu.classList.toggle("open", open);
      btn.setAttribute("aria-expanded", String(open));
    });
  });
  document.addEventListener("click", () => $$("[data-menu].open").forEach((m) => m.classList.remove("open")));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $$("[data-menu].open").forEach((m) => { m.classList.remove("open"); m.querySelector("button").focus(); });
  });

  // ---------- Display preferences (theme, contrast, motion) ----------
  const prefs = (() => { try { return JSON.parse(localStorage.getItem("mboni-prefs") || "{}"); } catch { return {}; } })();
  const savePrefs = () => { try { localStorage.setItem("mboni-prefs", JSON.stringify(prefs)); } catch {} };
  const applyPref = (key, value) => {
    prefs[key] = value;
    if (value) document.documentElement.dataset[key] = value;
    else delete document.documentElement.dataset[key];
    savePrefs();
  };
  $$("[data-pref]").forEach((seg) => {
    const key = seg.dataset.pref;
    const sync = () => $$("button", seg).forEach((b) => b.setAttribute("aria-pressed", String((prefs[key] || "") === b.dataset.v)));
    seg.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (b) { applyPref(key, b.dataset.v); sync(); }
    });
    sync();
  });
  $$("[data-toggle-theme]").forEach((b) => b.addEventListener("click", () => applyPref("theme", prefs.theme === "light" ? "" : "light")));

  // ---------- Search overlay with live results and voice ----------
  const pop = $("#search-pop");
  const qInput = $("#quick-q");
  const results = $("#quick-results");
  let lastFocus = null;
  const openSearch = () => {
    lastFocus = document.activeElement;
    pop.classList.add("open");
    document.body.style.overflow = "hidden";
    setTimeout(() => qInput.focus(), 30);
  };
  const closeSearch = () => {
    pop.classList.remove("open");
    document.body.style.overflow = "";
    lastFocus && lastFocus.focus();
  };
  $$("[data-open-search]").forEach((b) => b.addEventListener("click", openSearch));
  $$("[data-close-search]").forEach((b) => b.addEventListener("click", closeSearch));
  document.addEventListener("keydown", (e) => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
    if (e.key === "/" && !typing && pop) { e.preventDefault(); openSearch(); }
    if (e.key === "Escape" && pop && pop.classList.contains("open")) closeSearch();
  });
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  let timer;
  const runSearch = () => {
    const q = qInput.value.trim();
    if (!q) { results.innerHTML = ""; return; }
    fetch(`${N.searchApi}?q=${encodeURIComponent(q)}`)
      .then((r) => r.json())
      .then((items) => {
        results.innerHTML = items.length
          ? items.map((m) => `<a class="quick-item" role="option" href="${m.url}">
              <div class="art pat-${m.pattern}${m.cover ? " has-photo" : ""}" style="--c1:${m.c1};--c2:${m.c2};--c3:${m.c3}${m.cover ? `;--photo:url('${m.cover}')` : ""}"></div>
              <div><b>${esc(m.title)}</b><div class="faint" style="font-size:.85rem">${m.year} · ${esc(m.country)} · ${esc(m.genres)}</div></div></a>`).join("") +
            `<a class="btn btn-sm" style="justify-self:start" href="/search?q=${encodeURIComponent(q)}">See all results</a>`
          : `<p class="muted">No films for “${esc(q)}”. Try a country, language or actor.</p>`;
      })
      .catch(() => { results.innerHTML = `<p class="muted">Search needs a connection.</p>`; });
  };
  if (qInput) {
    qInput.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(runSearch, 160); });
    $$("[data-suggest]").forEach((b) => b.addEventListener("click", () => { qInput.value = b.dataset.suggest; runSearch(); qInput.focus(); }));
  }
  const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
  const mic = $("[data-voice]");
  if (Speech && mic) {
    mic.hidden = false;
    mic.addEventListener("click", () => {
      const rec = new Speech();
      rec.lang = { rw: "rw-RW", fr: "fr-FR" }[document.documentElement.lang] || "en-US";
      rec.interimResults = true;
      mic.classList.add("listening");
      rec.onresult = (e) => { qInput.value = [...e.results].map((r) => r[0].transcript).join(""); runSearch(); };
      rec.onend = () => mic.classList.remove("listening");
      rec.onerror = () => { mic.classList.remove("listening"); toast("Couldn't hear that. Try typing instead.", "error"); };
      rec.start();
    });
  }

  // ---------- Watchlist toggle ----------
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-watchlist]");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    if (!N.hasProfile) { location.href = "/login"; return; }
    const res = await post(`/api/watchlist/${btn.dataset.watchlist}`);
    if (!res.ok) return toast("Couldn't update your list.", "error");
    const data = await res.json();
    $$(`[data-watchlist="${btn.dataset.watchlist}"]`).forEach((b) => {
      b.setAttribute("aria-pressed", String(data.added));
      const svg = b.querySelector("svg");
      if (svg) svg.innerHTML = data.added ? '<path d="M20 6 9 17l-5-5"/>' : '<path d="M12 5v14M5 12h14"/>';
      if (!b.hasAttribute("data-label")) b.setAttribute("aria-label", `${data.added ? "Remove from" : "Add to"} My List`);
    });
    toast(data.added ? `${data.title} added to My List` : `${data.title} removed from My List`, "success");
  });

  // ---------- Cart ----------
  const setCartCount = (n) => $$("[data-cart-count]").forEach((el) => { el.textContent = n; el.hidden = !n; });
  const cartFetch = async (url, fd) => {
    const res = await fetch(url, { method: "POST", body: fd, headers: { "X-Requested-With": "fetch", "X-CSRF": N.csrf } });
    let data = {};
    try { data = await res.json(); } catch {}
    if (!res.ok || !data.ok) { toast(data.error || "Couldn't update your cart. Try again.", "error"); return null; }
    setCartCount(data.count);
    return data;
  };
  // "Add to cart" buttons on film pages and posters.
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-cart-add]");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    const fd = new FormData();
    fd.append("csrf", N.csrf);
    fd.append("movie", btn.dataset.cartAdd);
    fd.append("kind", btn.dataset.kind || "buy");
    btn.disabled = true;
    const data = await cartFetch(N.cartAdd, fd);
    btn.disabled = false;
    if (!data) return;
    toast(data.message, "success");
    const link = document.createElement("a");
    link.href = N.cartUrl; link.className = "toast-link"; link.textContent = "View cart →";
    const last = $("#toasts").lastElementChild;
    if (last) last.firstChild.after(link);
    $$("[data-cart-icon]").forEach((c) => { c.classList.remove("bump"); void c.offsetWidth; c.classList.add("bump"); });
  });
  // Cart page: every form updates the cart in place, without reloading.
  document.addEventListener("submit", async (e) => {
    const form = e.target.closest("form[data-cart-form]");
    if (!form || form.dataset.confirm) return;
    e.preventDefault();
    const data = await cartFetch(form.action, new FormData(form, e.submitter));
    if (!data) return;
    const body = $("#cart-body");
    if (body) body.innerHTML = data.html;
    if (data.message) toast(data.message, "info");
  });
  document.addEventListener("change", (e) => {
    const form = e.target.closest("form[data-submit-on-change]");
    if (form) form.requestSubmit();
  });
  // Copy gift codes.
  document.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-copy]");
    if (!b) return;
    try { await navigator.clipboard.writeText(b.dataset.copy); toast(`${b.dataset.copy} copied`, "success"); }
    catch { toast(b.dataset.copy); }
  });

  // ---------- Rails: arrow buttons ----------
  $$("[data-rail]").forEach((b) => b.addEventListener("click", () => {
    const rail = b.parentElement.querySelector(".rail");
    rail.scrollBy({ left: Number(b.dataset.rail) * rail.clientWidth * 0.85, behavior: "smooth" });
  }));

  // ---------- Hero carousel ----------
  const hero = $("[data-hero]");
  if (hero) {
    const slides = $$("[data-slide]", hero);
    const contents = $$("[data-slide-content]", hero);
    const dots = $$("[data-dot]", hero);
    let i = 0, auto;
    const show = (n) => {
      i = (n + slides.length) % slides.length;
      slides.forEach((s, k) => { s.classList.toggle("on", k === i); s.setAttribute("aria-hidden", String(k !== i)); });
      contents.forEach((c, k) => { c.hidden = k !== i; if (k === i) { c.classList.remove("reveal-up"); void c.offsetWidth; c.classList.add("reveal-up"); } });
      dots.forEach((d, k) => { if (k === i) d.setAttribute("aria-current", "true"); else d.removeAttribute("aria-current"); });
    };
    const start = () => { clearInterval(auto); if (slides.length > 1 && !matchMedia("(prefers-reduced-motion: reduce)").matches) auto = setInterval(() => show(i + 1), 8000); };
    dots.forEach((d) => d.addEventListener("click", () => { show(Number(d.dataset.dot)); start(); }));
    hero.addEventListener("mouseenter", () => clearInterval(auto));
    hero.addEventListener("mouseleave", start);
    hero.addEventListener("focusin", () => clearInterval(auto));
    let x0 = null;
    hero.addEventListener("touchstart", (e) => (x0 = e.touches[0].clientX), { passive: true });
    hero.addEventListener("touchend", (e) => {
      if (x0 === null) return;
      const dx = e.changedTouches[0].clientX - x0;
      if (Math.abs(dx) > 50) { show(i + (dx < 0 ? 1 : -1)); start(); }
      x0 = null;
    });
    start();
  }

  // ---------- Tabs (Library) ----------
  $$("[data-tabs]").forEach((list) => {
    const tabs = $$("[role=tab]", list);
    const select = (tab) => {
      tabs.forEach((t) => {
        const on = t === tab;
        t.setAttribute("aria-selected", String(on));
        t.tabIndex = on ? 0 : -1;
        document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
      });
      try { sessionStorage.setItem("mboni-lib-tab", tab.id); } catch {}
    };
    tabs.forEach((t, k) => {
      t.addEventListener("click", () => select(t));
      t.addEventListener("keydown", (e) => {
        if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
          const next = tabs[(k + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length];
          next.focus(); select(next);
        }
      });
    });
    const hashTab = location.hash && document.getElementById(`t-${location.hash.slice(1)}`);
    let saved = null;
    try { saved = document.getElementById(sessionStorage.getItem("mboni-lib-tab")); } catch {}
    select(hashTab || saved || tabs[0]);
  });

  // ---------- Rental countdowns ----------
  const countdowns = $$("[data-countdown]");
  if (countdowns.length) {
    const tick = () => countdowns.forEach((el) => {
      const ms = new Date(el.dataset.countdown.replace(" ", "T")) - new Date();
      if (ms <= 0) { el.textContent = "Expired"; return; }
      const h = Math.floor(ms / 3.6e6), m = Math.floor((ms % 3.6e6) / 6e4), s = Math.floor((ms % 6e4) / 1000);
      const txt = `${h}h ${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s`;
      const svg = el.querySelector("svg");
      el.textContent = el.classList.contains("pill-time") ? ` ${txt} left` : txt;
      if (svg) el.prepend(svg);
    });
    tick();
    setInterval(tick, 1000);
  }

  // ---------- Confirm dialogs (no browser alerts) ----------
  const dlg = document.createElement("dialog");
  dlg.className = "panel";
  dlg.style.cssText = "max-width:420px;width:calc(100% - 32px);color:var(--text);border:1px solid var(--line-strong)";
  dlg.innerHTML = `<form method="dialog" class="stack"><p style="font-weight:700;font-size:1.05rem" id="dlg-msg"></p>
    <div class="row-gap" style="justify-content:flex-end"><button class="btn btn-sm" value="no">Keep it</button><button class="btn btn-sm btn-gold" value="yes">Yes, continue</button></div></form>`;
  document.body.append(dlg);
  document.addEventListener("submit", (e) => {
    const f = e.target.closest("form[data-confirm]");
    if (!f || f.dataset.confirmed) return;
    e.preventDefault();
    $("#dlg-msg", dlg).textContent = f.dataset.confirm;
    dlg.returnValue = "";
    dlg.showModal();
    dlg.addEventListener("close", () => { if (dlg.returnValue === "yes") { f.dataset.confirmed = "1"; f.submit(); } }, { once: true });
  });

  // ---------- Forms: auto-submit filters, password helpers, demo fill ----------
  $$("form[data-autosubmit]").forEach((f) => {
    $$("select", f).forEach((s) => s.addEventListener("change", () => f.submit()));
  });
  $$("[data-reveal]").forEach((b) => b.addEventListener("click", () => {
    const input = document.getElementById(b.dataset.reveal);
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    b.textContent = show ? "Hide" : "Show";
  }));
  const pw = $("[data-strength]");
  if (pw) pw.addEventListener("input", () => {
    const v = pw.value;
    const score = [v.length >= 8, /[A-Z]/.test(v) && /[a-z]/.test(v), /\d/.test(v), /[^A-Za-z0-9]/.test(v), v.length >= 12].filter(Boolean).length;
    const labels = ["Too short", "Weak", "Okay", "Good", "Strong", "Excellent"];
    const colors = ["var(--danger)", "var(--danger)", "var(--gold)", "var(--gold)", "var(--leaf)", "var(--leaf)"];
    const s = v.length < 8 ? 0 : score;
    $("#pw-bar").style.width = `${(s / 5) * 100}%`;
    $("#pw-bar").style.background = colors[s];
    $("#pw-text").textContent = v ? labels[s] : "At least 8 characters.";
  });
  $$("[data-fill]").forEach((b) => b.addEventListener("click", () => {
    const [email, pass] = b.dataset.fill.split("|");
    $("#email").value = email;
    $("#password").value = pass;
    b.closest("form").requestSubmit();
  }));

  // ---------- Checkout ----------
  const checkout = $("#checkout-form");
  if (checkout) {
    const syncMethod = () => {
      const m = (checkout.querySelector("[name=method]:checked") || {}).value || "mtn";
      $$(".pay-fields", checkout).forEach((p) => (p.hidden = !p.dataset.for.split(" ").includes(m)));
    };
    $$("[name=method]", checkout).forEach((r) => r.addEventListener("change", syncMethod));
    syncMethod();
    const card = $("[data-card]");
    card && card.addEventListener("input", () => {
      card.value = card.value.replace(/\D/g, "").slice(0, 19).replace(/(\d{4})(?=\d)/g, "$1 ");
    });
    const exp = $("[data-expiry]");
    exp && exp.addEventListener("input", (e) => {
      let v = exp.value.replace(/\D/g, "").slice(0, 4);
      if (v.length >= 3 || (v.length === 2 && e.inputType !== "deleteContentBackward")) v = `${v.slice(0, 2)}/${v.slice(2)}`;
      exp.value = v;
    });
    const total = $("#total");
    const base = Number(total.dataset.base);
    const fmt = (n) => `${n.toLocaleString("en-US")} RWF`;
    const applyPromo = async () => {
      const code = $("#promo").value.trim();
      const msg = $("#promo-msg");
      if (!code) { $("#discount-line").hidden = true; total.textContent = fmt(base); $("#pay-amount").textContent = fmt(base); msg.textContent = ""; return; }
      const data = await (await fetch(`${$("#apply-promo").dataset.url}?code=${encodeURIComponent(code)}`)).json();
      if (!data.ok) {
        msg.className = "error-text"; msg.textContent = `${data.error} Try STUDENT50.`;
        $("#discount-line").hidden = true; total.textContent = fmt(base); $("#pay-amount").textContent = fmt(base);
        return;
      }
      const off = Math.floor((base * data.percent) / 100);
      msg.className = "hint"; msg.textContent = `✓ ${data.label}: ${data.percent}% off`;
      $("#promo-name").textContent = data.code;
      $("#discount-amt").textContent = `−${fmt(off)}`;
      $("#discount-line").hidden = false;
      total.textContent = fmt(base - off);
      $("#pay-amount").textContent = fmt(base - off);
    };
    if ($("#apply-promo")) {
      $("#apply-promo").addEventListener("click", applyPromo);
      $("#promo").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); applyPromo(); } });
      if ($("#promo").value) applyPromo();
    }
    checkout.addEventListener("submit", () => {
      const b = $("#pay-btn");
      b.disabled = true;
      b.innerHTML = '<span class="ring" style="width:20px;height:20px;border-width:3px;margin:0"></span> Sending request…';
    });
  }

  // ---------- Simulated phone approval ----------
  const confirmForm = $("#confirm-form");
  if (confirmForm) {
    let n = 6;
    const dots = $("#pin-dots");
    const tick = setInterval(() => {
      n -= 1;
      $("#auto-count").textContent = n;
      if (dots) dots.textContent = "* ".repeat(Math.min(5, 6 - n)) + "_ ".repeat(Math.max(0, n - 1));
      if (n <= 0) { clearInterval(tick); $("#approve-btn").click(); }
    }, 1000);
    confirmForm.addEventListener("submit", () => clearInterval(tick));
  }

  // ---------- Celebrate a successful payment ----------
  if ($("[data-celebrate]") && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const c = document.createElement("div");
    c.className = "confetti";
    const colors = ["#f5a524", "#e4572e", "#3ecf8e", "#5aa9ff", "#ffcf6b"];
    for (let k = 0; k < 90; k++) {
      const p = document.createElement("i");
      p.style.left = `${Math.random() * 100}%`;
      p.style.background = colors[k % colors.length];
      p.style.animationDelay = `${Math.random() * 0.8}s`;
      p.style.animationDuration = `${2 + Math.random() * 1.6}s`;
      c.append(p);
    }
    document.body.append(c);
    setTimeout(() => c.remove(), 4500);
  }

  // ---------- Share ----------
  $$("[data-share]").forEach((b) => b.addEventListener("click", async () => {
    const text = b.dataset.shareText || `Watch ${b.dataset.share} on Mboni`;
    const data = b.dataset.shareText ? { title: b.dataset.share, text } : { title: b.dataset.share, text, url: location.href };
    if (navigator.share) { try { await navigator.share(data); } catch {} return; }
    const copy = b.dataset.shareText || location.href;
    try { await navigator.clipboard.writeText(copy); toast("Copied. Paste it into WhatsApp or SMS!", "success"); }
    catch { toast(copy); }
  }));

  // ---------- Offline downloads (Cache API, served by the service worker) ----------
  const setDlButton = (b, on) => {
    b.dataset.downloaded = String(on);
    const label = b.querySelector("span");
    if (label && !b.hasAttribute("data-remove-row")) label.textContent = on ? "Downloaded · remove" : "Download for offline";
  };
  $$("[data-download]").forEach((b) => b.addEventListener("click", async () => {
    const slug = b.dataset.download;
    const removing = b.dataset.downloaded === "true";
    b.disabled = true;
    try {
      const res = await post(`/api/download/${slug}${removing ? "?remove=1" : ""}`);
      const data = await res.json();
      if (!data.ok) { toast(data.error, "error"); return; }
      if (removing) {
        setDlButton(b, false);
        toast("Download removed.", "info");
        const row = b.closest("[data-download-row]");
        if (row) row.remove();
        return;
      }
      label(b, "Downloading…");
      if ("caches" in window) {
        const cache = await caches.open(DOWNLOADS);
        await cache.add(data.src);
        try { localStorage.setItem(`mboni-dl-${slug}`, data.src); } catch {}
      }
      setDlButton(b, true);
      toast(`Saved in ${data.quality}. It will play without internet.`, "success");
    } catch {
      toast("Download failed. Check your connection and try again.", "error");
    } finally {
      b.disabled = false;
    }
  }));
  function label(b, text) { const s = b.querySelector("span"); if (s) s.textContent = text; }
  $$("[data-offline-state]").forEach(async (el) => {
    let src = null;
    try { src = localStorage.getItem(`mboni-dl-${el.dataset.offlineState}`); } catch {}
    const hit = src && "caches" in window && (await (await caches.open(DOWNLOADS)).match(src));
    el.textContent = hit ? "✓ ready offline" : "not on this device yet";
    el.style.color = hit ? "var(--leaf)" : "";
  });

  // ---------- Data saver: no autoplay previews ----------
  const saveData = navigator.connection && navigator.connection.saveData;
  if (saveData || prefs.motion === "reduce") $$("[data-saver-hide]").forEach((v) => v.remove());

  // ---------- Admin poster preview ----------
  const preview = $("#preview");
  if (preview) {
    const form = $("#movie-form");
    form.addEventListener("input", () => {
      preview.style.setProperty("--c1", form.c1.value);
      preview.style.setProperty("--c2", form.c2.value);
      preview.style.setProperty("--c3", form.c3.value);
      preview.className = `art pat-${form.pattern.value}`;
      $("#pv-title").textContent = form.title.value || "Film title";
      $("#pv-country").textContent = form.country.value || "Country";
    });
  }

  // ---------- Online / offline + PWA ----------
  const net = () => document.body.classList.toggle("is-offline", !navigator.onLine);
  addEventListener("online", net);
  addEventListener("offline", net);
  net();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  let deferred;
  addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferred = e;
    $$("[data-install]").forEach((b) => (b.hidden = false));
    const card = $("#install-card");
    card && card.classList.add("show");
  });
  $$("[data-install]").forEach((b) => b.addEventListener("click", async (e) => {
    e.preventDefault();
    if (!deferred) return;
    deferred.prompt();
    await deferred.userChoice;
    deferred = null;
  }));
})();
