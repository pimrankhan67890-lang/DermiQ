function onReady(fn) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", fn, { once: true });
  } else {
    fn();
  }
}

onReady(() => {
  const yearEl = document.getElementById("year");
  if (yearEl) yearEl.textContent = String(new Date().getFullYear());

  const githubLink = document.getElementById("githubLink");
  const contactLink = document.getElementById("contactLink");
  const githubUrl = String(window.DERMIQ_GITHUB_URL || "").trim();
  const contactEmail = String(window.DERMIQ_CONTACT_EMAIL || "").trim();
  if (githubLink) {
    if (githubUrl) githubLink.setAttribute("href", githubUrl);
    else githubLink.setAttribute("href", "https://github.com/");
  }
  if (contactLink) {
    if (contactEmail) contactLink.setAttribute("href", `mailto:${contactEmail}`);
    else contactLink.setAttribute("href", "mailto:support@example.com");
  }

  // Prevent placeholder links from jumping to the top.
  document.querySelectorAll('a[href="#"]').forEach((a) => {
    a.addEventListener("click", (e) => e.preventDefault());
  });

  const apiStatus = document.getElementById("apiStatus");
  const apiError = document.getElementById("apiError");
  const modelStatus = document.getElementById("modelStatus");
  const scanStage = document.getElementById("scanStage");
  const fbUp = document.getElementById("fbUp");
  const fbDown = document.getElementById("fbDown");
  const fbText = document.getElementById("fbText");
  const fbSend = document.getElementById("fbSend");
  const fbStatus = document.getElementById("fbStatus");

  // Optional: server-side routine tracking (timeline) for this device.
  const trackerCard = document.getElementById("trackerCard");
  const trackerEnable = document.getElementById("trackerEnable");
  const trackerRefresh = document.getElementById("trackerRefresh");
  const trackerDelete = document.getElementById("trackerDelete");
  const trackerStatus = document.getElementById("trackerStatus");
  const trackerBanner = document.getElementById("trackerBanner");
  const trackerTimeline = document.getElementById("trackerTimeline");
  const routineProduct = document.getElementById("routineProduct");
  const routineAction = document.getElementById("routineAction");
  const routineFrequency = document.getElementById("routineFrequency");
  const routineNotes = document.getElementById("routineNotes");
  const routineSave = document.getElementById("routineSave");
  const routineStatus = document.getElementById("routineStatus");
  const symptomSeverity = document.getElementById("symptomSeverity");
  const symptomSeverityVal = document.getElementById("symptomSeverityVal");
  const symptomNotes = document.getElementById("symptomNotes");
  const symptomSave = document.getElementById("symptomSave");
  const symptomStatus = document.getElementById("symptomStatus");

  const topLabel = document.getElementById("topLabel");
  const topProb = document.getElementById("topProb");
  const adviceText = document.getElementById("adviceText");
  const notesText = document.getElementById("notesText");
  const productsGrid = document.getElementById("productsGrid");
  const productsEmpty = document.getElementById("productsEmpty");

  const predEls = [
    {
      name: document.getElementById("pred1Name"),
      fill: document.getElementById("pred1Fill"),
      pct: document.getElementById("pred1Pct"),
    },
    {
      name: document.getElementById("pred2Name"),
      fill: document.getElementById("pred2Fill"),
      pct: document.getElementById("pred2Pct"),
    },
    {
      name: document.getElementById("pred3Name"),
      fill: document.getElementById("pred3Fill"),
      pct: document.getElementById("pred3Pct"),
    },
  ];

  let lastScan = null;

  function setError(message) {
    if (!apiError) return;
    if (!message) {
      apiError.hidden = true;
      apiError.textContent = "";
      return;
    }
    apiError.hidden = false;
    apiError.textContent = message;
  }

  function setStatus(message) {
    if (apiStatus) apiStatus.textContent = message;
  }

  function setStage(message) {
    if (!scanStage) return;
    scanStage.textContent = safeText(message);
  }

  function setModelStatus(message) {
    if (!modelStatus) return;
    const s = safeText(message);
    modelStatus.textContent = s;
  }

  function telemetryEnabled() {
    return Boolean(window.DERMIQ_ENABLE_TELEMETRY);
  }

  async function postJson(path, payload) {
    try {
      const base = apiBase();
      await fetch(`${base}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
        keepalive: true,
      });
    } catch {
      // ignore
    }
  }

  function track(eventName, props) {
    if (!telemetryEnabled()) return;
    postJson("/events", {
      event: safeText(eventName),
      ts: Date.now(),
      path: window.location.pathname + window.location.hash,
      props: props || {},
    });
  }

  function apiBase() {
    // Optional override: http://localhost:5173/?api=http://127.0.0.1:8000
    const url = new URL(window.location.href);
    const override = url.searchParams.get("api");
    if (override) return override.replace(/\/+$/, "");
    const configured = String(window.DERMIQ_API_BASE || "").trim();
    if (configured) {
      // If someone forgot to change config and it points to localhost, it will break on mobile/public.
      const host = String(window.location.hostname || "").toLowerCase();
      const isPublicHost = host && host !== "127.0.0.1" && host !== "localhost";
      const isLocalConfigured = /^(https?:\/\/)?(127\.0\.0\.1|localhost)(:\d+)?(\/|$)/i.test(configured);
      if (!(isPublicHost && isLocalConfigured)) return configured.replace(/\/+$/, "");
    }

    // If the landing is served together with the backend (single-origin deploy), use current origin.
    // Keep local default when served from the standalone dev server (5173).
    const port = String(window.location.port || "");
    if (!port || port !== "5173") return window.location.origin;

    return "http://127.0.0.1:8000";
  }

  function labelToTitle(label) {
    const s = String(label || "").trim();
    if (!s) return "Unknown";
    return s
      .split("_")
      .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
      .join(" ");
  }

  function fmtPct(prob) {
    const p = Math.round(Math.max(0, Math.min(1, Number(prob))) * 100);
    return `${p}%`;
  }

  function safeText(x) {
    return String(x ?? "").trim();
  }

  async function clientQualityCheck(file) {
    try {
      if (!file) return { ok: false, message: "No file selected." };
      if (file.size > 10 * 1024 * 1024) return { ok: false, message: "File too large (max 10MB)." };

      const bmp = await createImageBitmap(file);
      const w = bmp.width || 0;
      const h = bmp.height || 0;
      if (Math.min(w, h) < 160) return { ok: false, message: "Photo is too small. Use a closer photo." };

      const maxSide = 256;
      const scale = maxSide / Math.max(w, h);
      const cw = Math.max(1, Math.round(w * Math.min(1, scale)));
      const ch = Math.max(1, Math.round(h * Math.min(1, scale)));
      const canvas = document.createElement("canvas");
      canvas.width = cw;
      canvas.height = ch;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) return { ok: true, message: "" };
      ctx.drawImage(bmp, 0, 0, cw, ch);
      const data = ctx.getImageData(0, 0, cw, ch).data;

      let sum = 0;
      const gray = new Float32Array(cw * ch);
      for (let i = 0, p = 0; i < data.length; i += 4, p++) {
        const r = data[i];
        const g = data[i + 1];
        const b = data[i + 2];
        const y = 0.299 * r + 0.587 * g + 0.114 * b;
        gray[p] = y;
        sum += y;
      }
      const mean = sum / gray.length / 255.0;
      if (mean < 0.18) return { ok: false, message: "Photo is too dark. Move to better lighting and try again." };
      if (mean > 0.98) return { ok: false, message: "Photo is too bright/overexposed. Avoid glare and try again." };

      // Laplacian variance (blur). Conservative threshold to reduce false rejects.
      let lapSum = 0;
      let lapSum2 = 0;
      let n = 0;
      for (let y = 1; y < ch - 1; y++) {
        for (let x = 1; x < cw - 1; x++) {
          const c = gray[y * cw + x];
          const lap = -4 * c + gray[y * cw + (x - 1)] + gray[y * cw + (x + 1)] + gray[(y - 1) * cw + x] + gray[(y + 1) * cw + x];
          lapSum += lap;
          lapSum2 += lap * lap;
          n++;
        }
      }
      if (n > 0) {
        const varLap = lapSum2 / n - (lapSum / n) * (lapSum / n);
        if (varLap < 60) return { ok: false, message: "Photo looks too blurry. Hold steady and make sure the skin is in focus." };
      }

      return { ok: true, message: "" };
    } catch {
      // If the browser can't compute quality, don't block the user.
      return { ok: true, message: "" };
    }
  }

  const TRACKER_STORAGE_KEY = "dermiq_session_id_v1";

  function setTrackerBanner(message) {
    if (!trackerBanner) return;
    const s = safeText(message);
    if (!s) {
      trackerBanner.hidden = true;
      trackerBanner.textContent = "";
      return;
    }
    trackerBanner.hidden = false;
    trackerBanner.textContent = s;
  }

  function setTrackerStatus(message) {
    if (!trackerStatus) return;
    trackerStatus.textContent = safeText(message);
  }

  function setRoutineStatus(message) {
    if (!routineStatus) return;
    routineStatus.textContent = safeText(message);
  }

  function setSymptomStatus(message) {
    if (!symptomStatus) return;
    symptomStatus.textContent = safeText(message);
  }

  function getSessionId() {
    try {
      return safeText(window.localStorage.getItem(TRACKER_STORAGE_KEY));
    } catch {
      return "";
    }
  }

  function setSessionId(sessionId) {
    try {
      window.localStorage.setItem(TRACKER_STORAGE_KEY, safeText(sessionId));
    } catch {
      // ignore
    }
  }

  function clearSessionId() {
    try {
      window.localStorage.removeItem(TRACKER_STORAGE_KEY);
    } catch {
      // ignore
    }
  }

  function fmtDate(tsSeconds) {
    const n = Number(tsSeconds);
    if (!Number.isFinite(n) || n <= 0) return "";
    const d = new Date(n * 1000);
    return d.toLocaleString();
  }

  function escapeHtml(s) {
    return String(s || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('\"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function renderTimeline(events) {
    if (!trackerTimeline) return;
    const list = Array.isArray(events) ? events.slice() : [];
    if (!list.length) {
      trackerTimeline.innerHTML = `<div class="muted">No timeline entries yet.</div>`;
      return;
    }
    // API returns newest first; render oldest first for readability.
    list.reverse();
    trackerTimeline.innerHTML = list
      .map((e) => {
        const kind = safeText(e?.kind) || "event";
        const ts = fmtDate(e?.ts);
        const p = e?.payload || {};
        let msg = "";
        if (kind === "analysis") {
          msg = `Analysis: <b>${escapeHtml(labelToTitle(p?.top_label))}</b> (${escapeHtml(fmtPct(p?.top_prob))})`;
        } else if (kind === "routine") {
          const action = escapeHtml(p?.action || "");
          const name = escapeHtml(p?.product || "");
          const freq = escapeHtml(p?.frequency || "");
          msg = `Routine: <b>${name || "Product"}</b>${action ? ` (${action})` : ""}${freq ? ` - ${freq}` : ""}`;
          if (p?.notes) msg += `<div class="muted" style="margin-top:4px;">${escapeHtml(p.notes)}</div>`;
        } else if (kind === "symptom") {
          const sev = Number(p?.severity);
          msg = `Symptoms: severity <b>${Number.isFinite(sev) ? sev : 0}</b>/10`;
          if (p?.notes) msg += `<div class="muted" style="margin-top:4px;">${escapeHtml(p.notes)}</div>`;
        } else if (kind === "red_flag") {
          const flags = Array.isArray(p?.flags) ? p.flags : [];
          const on = flags.filter((x) => Boolean(x));
          msg = `Red flags: <b>${on.length ? "YES" : "no"}</b>`;
        } else {
          msg = escapeHtml(JSON.stringify(e?.payload || {}));
        }

        return `
          <div class="timeline-item">
            <div>
              <div class="timeline-kind">${escapeHtml(kind)}</div>
              <div class="timeline-msg">${msg}</div>
            </div>
            <div class="timeline-ts">${escapeHtml(ts)}</div>
          </div>
        `;
      })
      .join("");
  }

  async function ensureSession() {
    const existing = getSessionId();
    if (existing) return existing;
    const ok = await checkApi();
    if (!ok) return "";
    setTrackerStatus("Creating sessionâ€¦");
    try {
      const base = apiBase();
      const r = await fetch(`${base}/tracker/session`, { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      const sid = safeText(j?.session_id);
      if (!sid) throw new Error("No session id");
      setSessionId(sid);
      setTrackerStatus("Tracking enabled.");
      return sid;
    } catch {
      setTrackerStatus("Could not enable tracking.");
      return "";
    }
  }

  async function postTracker(kind, payload) {
    const sid = getSessionId();
    if (!sid) return false;
    const ok = await checkApi();
    if (!ok) return false;
    try {
      const base = apiBase();
      const body = {
        session_id: sid,
        kind: safeText(kind),
        ts: Math.floor(Date.now() / 1000),
        payload: payload || {},
      };
      const r = await fetch(`${base}/tracker/event`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      return r.ok;
    } catch {
      return false;
    }
  }

  async function refreshTimeline() {
    const sid = getSessionId();
    if (!sid) {
      setTrackerStatus("Tracking is off.");
      setTrackerBanner("");
      renderTimeline([]);
      return;
    }
    const ok = await checkApi();
    if (!ok) return;
    setTrackerStatus("Loading timelineâ€¦");
    try {
      const base = apiBase();
      const r = await fetch(`${base}/tracker/timeline?session_id=${encodeURIComponent(sid)}&limit=200`, { method: "GET" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      const events = Array.isArray(j?.events) ? j.events : [];
      const esc = j?.escalation || {};
      const level = safeText(esc?.level);
      const reason = safeText(esc?.reason);
      if (level === "urgent") {
        setTrackerBanner(`Safety check: please consult a clinician promptly. ${reason}`);
      } else if (level === "caution") {
        setTrackerBanner(`Safety check: consider consulting a clinician. ${reason}`);
      } else {
        setTrackerBanner("");
      }
      renderTimeline(events);
      setTrackerStatus("Timeline updated.");
    } catch {
      setTrackerStatus("Timeline error.");
    }
  }

  function productIcon(productId) {
    const s = String(productId || "").toLowerCase();
    if (s.includes("sunscreen") || s.includes("spf")) return "☀️";
    if (s.includes("serum") || s.includes("acid")) return "💧";
    if (s.includes("shampoo")) return "🫧";
    if (s.includes("cleanser") || s.includes("wash")) return "🧴";
    if (s.includes("cream") || s.includes("ceramide") || s.includes("moist")) return "🧴";
    return "🧴";
  }

  function clearProducts(message) {
    if (productsGrid) productsGrid.innerHTML = "";
    if (productsEmpty) {
      const msg = safeText(message);
      productsEmpty.hidden = !msg;
      if (msg) productsEmpty.textContent = msg;
    }
  }

  function renderProducts(products, top3Raw) {
    if (!productsGrid) return;

    const list = Array.isArray(products) ? products : [];
    productsGrid.innerHTML = "";

    if (!list.length) {
      clearProducts("No product links available for this result.");
      return;
    }

    if (productsEmpty) productsEmpty.hidden = true;

    const top3 = Array.isArray(top3Raw) ? top3Raw : [];
    const topLabels = top3.map((t) => safeText(t?.label)).filter(Boolean);

    list.forEach((p) => {
      const card = document.createElement("div");
      card.className = "product-card reveal visible";

      const img = document.createElement("div");
      img.className = "product-img";
      img.textContent = productIcon(p?.id);

      const info = document.createElement("div");
      info.className = "product-info";

      const productTag = document.createElement("div");
      productTag.className = "product-tag";
      const conditions = Array.isArray(p?.conditions) ? p.conditions.map((c) => safeText(c)).filter(Boolean) : [];
      const matched = topLabels.find((l) => conditions.includes(l));
      productTag.textContent = matched ? `${labelToTitle(matched)} match` : "Recommended";

      const name = document.createElement("div");
      name.className = "product-name";
      name.textContent = safeText(p?.name) || "Product";

      const desc = document.createElement("div");
      desc.className = "product-desc";
      desc.textContent = safeText(p?.reason) || "Suggested based on your top result.";

      const buy = document.createElement("div");
      buy.className = "product-buy";
      buy.style.justifyContent = "flex-start";

      const linksWrap = document.createElement("div");
      linksWrap.style.display = "flex";
      linksWrap.style.flexWrap = "wrap";
      linksWrap.style.gap = "10px";

      const links = Array.isArray(p?.buy_links) ? p.buy_links : [];
      if (!links.length) {
        const empty = document.createElement("span");
        empty.className = "product-desc";
        empty.style.marginBottom = "0";
        empty.textContent = "No buy links provided.";
        linksWrap.appendChild(empty);
      } else {
        links.slice(0, 4).forEach((l) => {
          const url = safeText(l?.url);
          const label = safeText(l?.name) || "Buy / View";
          if (!url) return;

          const a = document.createElement("a");
          a.className = "product-link";
          a.href = url;
          a.target = "_blank";
          a.rel = "noreferrer noopener";
          a.textContent = `Buy on ${label} →`;
          linksWrap.appendChild(a);
        });
      }

      buy.appendChild(linksWrap);

      info.appendChild(productTag);
      info.appendChild(name);
      info.appendChild(desc);
      info.appendChild(buy);

      card.appendChild(img);
      card.appendChild(info);
      productsGrid.appendChild(card);
    });
  }

  async function checkApi() {
    setError("");
    const base = apiBase();
    setStatus(`API: checking (${base})…`);
    try {
      // Render free-tier can take ~50s to wake. Retry a few times with a short timeout.
      const url = `${base}/health`;
      let lastErr = "";
      for (let attempt = 1; attempt <= 5; attempt++) {
        const controller = new AbortController();
        const t = window.setTimeout(() => controller.abort(), 12000);
        try {
          if (attempt > 1) setStatus(`API: waking up… (try ${attempt}/5)`);
          const r = await fetch(url, { method: "GET", signal: controller.signal });
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          window.clearTimeout(t);
          lastErr = "";
          break;
        } catch (e) {
          window.clearTimeout(t);
          lastErr = e?.message ? String(e.message) : "Request failed";
          // Small delay between attempts.
          await new Promise((res) => window.setTimeout(res, 900));
        }
      }
      if (lastErr) throw new Error(lastErr);

      setStatus("API: online ✅");

      // Optional: show model status so users understand whether this is a real model or demo fallback.
      try {
        const m = await fetch(`${base}/model`, { method: "GET" });
        if (m.ok) {
          const j = await m.json();
          const backend = safeText(j?.model_backend);
          if (backend && backend !== "tensorflow") {
            setModelStatus("Model: demo fallback (heuristic). Accuracy will be limited until a trained model is installed.");
          } else if (backend) {
            setModelStatus("Model: tensorflow (trained model loaded).");
          } else {
            setModelStatus("");
          }
        } else {
          setModelStatus("");
        }
      } catch {
        setModelStatus("");
      }
      return true;
    } catch {
      setStatus("API: offline ❌");

      const host = String(window.location.hostname || "").toLowerCase();
      const isGitHubPages = host.endsWith("github.io");
      const isLocalHost = host === "127.0.0.1" || host === "localhost";
      const configured = String(window.DERMIQ_API_BASE || "").trim();
      const usingSameOrigin = base === window.location.origin;

      if (!isLocalHost && isGitHubPages && usingSameOrigin && !configured) {
        setError(
          `Backend API not reachable from this site.\n\n` +
            `You are hosting the landing separately (GitHub Pages). Set DERMIQ_API_BASE in landing/config.js to your backend URL (e.g. https://your-backend.onrender.com), redeploy, then refresh.`,
        );
      } else {
        setError(
          `Backend API not reachable.\n\n` +
            `If you are using Render free tier, wait ~50 seconds and refresh (cold start).\n` +
            `If you deployed frontend separately, set DERMIQ_API_BASE in landing/config.js to the public backend URL.\n\n` +
            `Dev (local) start commands:\n` +
            `python -m venv .venv\n` +
            `.\\.venv\\Scripts\\Activate.ps1\n` +
            `pip install -r backend/requirements-ml.txt\n` +
            `python -m uvicorn backend.main:app --reload --port 8000`,
        );
      }
      setModelStatus("");
      return false;
    }
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry, index) => {
        if (!entry.isIntersecting) return;
        window.setTimeout(() => entry.target.classList.add("visible"), index * 80);
      });
    },
    { threshold: 0.1 },
  );
  document.querySelectorAll(".reveal").forEach((el) => observer.observe(el));

  const uploadBtn = document.querySelector(".upload-btn");
  const uploadDemo = document.querySelector(".upload-demo");
  const uploadTitle = document.querySelector(".upload-demo-text");
  const uploadSub = document.querySelector(".upload-demo-sub");
  const hasDemo = Boolean(uploadBtn || uploadDemo || topLabel || apiStatus);
  if (!hasDemo) return;

  // Simple demo interaction: pick a file and show its name (no upload).
  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = "image/*";
  fileInput.style.display = "none";
  document.body.appendChild(fileInput);

  function openPicker() {
    fileInput.click();
  }

  uploadBtn?.addEventListener("click", openPicker);
  uploadDemo?.addEventListener("click", (e) => {
    if (e.target instanceof HTMLAnchorElement || e.target instanceof HTMLButtonElement) return;
    openPicker();
  });

  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    if (uploadTitle) uploadTitle.textContent = "Selected:";
    if (uploadSub) uploadSub.textContent = file.name;

    runPrediction(file).catch(() => {});
  });

  async function runPrediction(file) {
    setError("");
    setStage("");

    setStage("Checking photo quality…");
    const q = await clientQualityCheck(file);
    if (!q.ok) {
      setStatus("API: waiting for a better photo");
      setError(q.message);
      clearProducts("");
      return;
    }

    const ok = await checkApi();
    if (!ok) return;

    setStage("Preprocessing…");
    setStatus("API: analyzing…");
    if (topLabel) topLabel.textContent = "Analyzing…";
    if (topProb) topProb.textContent = "";
    if (adviceText) adviceText.textContent = "Analyzing your photo…";
    if (notesText) notesText.textContent = "";
    clearProducts("Loading product links…");

    const base = apiBase();
    const form = new FormData();
    form.append("file", file, file.name || "upload.jpg");

    try {
      const headers = {};
      const sid = getSessionId();
      if (sid) headers["X-Session-Id"] = sid;
      setStage("Running model…");
      const resp = await fetch(`${base}/predict`, { method: "POST", body: form, headers });
      if (!resp.ok) {
        const ct = String(resp.headers.get("content-type") || "");
        if (ct.includes("application/json")) {
          const j = await resp.json().catch(() => null);
          const detail = j?.detail;
          if (detail && typeof detail === "object" && detail.code === "image_quality") {
            throw new Error(detail.message || "Photo quality issue. Please try again.");
          }
        }
        const text = await resp.text().catch(() => "");
        throw new Error(text || `HTTP ${resp.status}`);
      }
      const data = await resp.json();
      lastScan = {
        scan_id: safeText(data?.scan_id),
        top_label: safeText(data?.top_label),
        top_prob: Number(data?.top_prob),
        top3: Array.isArray(data?.top3) ? data.top3 : [],
        model_backend: safeText(data?.model_backend),
      };

      const top = labelToTitle(data?.top_label);
      const prob = fmtPct(data?.top_prob);
      if (topLabel) topLabel.textContent = top;
      if (topProb) topProb.textContent = `${prob} match`;

      const top3 = Array.isArray(data?.top3) ? data.top3 : [];
      for (let i = 0; i < predEls.length; i++) {
        const el = predEls[i];
        const item = top3[i];
        const label = labelToTitle(item?.label);
        const pct = fmtPct(item?.prob);
        if (el.name) el.name.textContent = label;
        if (el.pct) el.pct.textContent = pct;
        if (el.fill) el.fill.style.width = pct;
      }

      let advice = data?.advice;
      if (Array.isArray(advice)) advice = advice.filter(Boolean).join(" • ");
      if (adviceText) adviceText.textContent = String(advice || "").trim() || "No advice available.";
      const notes = String(data?.notes || "").trim();
      const backend = String(data?.model_backend || "").trim();
      const disclaimer = String(data?.disclaimer || "").trim();
      if (notesText) {
        const noteLine = backend === "tensorflow" ? "" : notes;
        notesText.textContent = [backend ? `Model: ${backend}.` : "", noteLine, disclaimer].filter(Boolean).join(" ");
      }

      setStage("Matching products…");
      renderProducts(data?.products, data?.top3);
      setStatus("API: done ✅");
      setStage("Done.");
      track("predict_success", {
        top_label: safeText(data?.top_label),
        top_prob: Number(data?.top_prob),
        model_backend: safeText(data?.model_backend),
      });
      if (getSessionId()) refreshTimeline().catch(() => {});
      if (trackerCard) trackerCard.hidden = false;
    } catch (e) {
      setStatus("API: error ❌");
      setStage("");
      setError(`Prediction failed: ${e?.message ? String(e.message) : "Unknown error"}`);
      clearProducts("");
      track("predict_error", { message: e?.message ? String(e.message) : "Unknown error" });
    }
  }

  // Initial health check so the UI tells you what to start.
  checkApi().catch(() => {});
  track("page_view", { host: window.location.host });

  // Tracker wiring (optional).
  function updateTrackerUiState() {
    const sid = getSessionId();
    if (trackerEnable) trackerEnable.textContent = sid ? "Tracking enabled" : "Enable tracking";
    setTrackerStatus(sid ? "Tracking is on for this device." : "Tracking is off.");
  }

  updateTrackerUiState();
  const existingSid = getSessionId();
  if (existingSid && trackerCard) trackerCard.hidden = false;
  if (existingSid) refreshTimeline().catch(() => {});

  if (symptomSeverity && symptomSeverityVal) {
    const sync = () => (symptomSeverityVal.textContent = safeText(symptomSeverity.value));
    symptomSeverity.addEventListener("input", sync);
    sync();
  }

  trackerEnable?.addEventListener("click", async () => {
    setTrackerBanner("");
    const sid = await ensureSession();
    updateTrackerUiState();
    if (sid && trackerCard) trackerCard.hidden = false;
    if (sid) await refreshTimeline();
  });

  trackerRefresh?.addEventListener("click", async () => {
    await refreshTimeline();
  });

  trackerDelete?.addEventListener("click", async () => {
    const sid = getSessionId();
    if (!sid) {
      setTrackerStatus("Nothing to delete.");
      return;
    }
    if (!window.confirm("Delete your tracking data for this device on this server?")) return;
    const ok = await checkApi();
    if (!ok) return;
    setTrackerStatus("Deletingâ€¦");
    try {
      const base = apiBase();
      const r = await fetch(`${base}/tracker/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sid }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      clearSessionId();
      updateTrackerUiState();
      setTrackerBanner("");
      renderTimeline([]);
      setTrackerStatus("Deleted.");
    } catch {
      setTrackerStatus("Delete failed.");
    }
  });

  routineSave?.addEventListener("click", async () => {
    const sid = await ensureSession();
    if (!sid) return;
    const product = safeText(routineProduct?.value);
    const action = safeText(routineAction?.value);
    const frequency = safeText(routineFrequency?.value);
    const notes = safeText(routineNotes?.value);
    if (!product) {
      setRoutineStatus("Add a product name.");
      return;
    }
    setRoutineStatus("Savingâ€¦");
    const ok = await postTracker("routine", { product, action, frequency, notes });
    setRoutineStatus(ok ? "Saved." : "Save failed.");
    if (ok) {
      if (routineProduct) routineProduct.value = "";
      if (routineNotes) routineNotes.value = "";
      await refreshTimeline();
    }
  });

  symptomSave?.addEventListener("click", async () => {
    const sid = await ensureSession();
    if (!sid) return;
    const severity = Number(symptomSeverity?.value || 0);
    const notes = safeText(symptomNotes?.value);
    const flags = Array.from(document.querySelectorAll('.tracker-flags input[type="checkbox"][data-flag]')).map((el) =>
      Boolean(el && el.checked),
    );
    setSymptomStatus("Savingâ€¦");
    if (flags.some(Boolean)) {
      await postTracker("red_flag", { flags });
    }
    const ok = await postTracker("symptom", { severity, notes });
    setSymptomStatus(ok ? "Saved." : "Save failed.");
    if (ok) {
      if (symptomNotes) symptomNotes.value = "";
      await refreshTimeline();
    }
  });

  let lastThumb = 0;
  function setFbStatus(msg) {
    if (!fbStatus) return;
    fbStatus.textContent = safeText(msg);
  }
  fbUp?.addEventListener("click", () => {
    lastThumb = 1;
    setFbStatus("Selected 👍");
  });
  fbDown?.addEventListener("click", () => {
    lastThumb = -1;
    setFbStatus("Selected 👎");
  });
  fbSend?.addEventListener("click", async () => {
    if (!telemetryEnabled()) {
      setFbStatus("Feedback disabled.");
      return;
    }
    const text = safeText(fbText?.value);
    setFbStatus("Sending…");
    await postJson("/feedback", {
      ts: Date.now(),
      rating: lastThumb,
      message: text,
      scan: lastScan || undefined,
    });
    setFbStatus("Thanks!");
    if (fbText) fbText.value = "";
  });
});
