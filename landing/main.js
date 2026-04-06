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

  function setModelStatus(message) {
    if (!modelStatus) return;
    const s = safeText(message);
    modelStatus.textContent = s;
  }

  function apiBase() {
    // Optional override: http://localhost:5173/?api=http://127.0.0.1:8000
    const url = new URL(window.location.href);
    const override = url.searchParams.get("api");
    if (override) return override.replace(/\/+$/, "");
    const configured = String(window.DERMIQ_API_BASE || "").trim();
    if (configured) return configured.replace(/\/+$/, "");

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
      const r = await fetch(`${base}/health`, { method: "GET" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
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
      setError(
        `Backend API not running. Start it from repo root:\n` +
          `python -m venv .venv\n` +
          `.\\.venv\\Scripts\\Activate.ps1\n` +
          `pip install -r backend/requirements.txt\n` +
          `python -m uvicorn backend.main:app --reload --port 8000\n` +
          `\nThen refresh this page.`,
      );
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
    const ok = await checkApi();
    if (!ok) return;

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
      const resp = await fetch(`${base}/predict`, { method: "POST", body: form });
      if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        throw new Error(text || `HTTP ${resp.status}`);
      }
      const data = await resp.json();

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
        notesText.textContent = [backend ? `Model: ${backend}.` : "", notes, disclaimer].filter(Boolean).join(" ");
      }

      renderProducts(data?.products, data?.top3);
      setStatus("API: done ✅");
    } catch (e) {
      setStatus("API: error ❌");
      setError(`Prediction failed: ${e?.message ? String(e.message) : "Unknown error"}`);
      clearProducts("");
    }
  }

  // Initial health check so the UI tells you what to start.
  checkApi().catch(() => {});
});
