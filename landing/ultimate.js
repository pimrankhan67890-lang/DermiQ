(() => {
  function qs(id) {
    return document.getElementById(id);
  }

  /* WARM-UP (Render free tier can cold start). */
  function hideWarmup() {
    const w = qs("warmup");
    if (!w) return;
    w.classList.add("hidden");
    window.setTimeout(() => {
      w.style.display = "none";
    }, 900);
  }

  async function pingHealth() {
    const maxAttempts = 8;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      const controller = new AbortController();
      const t = window.setTimeout(() => controller.abort(), 12000);
      try {
        const r = await fetch("/health", { method: "GET", signal: controller.signal });
        window.clearTimeout(t);
        if (r.ok) {
          hideWarmup();
          return true;
        }
      } catch {
        window.clearTimeout(t);
      }
      await new Promise((res) => window.setTimeout(res, 900));
    }
    hideWarmup();
    return false;
  }

  pingHealth().catch(() => {});

  /* STATE */
  let currentFile = null;
  let scanId = null;
  let lastScan = null;
  let sessionId = null;
  let billingPlan = "free";
  let billingProToken = "";

  function loadSessionId() {
    try {
      const s = window.localStorage.getItem("dermiq_session_id");
      sessionId = String(s || "").trim() || null;
    } catch {
      sessionId = null;
    }
  }

  async function ensureSession() {
    if (sessionId) return sessionId;
    loadSessionId();
    if (sessionId) return sessionId;
    try {
      const r = await fetch("/tracker/session", { method: "POST" });
      if (!r.ok) return null;
      const j = await r.json().catch(() => null);
      const sid = String(j?.session_id || "").trim();
      if (!sid) return null;
      sessionId = sid;
      try {
        window.localStorage.setItem("dermiq_session_id", sid);
      } catch {}
      return sid;
    } catch {
      return null;
    }
  }

  // Fire-and-forget so the first scan already has a session id.
  ensureSession().catch(() => {});

  async function refreshBilling() {
    try {
      const sid = await ensureSession();
      if (!sid) return;
      const r = await fetch("/billing/status", { method: "GET", headers: { "X-Session-Id": sid } });
      if (!r.ok) return;
      const j = await r.json().catch(() => null);
      billingPlan = String(j?.plan || "free");
      billingProToken = String(j?.pro_token || "");
    } catch {}
  }

  refreshBilling().catch(() => {});

  function labelToTitle(label) {
    const s = String(label || "").trim();
    if (!s) return "Unknown";
    return s
      .split("_")
      .map((p) => p.slice(0, 1).toUpperCase() + p.slice(1))
      .join(" ");
  }

  function probToPct(prob) {
    const n = Number(prob);
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(100, Math.round(n * 100)));
  }

  function productIcon(productId) {
    const s = String(productId || "").toLowerCase();
    if (s.includes("sunscreen") || s.includes("spf")) return "☀️";
    if (s.includes("serum") || s.includes("acid")) return "💧";
    if (s.includes("shampoo")) return "🧴";
    if (s.includes("cleanser") || s.includes("wash")) return "🧼";
    if (s.includes("cream") || s.includes("ceramide") || s.includes("moist")) return "🧴";
    return "🧴";
  }

  /* FILE HANDLING */
  function handleFile(e) {
    const f = e?.target?.files?.[0];
    if (!f) return;
    if (!String(f.type || "").startsWith("image/")) {
      alert("Please upload an image file.");
      return;
    }
    if (f.size > 10 * 1024 * 1024) {
      alert("File too large — max 10MB");
      return;
    }
    currentFile = f;
    const rd = new FileReader();
    rd.onload = (ev) => {
      const img = qs("preview-img");
      if (img) img.src = ev.target.result;
      const wrap = qs("preview-wrap");
      if (wrap) wrap.style.display = "block";
    };
    rd.readAsDataURL(f);

    const btn = qs("scan-btn");
    if (btn) btn.style.display = "inline-flex";

    const results = qs("results");
    if (results) results.style.display = "none";
    const products = qs("products-wrap");
    if (products) products.style.display = "none";
    const fb = qs("feedback-wrap");
    if (fb) fb.style.display = "none";
  }

  /* Drag & drop */
  const dz = qs("dropzone");
  dz?.addEventListener("dragover", (e) => {
    e.preventDefault();
    dz.classList.add("drag");
  });
  dz?.addEventListener("dragleave", () => dz.classList.remove("drag"));
  dz?.addEventListener("drop", (e) => {
    e.preventDefault();
    dz.classList.remove("drag");
    const f = e.dataTransfer?.files?.[0];
    if (!f) return;
    const input = qs("file-input");
    if (input) input.files = e.dataTransfer.files;
    handleFile({ target: { files: [f] } });
  });

  /* SCAN ANIMATION */
  const STEPS = [
    { id: "ss0", prog: 8 },
    { id: "ss1", prog: 20 },
    { id: "ss2", prog: 40 },
    { id: "ss3", prog: 62 },
    { id: "ss4", prog: 80 },
    { id: "ss5", prog: 94 },
  ];
  let stepTmr = null;
  const stepDelays = [0, 700, 1800, 3500, 5500, 7500];

  function startAnim() {
    const prog = qs("scan-progress");
    if (prog) prog.style.display = "block";
    const btn = qs("scan-btn");
    if (btn) btn.style.display = "none";
    STEPS.forEach((s) => {
      const el = qs(s.id);
      if (el) el.className = "sp-step";
    });
    setStep(0);
  }

  function setStep(n) {
    for (let i = 0; i < n; i++) {
      const el = qs(STEPS[i].id);
      if (el) el.className = "sp-step done";
    }
    if (n < STEPS.length) {
      const el = qs(STEPS[n].id);
      if (el) el.className = "sp-step active";
    }
    const prog = STEPS[n]?.prog || 95;
    const bar = qs("sp-bar");
    const pct = qs("sp-pct");
    if (bar) bar.style.width = prog + "%";
    if (pct) pct.textContent = prog + "%";
    if (n < STEPS.length - 1) {
      stepTmr = window.setTimeout(() => setStep(n + 1), stepDelays[n + 1] - stepDelays[n]);
    }
  }

  function finishAnim() {
    window.clearTimeout(stepTmr);
    STEPS.forEach((s) => {
      const el = qs(s.id);
      if (el) el.className = "sp-step done";
    });
    const bar = qs("sp-bar");
    const pct = qs("sp-pct");
    if (bar) bar.style.width = "100%";
    if (pct) pct.textContent = "100%";
    window.setTimeout(() => {
      const prog = qs("scan-progress");
      if (prog) prog.style.display = "none";
    }, 600);
  }

  function showQualityErr(msg) {
    const results = qs("results");
    if (results) results.style.display = "block";
    const alertBox = qs("alert-box");
    if (alertBox) {
      alertBox.innerHTML =
        `<div class="alert alert-upgrade">` +
        `<div class="alert-title">📸 Photo quality check failed</div>` +
        `<div style="font-size:.875rem;line-height:1.65;color:var(--w)">${String(msg || "")}</div>` +
        `<div style="font-size:.76rem;margin-top:10px;color:rgba(255,184,48,.7)">Tips: Natural lighting · Hold phone steady · Close-up of skin only · No flash</div>` +
        `</div>`;
      const up = document.getElementById("upgrade-btn");
      up?.addEventListener("click", () => startUpgrade());
      const lk = document.getElementById("pro-link-btn");
      lk?.addEventListener("click", () => linkProFromInput());
    }
    const rm = qs("result-main");
    const gc = qs("guidance-card");
    if (rm) rm.style.display = "none";
    if (gc) gc.style.display = "none";
  }

  function showFreemiumLimit(detail) {
    const results = qs("results");
    if (results) results.style.display = "block";
    const alertBox = qs("alert-box");
    const max = Number(detail?.daily_max);
    const msg = String(detail?.message || "Daily free scan limit reached. Please try again tomorrow.");
    if (alertBox) {
      alertBox.innerHTML =
        `<div class="alert alert-upgrade">` +
        `<div class="alert-title">⏳ Limit reached</div>` +
        `<div style="font-size:.875rem;line-height:1.65;color:var(--w)">${msg}</div>` +
        (Number.isFinite(max) && max > 0
          ? `<div style="font-size:.76rem;margin-top:10px;color:rgba(255,184,48,.7)">Free plan: ${max} scans/day</div>`
          : ``) +
        `<div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:12px;align-items:center">` +
        `<button class="btn-ghost" id="upgrade-btn" type="button">Upgrade to Pro</button>` +
        `<input id="pro-code-in" placeholder="Have a Pro code? Paste here" style="flex:1;min-width:210px;padding:8px 12px;border-radius:12px;border:1px solid var(--border2);background:rgba(255,255,255,.03);color:var(--w);outline:none"/>` +
        `<button class="btn-ghost" id="pro-link-btn" type="button">Unlock</button>` +
        `</div>` +
        `</div>`;
    }
    const rm = qs("result-main");
    const gc = qs("guidance-card");
    const pw = qs("products-wrap");
    if (rm) rm.style.display = "none";
    if (gc) gc.style.display = "none";
    if (pw) pw.style.display = "none";
  }

  async function startUpgrade() {
    try {
      const sid = await ensureSession();
      if (!sid) return alert("Please refresh and try again.");
      const r = await fetch("/billing/checkout", { method: "POST", headers: { "X-Session-Id": sid } });
      if (!r.ok) {
        const t = await r.text().catch(() => "");
        return alert(t || "Billing is not configured yet.");
      }
      const j = await r.json().catch(() => null);
      const url = String(j?.url || "").trim();
      if (!url) return alert("Billing is not configured yet.");
      window.open(url, "_blank", "noopener,noreferrer");
    } catch {
      alert("Could not start upgrade. Please try again.");
    }
  }

  async function linkProFromInput() {
    try {
      const sid = await ensureSession();
      if (!sid) return;
      const inp = document.getElementById("pro-code-in");
      const tok = String(inp?.value || "").trim();
      if (!tok) return alert("Paste your Pro code first.");
      const r = await fetch("/billing/link", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Session-Id": sid },
        body: JSON.stringify({ pro_token: tok }),
      });
      if (!r.ok) return alert("Invalid Pro code.");
      await refreshBilling();
      alert("Pro unlocked on this device.");
    } catch {
      alert("Could not unlock Pro. Try again.");
    }
  }

  function showResults(d) {
    const rm = qs("result-main");
    const gc = qs("guidance-card");
    if (rm) rm.style.display = "";
    if (gc) gc.style.display = "";

    const alertBox = qs("alert-box");
    if (alertBox) alertBox.innerHTML = "";

    const tierTag = qs("tier-tag-el");
    if (tierTag) {
      tierTag.innerHTML = "";
      const u = d?.usage;
      const plan = String(u?.plan || billingPlan || "free");
      if (plan === "pro") {
        tierTag.innerHTML = `<div class="tier-tag tt1">Pro plan · Unlimited scans</div>`;
      } else {
        const rem = Number(u?.daily_remaining);
        const max = Number(u?.daily_max);
        if (Number.isFinite(rem) && Number.isFinite(max) && max > 0) {
          tierTag.innerHTML = `<div class="tier-tag tt1">Free plan · ${rem} scans left today</div>`;
        }
      }
    }

    const topLabel = labelToTitle(d?.top_label);
    const pct = probToPct(d?.top_prob);
    const ringCol = pct > 70 ? "#00f0cc" : pct > 45 ? "#ffb830" : "#ff5757";

    const condEl = qs("r-cond");
    if (condEl) condEl.textContent = topLabel;

    const sevEl = qs("r-sev");
    if (sevEl) {
      sevEl.textContent = "educational";
      sevEl.className = "sev-pill sp-mild";
    }

    const circ = 226.2;
    const offset = circ - (circ * pct) / 100;
    window.setTimeout(() => {
      const ring = qs("r-ring");
      if (ring) {
        ring.style.strokeDashoffset = String(offset);
        ring.style.stroke = ringCol;
      }
      const rn = qs("r-conf-num");
      if (rn) {
        rn.textContent = pct + "%";
        rn.style.color = ringCol;
      }
    }, 120);

    const predsEl = qs("r-preds");
    if (predsEl) {
      predsEl.innerHTML = "";
      const top3 = Array.isArray(d?.top3) ? d.top3 : [];
      const bfCls = ["bf1", "bf2", "bf3"];
      top3.slice(0, 3).forEach((p, i) => {
        const nm = labelToTitle(p?.label);
        const pp = probToPct(p?.prob);
        predsEl.innerHTML += `<div class="pred">
          <span class="pred-n${i === 0 ? " p1" : ""}">${nm}</span>
          <div class="bar-t"><div class="bar-f ${bfCls[i] || "bf3"}" style="width:0%" data-w="${pp}%"></div></div>
          <span class="pred-p" style="color:${i === 0 ? ringCol : "var(--w3)"}">${pp}%</span>
        </div>`;
      });
      window.setTimeout(() => predsEl.querySelectorAll(".bar-f").forEach((b) => (b.style.width = b.dataset.w)), 160);
    }

    // Guidance
    let advice = d?.advice;
    if (Array.isArray(advice)) advice = advice.filter(Boolean).join(" • ");
    const guidance = String(advice || "").trim();
    const guidanceEl = qs("r-guidance");
    if (guidanceEl) guidanceEl.textContent = guidance || "No guidance available.";

    const actionsEl = qs("r-actions");
    if (actionsEl) actionsEl.innerHTML = "";

    const esc = d?.escalation;
    if (actionsEl && esc && typeof esc === "object" && esc.should_consult) {
      const url = String(esc.consult_url || "").trim();
      const label = String(esc.consult_label || "Consult a clinician").trim();
      const reason = String(esc.reason || "If symptoms worsen or you're worried, seek care.").trim();
      const href = url || "#safety";
      actionsEl.innerHTML = `<div class="action-card ac-avoid">
        <div class="ac-eye">Consult</div>
        <div class="ac-item"><span class="ac-dot"></span><span>${reason}</span></div>
        <div style="margin-top:10px">
          <a href="${href}" ${url ? 'target="_blank" rel="noreferrer noopener"' : ""} class="btn-ghost">${label} →</a>
        </div>
      </div>`;
    }

    // Products
    const prods = Array.isArray(d?.products) ? d.products : [];
    const prodWrap = qs("products-wrap");
    const grid = qs("prods-grid");
    const prodTitle = qs("prod-title");
    const prodNote = qs("products-note");
    const tierTagEl = qs("prod-tier-tag");
    if (tierTagEl) {
      tierTagEl.textContent = "";
      tierTagEl.style.display = "none";
    }
    if (prodTitle) prodTitle.textContent = "Matched products";
    if (grid) grid.innerHTML = "";
    if (prodWrap) prodWrap.style.display = prods.length ? "block" : "none";
    if (prodNote) {
      const a = String(d?.affiliate_disclosure || "").trim();
      prodNote.textContent = a;
      prodNote.style.display = a ? "block" : "none";
    }

    if (grid && prods.length) {
      prods.slice(0, 8).forEach((p) => {
        const name = String(p?.name || "Product");
        const reason = String(p?.reason || "");
        const links = Array.isArray(p?.buy_links) ? p.buy_links : [];
        const icon = productIcon(p?.id);
        const linksHtml = links
          .slice(0, 2)
          .map((l) => {
            const url = String(l?.url || "").trim();
            const label = String(l?.name || "Buy").trim();
            if (!url) return "";
            return `<a href="${url}" target="_blank" rel="noreferrer noopener sponsored" class="prod-buy">Buy on ${label} →</a>`;
          })
          .join("");
        grid.innerHTML += `<div class="prod-card">
          <div class="prod-img">${icon}</div>
          <div class="prod-body">
            <div class="prod-name">${name}</div>
            <div class="prod-why">${reason}</div>
            <div class="prod-links">${linksHtml || "<span class='prod-why'>No buy links</span>"}</div>
          </div>
        </div>`;
      });
    }

    // Show model status + disclaimer in safety note (avoid noisy debug when tensorflow works).
    const notes = String(d?.notes || "").trim();
    const backend = String(d?.model_backend || "").trim();
    const disclaimer = String(d?.disclaimer || "").trim();
    const modelLine = backend ? `Model: ${backend}.` : "";
    const notesLine = backend === "tensorflow" ? "" : notes;
    const safetyLine = [modelLine, notesLine, disclaimer].filter(Boolean).join(" ");
    const safetyNote = document.querySelector(".safety-note");
    if (safetyNote && safetyLine) safetyNote.textContent = "⚠️ " + safetyLine;

    const results = qs("results");
    if (results) results.style.display = "block";

    const fb = qs("feedback-wrap");
    if (fb) fb.style.display = "block";
    const thanks = document.querySelector(".fb-thanks");
    if (thanks) thanks.style.display = "none";
    document.querySelectorAll(".fb-btn").forEach((b) => (b.disabled = false));

    results?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function doScan() {
    if (!currentFile) return;
    startAnim();
    const fd = new FormData();
    fd.append("file", currentFile);
    try {
      const sid = await ensureSession();
      const headers = {};
      if (sid) headers["X-Session-Id"] = sid;
      const r = await fetch("/predict", { method: "POST", body: fd, headers });
      if (r.status === 422) {
        const j = await r.json().catch(() => null);
        const d = j?.detail;
        if (d && typeof d === "object" && d.code === "image_quality") {
          finishAnim();
          showQualityErr(String(d.message || "Photo quality issue. Please try again."));
          const btn = qs("scan-btn");
          const txt = qs("scan-btn-txt");
          if (btn) btn.style.display = "inline-flex";
          if (txt) txt.textContent = "🔬 Try again";
          return;
        }
      }
      if (r.status === 429) {
        const j = await r.json().catch(() => null);
        const d = j?.detail;
        const btn = qs("scan-btn");
        const txt = qs("scan-btn-txt");
        finishAnim();
        if (d && typeof d === "object" && d.code === "freemium_limit") {
          showFreemiumLimit(d);
          if (btn) btn.style.display = "inline-flex";
          if (txt) txt.textContent = "Try tomorrow";
          return;
        }
        alert("Too many requests — please wait a few minutes.");
        if (btn) btn.style.display = "inline-flex";
        return;
      }
      if (!r.ok) {
        const text = await r.text().catch(() => "");
        throw new Error(text || `HTTP ${r.status}`);
      }
      const d = await r.json();
      finishAnim();
      scanId = String(d?.scan_id || "");
      lastScan = {
        scan_id: scanId,
        top_label: String(d?.top_label || ""),
        top_prob: Number(d?.top_prob),
        top3: Array.isArray(d?.top3) ? d.top3 : [],
        model_backend: String(d?.model_backend || ""),
      };
      showResults(d);
    } catch {
      finishAnim();
      alert("Analysis failed — please check your connection and try again.");
      const btn = qs("scan-btn");
      if (btn) btn.style.display = "inline-flex";
    }
    const txt = qs("scan-btn-txt");
    const btn = qs("scan-btn");
    if (txt) txt.textContent = "🔬 Scan again";
    if (btn) btn.style.display = "inline-flex";
  }

  async function sendFb(acc, btn) {
    if (!scanId) return;
    document.querySelectorAll(".fb-btn").forEach((b) => (b.disabled = true));
    btn.classList.add("sel");
    try {
      await fetch("/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ts: Date.now(),
          rating: acc ? 1 : -1,
          scan_id: scanId,
          scan: lastScan || undefined,
        }),
        keepalive: true,
      });
    } catch {
      // ignore
    }
    const thanks = document.querySelector(".fb-thanks");
    if (thanks) thanks.style.display = "block";
  }

  // Export functions for inline HTML handlers.
  window.handleFile = handleFile;
  window.doScan = doScan;
  window.sendFb = sendFb;

  /* Scroll reveals */
  const obs = new IntersectionObserver(
    (entries) => {
      entries.forEach((e, i) => {
        if (e.isIntersecting) window.setTimeout(() => e.target.classList.add("visible"), i * 65);
      });
    },
    { threshold: 0.1 },
  );
  document.querySelectorAll(".reveal").forEach((el) => obs.observe(el));
})();
    if (String(d?.top_label || "") === "uncertain") {
      if (prodWrap) prodWrap.style.display = "none";
    }
