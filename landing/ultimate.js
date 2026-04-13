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
  const CART_KEY = "dermiq_cart_v1";
  let cartIds = [];
  let cartPrefs = { preferred_store: "", note: "" };
  let exploreCategory = "sunscreen";
  const catalogCache = new Map();
  let matchedProducts = [];
  let cameraStream = null;
  let lastCapturedBlob = null;
  const selectedSymptoms = new Set();

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

  function clinicalContext() {
    return {
      body_zone: String(qs("meta-body-zone")?.value || "").trim(),
      duration_days: Number(qs("meta-duration")?.value || 0),
      severity: Number(qs("meta-severity")?.value || 0),
      triggers: String(qs("meta-triggers")?.value || "")
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean),
      symptoms: Array.from(selectedSymptoms),
    };
  }

  function setCameraGuidance(text) {
    const el = qs("camera-guidance");
    if (el) el.textContent = text;
  }

  function outHref(url, store, productId) {
    const u = String(url || "").trim();
    if (!u) return "#";
    const sid = String(sessionId || "").trim();
    const params = new URLSearchParams();
    params.set("url", u);
    if (store) params.set("store", String(store));
    if (productId) params.set("product_id", String(productId));
    if (scanId) params.set("scan_id", String(scanId));
    if (sid) params.set("session_id", sid);
    return "/out?" + params.toString();
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

  function loadCart() {
    try {
      const raw = window.localStorage.getItem(CART_KEY);
      const arr = raw ? JSON.parse(raw) : [];
      cartIds = Array.isArray(arr) ? arr.map((x) => String(x || "").trim()).filter(Boolean) : [];
    } catch {
      cartIds = [];
    }
  }

  function saveCart() {
    try {
      window.localStorage.setItem(CART_KEY, JSON.stringify(cartIds.slice(0, 30)));
    } catch {}
  }

  function loadCartPrefs() {
    try {
      cartPrefs = {
        preferred_store: String(qs("pref-store")?.value || "").trim(),
        note: String(qs("pref-note")?.value || "").trim(),
      };
    } catch {
      cartPrefs = { preferred_store: "", note: "" };
    }
  }

  function applyCartPrefs(prefs) {
    const p = prefs && typeof prefs === "object" ? prefs : {};
    const preferredStore = String(p.preferred_store || "").trim();
    const note = String(p.note || "").trim();
    if (qs("pref-store")) qs("pref-store").value = preferredStore;
    if (qs("pref-note")) qs("pref-note").value = note;
    cartPrefs = { preferred_store: preferredStore, note };
  }

  async function logTrackerEvent(kind, payload) {
    const sid = await ensureSession();
    if (!sid) return;
    try {
      await fetch("/tracker/event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sid, kind, payload: payload || {} }),
      });
    } catch {}
  }

  async function logCartUpdate() {
    loadCartPrefs();
    await logTrackerEvent("cart_update", {
      product_ids: cartIds.slice(0, 30),
      scan_id: scanId || "",
      preferred_store: cartPrefs.preferred_store,
      note: cartPrefs.note,
    });
  }

  function allKnownProducts() {
    const items = [];
    const seen = new Set();
    matchedProducts.forEach((product) => {
      const id = String(product?.id || "").trim();
      if (!id || seen.has(id)) return;
      seen.add(id);
      items.push(product);
    });
    catalogCache.forEach((payload) => {
      const products = Array.isArray(payload?.products) ? payload.products : [];
      products.forEach((product) => {
        const id = String(product?.id || "").trim();
        if (!id || seen.has(id)) return;
        seen.add(id);
        items.push(product);
      });
    });
    return items;
  }

  function renderCart(catalogProducts) {
    const wrap = qs("cart-wrap");
    const box = qs("cart-items");
    if (!wrap || !box) return;

    if (!cartIds.length) {
      wrap.style.display = "none";
      box.innerHTML = "";
      return;
    }

    wrap.style.display = "block";
    const sourceProducts = Array.isArray(catalogProducts) && catalogProducts.length ? catalogProducts : allKnownProducts();
    const idx = new Map((sourceProducts || []).map((p) => [String(p?.id || ""), p]));
    box.innerHTML = "";
    cartIds.forEach((id) => {
      const p = idx.get(id);
      const name = String(p?.name || id);
      const cat = String(p?.category || "");
      box.innerHTML += `<div class="cart-row">
        <div>
          <div class="cart-item">${name}</div>
          <div class="cart-sub">${cat ? "Category: " + cat : ""}</div>
        </div>
        <button class="cart-x" type="button" data-rm="${id}">Remove</button>
      </div>`;
    });
    box.querySelectorAll("[data-rm]").forEach((b) =>
      b.addEventListener("click", () => {
        const id = String(b.getAttribute("data-rm") || "").trim();
        if (!id) return;
        cartIds = cartIds.filter((x) => x !== id);
        saveCart();
        renderCart(allKnownProducts());
        logCartUpdate().catch(() => {});
      }),
    );
  }

  async function fetchCatalog(category) {
    const cat = String(category || "").trim().toLowerCase();
    if (catalogCache.has(cat)) return catalogCache.get(cat);
    const r = await fetch(`/products?category=${encodeURIComponent(cat)}&limit=200`);
    if (!r.ok) throw new Error("catalog");
    const j = await r.json().catch(() => null);
    const prods = Array.isArray(j?.products) ? j.products : [];
    const payload = { products: prods, affiliate_disclosure: String(j?.affiliate_disclosure || ""), disclaimer: String(j?.disclaimer || "") };
    catalogCache.set(cat, payload);
    return payload;
  }

  function buildHubProducts(category, payload) {
    const prods = Array.isArray(payload?.products) ? payload.products : [];
    const merged = new Map();
    matchedProducts.forEach((product) => {
      const id = String(product?.id || "").trim();
      if (id) merged.set(id, { ...product, _source: "matched" });
    });
    prods.forEach((product) => {
      const id = String(product?.id || "").trim();
      if (!id) return;
      if (merged.has(id)) merged.set(id, { ...merged.get(id), ...product, _source: "matched" });
      else merged.set(id, { ...product, _source: "explore" });
    });
    const cat = String(category || "").trim().toLowerCase();
    return Array.from(merged.values())
      .filter((product) => product?._source === "matched" || String(product?.category || "").trim().toLowerCase() === cat)
      .sort((a, b) => {
        const am = a?._source === "matched" ? 0 : 1;
        const bm = b?._source === "matched" ? 0 : 1;
        if (am !== bm) return am - bm;
        const ar = Number(a?.rank || 999);
        const br = Number(b?.rank || 999);
        if (ar !== br) return ar - br;
        return String(a?.name || "").localeCompare(String(b?.name || ""));
      });
  }

  function renderHub(category, payload) {
    const wrap = qs("products-wrap");
    const grid = qs("prods-grid");
    const prodTitle = qs("prod-title");
    const prodNote = qs("products-note");
    const hubNote = qs("hub-note");
    if (!wrap || !grid) return;
    wrap.style.display = "block";

    const prods = buildHubProducts(category, payload);
    const matchCount = prods.filter((product) => product?._source === "matched").length;
    const topLabel = String(lastScan?.top_label || "").trim();
    if (prodTitle) {
      prodTitle.textContent = topLabel && topLabel !== "uncertain" ? `Smart product hub for ${labelToTitle(topLabel)}` : "Smart product hub";
    }
    if (prodNote) {
      const affiliate = String(payload?.affiliate_disclosure || "").trim();
      const intro =
        matchCount > 0
          ? `${matchCount} matched pick${matchCount === 1 ? "" : "s"} appear first. Switch tabs to compare category alternatives in the same hub.`
          : "Compare curated products by category in one place, then shortlist what you want to try.";
      prodNote.textContent = [intro, affiliate].filter(Boolean).join(" ");
      prodNote.style.display = "block";
    }
    if (hubNote) {
      hubNote.textContent =
        "DermIQ helps you compare and shortlist products here. When you click a store button, checkout finishes on Amazon, Flipkart, or PharmEasy.";
    }

    grid.innerHTML = "";
    if (!prods.length) {
      grid.innerHTML = `<div class="products-note">No products found for this category yet.</div>`;
      return;
    }

    prods.slice(0, 18).forEach((p) => {
      const id = String(p?.id || "");
      const name = String(p?.name || "Product");
      const reason = String(p?.reason || "");
      const icon = productIcon(id);
      const badge = String(p?.pick_badge || "").trim();
      const links = Array.isArray(p?.buy_links) ? p.buy_links : [];
      const linksHtml = links
        .slice(0, 2)
        .map((l) => {
          const url = String(l?.url || "").trim();
          const label = String(l?.name || "Buy").trim();
          if (!url) return "";
          const href = outHref(url, label, id);
          return `<a href="${href}" target="_blank" rel="noreferrer noopener sponsored" class="prod-buy">Buy on ${label} →</a>`;
        })
        .join("");

      const inCart = cartIds.includes(id);
      grid.innerHTML += `<div class="prod-card">
        <div class="prod-img">
          ${icon}
          ${badge ? `<span class="prod-tag-badge tag-spf">${badge}</span>` : ""}
        </div>
        <div class="prod-body">
          <div class="prod-name">${name}</div>
          <div class="prod-why">${p?._source === "matched" ? "Matched after your scan. " : ""}${reason}</div>
          <div class="prod-actions">
            <button class="btn-mini pri" type="button" data-add="${id}">${inCart ? "Added" : "Add to cart"}</button>
            <button class="btn-mini" type="button" data-view="${id}">Show links</button>
          </div>
          <div class="prod-links" id="links-${id}" style="display:none">${linksHtml || "<span class='prod-why'>No buy links</span>"}</div>
        </div>
      </div>`;
    });

    grid.querySelectorAll("[data-add]").forEach((b) =>
      b.addEventListener("click", () => {
        const id = String(b.getAttribute("data-add") || "").trim();
        if (!id) return;
        if (!cartIds.includes(id)) cartIds.push(id);
        cartIds = cartIds.slice(0, 30);
        saveCart();
        renderHub(category, payload);
        renderCart(prods);
        logCartUpdate().catch(() => {});
      }),
    );
    grid.querySelectorAll("[data-view]").forEach((b) =>
      b.addEventListener("click", () => {
        const id = String(b.getAttribute("data-view") || "").trim();
        const el = document.getElementById("links-" + id);
        if (!el) return;
        el.style.display = el.style.display === "none" ? "flex" : "none";
      }),
    );

    renderCart(prods);
  }

  function renderExplorerList(category, payload) {
    const wrap = qs("explore-wrap");
    const grid = qs("explore-grid");
    if (!wrap || !grid) return;
    wrap.style.display = "block";
    const prods = Array.isArray(payload?.products) ? payload.products : [];
    grid.innerHTML = "";

    if (!prods.length) {
      grid.innerHTML = `<div class="products-note">No products found for this category yet.</div>`;
      return;
    }

    prods.slice(0, 18).forEach((p) => {
      const id = String(p?.id || "");
      const name = String(p?.name || "Product");
      const reason = String(p?.reason || "");
      const icon = productIcon(id);
      const badge = String(p?.pick_badge || "").trim();
      const links = Array.isArray(p?.buy_links) ? p.buy_links : [];
      const linksHtml = links
        .slice(0, 2)
        .map((l) => {
          const url = String(l?.url || "").trim();
          const label = String(l?.name || "Buy").trim();
          if (!url) return "";
          const href = outHref(url, label, id);
          return `<a href="${href}" target="_blank" rel="noreferrer noopener sponsored" class="prod-buy">Buy on ${label} →</a>`;
        })
        .join("");

      const inCart = cartIds.includes(id);
      grid.innerHTML += `<div class="prod-card">
        <div class="prod-img">
          ${icon}
          ${badge ? `<span class="prod-tag-badge tag-spf">${badge}</span>` : ""}
        </div>
        <div class="prod-body">
          <div class="prod-name">${name}</div>
          <div class="prod-why">${reason}</div>
          <div class="prod-actions">
            <button class="btn-mini pri" type="button" data-add="${id}">${inCart ? "Added" : "Add to cart"}</button>
            <button class="btn-mini" type="button" data-view="${id}">Show links</button>
          </div>
          <div class="prod-links" id="links-${id}" style="display:none">${linksHtml || "<span class='prod-why'>No buy links</span>"}</div>
        </div>
      </div>`;
    });

    grid.querySelectorAll("[data-add]").forEach((b) =>
      b.addEventListener("click", () => {
        const id = String(b.getAttribute("data-add") || "").trim();
        if (!id) return;
        if (!cartIds.includes(id)) cartIds.push(id);
        cartIds = cartIds.slice(0, 30);
        saveCart();
        renderExplorerList(category, payload);
        renderCart(prods);
        logCartUpdate().catch(() => {});
      }),
    );
    grid.querySelectorAll("[data-view]").forEach((b) =>
      b.addEventListener("click", () => {
        const id = String(b.getAttribute("data-view") || "").trim();
        const el = document.getElementById("links-" + id);
        if (!el) return;
        el.style.display = el.style.display === "none" ? "flex" : "none";
      }),
    );

    renderCart(prods);
  }

  async function loadExplorer(category) {
    exploreCategory = String(category || "").trim().toLowerCase() || "sunscreen";
    const payload = await fetchCatalog(exploreCategory);
    const hubProducts = buildHubProducts(exploreCategory, payload);
    await logTrackerEvent("product_view", {
      category: exploreCategory,
      product_ids: hubProducts.slice(0, 18).map((p) => String(p?.id || "")).filter(Boolean),
      scan_id: scanId || "",
    });
    renderHub(exploreCategory, payload);
  }

  async function restoreCartFromServer() {
    const sid = await ensureSession();
    if (!sid) return;
    try {
      const r = await fetch(`/tracker/timeline?session_id=${encodeURIComponent(sid)}&limit=50`);
      if (!r.ok) return;
      const j = await r.json().catch(() => null);
      const events = Array.isArray(j?.events) ? j.events : [];
      const found = events.find((e) => String(e?.kind || "") === "cart_update" && e?.payload && typeof e.payload === "object");
      if (!found) return;
      const payload = found.payload || {};
      const ids = Array.isArray(payload.product_ids) ? payload.product_ids.map((x) => String(x || "").trim()).filter(Boolean) : [];
      if (ids.length && !cartIds.length) {
        cartIds = ids.slice(0, 30);
        saveCart();
      }
      applyCartPrefs(payload);
    } catch {}
  }

  async function generateRoutinePlan() {
    if (!cartIds.length) return alert("Add at least one product to your cart.");
    const sid = await ensureSession();
    if (!sid) return alert("Please refresh and try again.");

    const prefs = {
      sensitive_skin: !!qs("pref-sensitive")?.checked,
      fragrance_free: !!qs("pref-fragrance")?.checked,
      pregnancy_safe: !!qs("pref-pregnancy")?.checked,
      ampm: !!qs("pref-ampm")?.checked,
      preferred_store: String(qs("pref-store")?.value || "").trim(),
      note: String(qs("pref-note")?.value || "").trim(),
    };

    const payload = {
      scan_id: scanId || "",
      top_label: String(lastScan?.top_label || ""),
      selected_products: cartIds.slice(0, 30),
      preferences: prefs,
    };

    const r = await fetch("/routine/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Session-Id": sid },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      const t = await r.text().catch(() => "");
      throw new Error(t || "routine");
    }
    const j = await r.json().catch(() => null);
    const plan = j?.plan || {};

    const rw = qs("routine-wrap");
    if (rw) rw.style.display = "block";
    const note = qs("routine-note");
    if (note) note.textContent = "Built from your selected products" + (lastScan?.top_label ? ` · Based on: ${labelToTitle(lastScan.top_label)}` : "");
    const headline = qs("routine-headline");
    if (headline) headline.textContent = String(plan.headline || "Keep the routine simple and consistent.");
    const focus = qs("routine-focus-copy");
    if (focus) focus.textContent = String(plan.today_focus || "Introduce products one at a time and track how your skin responds.");
    const stage = qs("routine-stage");
    if (stage) stage.textContent = `Protocol stage: ${String(plan.protocol_stage || "starting").replaceAll("_", " ")}`;
    const confidence = qs("routine-confidence");
    if (confidence) confidence.textContent = `Confidence mode: ${String(plan.confidence_mode || "uncertain").replaceAll("_", " ")}`;
    const safety = qs("routine-safety");
    if (safety) safety.textContent = "⚠️ " + String(j?.safety || "");

    function renderList(id, arr) {
      const el = qs(id);
      if (!el) return;
      const a = Array.isArray(arr) ? arr : [];
      el.innerHTML = a.map((x) => `<div class="routine-li">• ${String(x)}</div>`).join("") || `<div class="products-note">No items.</div>`;
    }

    renderList("routine-am", plan.am);
    renderList("routine-pm", plan.pm);
    renderList("routine-weekly", plan.weekly);
    renderList("routine-avoid", plan.avoid);
    renderList("routine-notes", plan.notes);
    renderList("routine-timeline", plan.timeline ? [plan.timeline] : []);
    const saveCard = qs("save-progress-card");
    if (saveCard) saveCard.style.display = "block";
    try {
      const savedName = qs("save-name");
      const savedEmail = qs("save-email");
      if (savedName && !savedName.value) savedName.value = String(window.localStorage.getItem("dermiq_save_name") || "");
      if (savedEmail && !savedEmail.value) savedEmail.value = String(window.localStorage.getItem("dermiq_save_email") || "");
    } catch {}
    const savedMsg = qs("save-progress-msg");
    if (savedMsg) savedMsg.style.display = "none";

    await logTrackerEvent("routine_generated_ui", { product_ids: cartIds.slice(0, 30), scan_id: scanId || "" });
    document.dispatchEvent(
      new CustomEvent("dermiq:routine-ready", {
        detail: {
          scan_id: scanId || "",
          top_label: String(lastScan?.top_label || ""),
          selected_products: cartIds.slice(0, 30),
          preferences: prefs,
          plan,
          safety: String(j?.safety || ""),
        },
      }),
    );
    rw?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderMoneySummary(data) {
    const summary = data?.summary || {};
    const stats = qs("money-stats");
    if (stats) {
      const items = [
        ["Sessions", summary.sessions ?? 0],
        ["Analyses", summary.analyses ?? 0],
        ["Product clicks", summary.product_clicks ?? 0],
        ["Routine plans", summary.routine_plans ?? 0],
        ["Checkout starts", summary.checkout_starts ?? 0],
        ["CTR", `${Number(summary.click_through_rate || 0).toFixed(1)}%`],
      ];
      stats.innerHTML = items
        .map(
          ([label, value]) =>
            `<div class="money-stat"><div class="money-stat-k">${String(label)}</div><div class="money-stat-v">${String(value)}</div></div>`,
        )
        .join("");
    }

    renderMoneyList("money-categories", data?.top_categories, (row) => {
      const cat = labelToTitle(row?.category || "unknown");
      return `<div class="money-row"><span>${cat}</span><small>${Number(row?.count || 0)} views</small></div>`;
    });
    renderMoneyList("money-stores", data?.top_stores, (row) => {
      return `<div class="money-row"><span>${String(row?.store || "Unknown")}</span><small>${Number(row?.count || 0)} clicks</small></div>`;
    });
    renderMoneyList("money-products", data?.top_products, (row) => {
      const stores = row?.stores && typeof row.stores === "object" ? Object.entries(row.stores).slice(0, 2).map(([name, count]) => `${name} ${count}`).join(" · ") : "";
      return `<div class="money-row"><span>${labelToTitle(row?.product_id || "product")}</span><small>${Number(row?.clicks || 0)} clicks${stores ? ` · ${stores}` : ""}</small></div>`;
    });
    renderMoneyList("money-conditions", data?.top_conditions, (row) => {
      return `<div class="money-row"><span>${labelToTitle(row?.label || "unknown")}</span><small>${Number(row?.count || 0)} scans</small></div>`;
    });

    const banner = qs("money-banner");
    if (banner) {
      const scope = String(data?.scope || "session");
      banner.textContent =
        scope === "global"
          ? `Owner view unlocked · last ${Number(data?.days || 30)} days · commissions still finalize in each affiliate dashboard.`
          : "Showing your current session by default. Add your owner analytics key to view full-site revenue signals.";
    }
  }

  async function refreshMoneyDashboard() {
    const sid = await ensureSession();
    if (!sid) return;
    const adminKey = String(qs("money-admin-key")?.value || loadAnalyticsKey()).trim();
    const params = new URLSearchParams({ days: "30" });
    const headers = {};
    if (adminKey) {
      headers["X-Analytics-Key"] = adminKey;
      saveAnalyticsKey(adminKey);
    } else {
      params.set("session_id", sid);
    }
    const r = await fetch(`/analytics/summary?${params.toString()}`, { method: "GET", headers });
    if (!r.ok) {
      if (r.status === 403 && adminKey) {
        saveAnalyticsKey("");
        throw new Error("Owner analytics key is invalid.");
      }
      throw new Error("Could not load money dashboard.");
    }
    const j = await r.json().catch(() => null);
    renderMoneySummary(j || {});
  }

  async function saveProgressIntent() {
    const name = String(qs("save-name")?.value || "").trim();
    const email = String(qs("save-email")?.value || "").trim();
    if (!email) return alert("Add your email to save progress.");
    try {
      window.localStorage.setItem("dermiq_save_name", name);
      window.localStorage.setItem("dermiq_save_email", email);
    } catch {}
    await logTrackerEvent("save_progress_interest", {
      scan_id: scanId || "",
      top_label: String(lastScan?.top_label || ""),
      product_ids: cartIds.slice(0, 30),
      name,
      email,
    });
    const msg = qs("save-progress-msg");
    if (msg) msg.style.display = "block";
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
    const cart = qs("cart-wrap");
    if (cart) cart.style.display = "none";
    const routine = qs("routine-wrap");
    if (routine) routine.style.display = "none";
    const saveCard = qs("save-progress-card");
    if (saveCard) saveCard.style.display = "none";
    const fb = qs("feedback-wrap");
    if (fb) fb.style.display = "none";
    setCameraGuidance("Photo selected. Analyse now or retake with the live camera guide.");
  }

  async function startCamera() {
    if (!navigator.mediaDevices?.getUserMedia) {
      alert("Camera is not supported in this browser.");
      return;
    }
    cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
    const video = qs("camera-video");
    const stage = qs("camera-stage");
    const empty = qs("camera-empty");
    if (video) {
      video.srcObject = cameraStream;
      await video.play().catch(() => {});
    }
    if (stage) {
      stage.classList.add("active");
      stage.classList.remove("captured");
    }
    if (empty) empty.style.display = "none";
    setCameraGuidance("Live camera is running. Center one skin zone and move closer until it fills most of the frame.");
  }

  function stopCamera() {
    if (cameraStream) {
      cameraStream.getTracks().forEach((track) => track.stop());
      cameraStream = null;
    }
  }

  async function compareCapture(blob) {
    if (!blob || !lastCapturedBlob) return;
    try {
      const fd = new FormData();
      fd.append("current_file", blob, "current.jpg");
      fd.append("baseline_file", lastCapturedBlob, "baseline.jpg");
      const r = await fetch("/capture/compare", { method: "POST", body: fd });
      if (!r.ok) return;
      const j = await r.json().catch(() => null);
      const box = qs("compare-box");
      const copy = qs("compare-copy");
      if (box && copy) {
        copy.textContent = String(j?.comparison?.summary || "Comparison ready.");
        box.style.display = "block";
      }
    } catch {}
  }

  async function captureFromCamera() {
    const video = qs("camera-video");
    const canvas = qs("camera-canvas");
    const stage = qs("camera-stage");
    if (!(video instanceof HTMLVideoElement) || !(canvas instanceof HTMLCanvasElement) || !video.videoWidth) {
      alert("Start camera first.");
      return;
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
    if (!blob) return;
    currentFile = new File([blob], `camera-capture-${Date.now()}.jpg`, { type: "image/jpeg" });
    if (stage) {
      stage.classList.remove("active");
      stage.classList.add("captured");
    }
    const btn = qs("scan-btn");
    if (btn) btn.style.display = "inline-flex";
    setCameraGuidance("Frame captured. Analyse now or retake if you want a steadier, closer crop.");
    await compareCapture(blob);
    lastCapturedBlob = blob;
  }

  function resetCameraCapture() {
    currentFile = null;
    const stage = qs("camera-stage");
    const empty = qs("camera-empty");
    if (stage) stage.classList.remove("captured");
    if (!cameraStream && empty) empty.style.display = "block";
    const btn = qs("scan-btn");
    if (btn) btn.style.display = "none";
    const wrap = qs("preview-wrap");
    if (wrap) wrap.style.display = "none";
    setCameraGuidance("Tip: keep one skin area centered and fill most of the frame.");
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
        `<div style="font-size:.76rem;margin-top:10px;color:rgba(255,184,48,.7)">Keep your shortlist and routine ready, then come back for the next scan window.</div>` +
        `</div>`;
    }
    const rm = qs("result-main");
    const gc = qs("guidance-card");
    const pw = qs("products-wrap");
    if (rm) rm.style.display = "none";
    if (gc) gc.style.display = "none";
    if (pw) pw.style.display = "none";
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
      const mode = String(d?.confidence_mode || "uncertain");
      sevEl.textContent = mode;
      sevEl.className = `sev-pill ${mode === "confident" ? "sp-mild" : mode === "watch" ? "sp-mod" : "sp-sev"}`;
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
    const reasoningCard = qs("reasoning-card");
    const reasoningSummary = qs("reasoning-summary");
    const reasoningFactors = qs("reasoning-factors");
    if (reasoningCard) reasoningCard.style.display = "none";

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

    if (reasoningCard && reasoningSummary && reasoningFactors) {
      const reasoning = d?.reasoning || {};
      const factors = Array.isArray(reasoning?.supporting_factors) ? reasoning.supporting_factors : [];
      reasoningSummary.textContent = String(reasoning?.what_changed || "DermIQ combines the image with your current context and saved journey.");
      reasoningFactors.textContent = factors.join(" • ");
      reasoningCard.style.display = "block";
    }

    // Products
    matchedProducts = String(d?.top_label || "") === "uncertain" ? [] : (Array.isArray(d?.products) ? d.products : []);
    const prods = [];
    const prodWrap = qs("products-wrap");
    const grid = qs("prods-grid");
    const prodTitle = qs("prod-title");
    const prodNote = qs("products-note");
    const tierTagEl = qs("prod-tier-tag");
    if (tierTagEl) {
      tierTagEl.textContent = "";
      tierTagEl.style.display = "none";
    }
    if (prodTitle) prodTitle.textContent = "Smart product hub";
    if (grid) grid.innerHTML = "";
    if (prodWrap) prodWrap.style.display = "none";
    if (String(d?.top_label || "") === "uncertain") {
      if (prodWrap) prodWrap.style.display = "none";
      if (grid) grid.innerHTML = "";
    }
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
            const href = outHref(url, label, String(p?.id || ""));
            return `<a href="${href}" target="_blank" rel="noreferrer noopener sponsored" class="prod-buy">Buy on ${label} →</a>`;
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

    if (d?.capture_guidance?.tips?.length) {
      setCameraGuidance(String(d.capture_guidance.tips[0]));
    }

    const results = qs("results");
    if (results) results.style.display = "block";

    const fb = qs("feedback-wrap");
    if (fb) fb.style.display = "block";
    const thanks = document.querySelector(".fb-thanks");
    if (thanks) thanks.style.display = "none";
    document.querySelectorAll(".fb-btn").forEach((b) => (b.disabled = false));

    if (String(d?.top_label || "") !== "uncertain") {
      loadExplorer(exploreCategory).catch(() => {});
    } else {
      const prodWrap = qs("products-wrap");
      const cartWrap = qs("cart-wrap");
      const routineWrap = qs("routine-wrap");
      if (prodWrap) prodWrap.style.display = "none";
      if (cartWrap) cartWrap.style.display = "none";
      if (routineWrap) routineWrap.style.display = "none";
    }

    results?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function doScan() {
    if (!currentFile) return;
    startAnim();
    const fd = new FormData();
    fd.append("file", currentFile);
    const context = clinicalContext();
    fd.append("body_zone", String(context.body_zone || ""));
    fd.append("duration_days", String(context.duration_days || 0));
    fd.append("severity", String(context.severity || 0));
    fd.append("symptoms", (context.symptoms || []).join(","));
    fd.append("triggers", (context.triggers || []).join(","));
    try {
      const sid = await ensureSession();
      const headers = {};
      if (sid) headers["X-Session-Id"] = sid;
      const r = await fetch("/capture/analyze", { method: "POST", body: fd, headers });
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
        confidence_mode: String(d?.confidence_mode || ""),
        reasoning: d?.reasoning || null,
        capture_guidance: d?.capture_guidance || null,
      };
      showResults(d);
      document.dispatchEvent(new CustomEvent("dermiq:scan-result", { detail: { ...lastScan, usage: d?.usage || null } }));
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
          session_id: sessionId || "",
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

  // Explorer + cart init (minimal: hidden until after first scan)
  loadCart();
  applyCartPrefs(cartPrefs);
  restoreCartFromServer().catch(() => {});
  const catBox = qs("hub-cats");
  catBox?.querySelectorAll(".chip").forEach((b) =>
    b.addEventListener("click", () => {
      const cat = String(b.getAttribute("data-cat") || "").trim();
      if (!cat) return;
      exploreCategory = cat;
      catBox.querySelectorAll(".chip").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      loadExplorer(cat).catch(() => {});
    }),
  );

  qs("btn-generate-plan")?.addEventListener("click", () => {
    generateRoutinePlan().catch(() => alert("Could not generate routine. Please try again."));
  });
  qs("btn-clear-cart")?.addEventListener("click", () => {
    cartIds = [];
    if (qs("pref-store")) qs("pref-store").value = "";
    if (qs("pref-note")) qs("pref-note").value = "";
    cartPrefs = { preferred_store: "", note: "" };
    saveCart();
    renderCart([]);
    logCartUpdate().catch(() => {});
    const rw = qs("routine-wrap");
    if (rw) rw.style.display = "none";
  });
  qs("pref-store")?.addEventListener("change", () => {
    logCartUpdate().catch(() => {});
  });
  qs("pref-note")?.addEventListener("change", () => {
    logCartUpdate().catch(() => {});
  });
  qs("btn-save-progress")?.addEventListener("click", () => {
    saveProgressIntent().catch(() => alert("Could not save your progress right now."));
  });
  qs("btn-camera-start")?.addEventListener("click", () => {
    startCamera().catch(() => alert("Could not start camera."));
  });
  qs("btn-camera-capture")?.addEventListener("click", () => {
    captureFromCamera().catch(() => alert("Could not capture from camera."));
  });
  qs("btn-camera-reset")?.addEventListener("click", () => {
    resetCameraCapture();
  });
  qs("symptom-chips")
    ?.querySelectorAll("[data-symptom]")
    .forEach((btn) =>
      btn.addEventListener("click", () => {
        const symptom = String(btn.getAttribute("data-symptom") || "").trim();
        if (!symptom) return;
        if (selectedSymptoms.has(symptom)) {
          selectedSymptoms.delete(symptom);
          btn.classList.remove("on");
        } else {
          selectedSymptoms.add(symptom);
          btn.classList.add("on");
        }
      }),
    );
  try {
    const savedName = String(window.localStorage.getItem("dermiq_save_name") || "");
    const savedEmail = String(window.localStorage.getItem("dermiq_save_email") || "");
    if (qs("save-name")) qs("save-name").value = savedName;
    if (qs("save-email")) qs("save-email").value = savedEmail;
  } catch {}
  window.DermIQ = {
    ensureSession,
    getSessionId: () => sessionId,
    getLastScan: () => (lastScan ? { ...lastScan } : null),
    getScanId: () => scanId,
    getCartState: () => {
      loadCartPrefs();
      return {
        product_ids: cartIds.slice(0, 30),
        preferences: { ...cartPrefs },
      };
    },
  };
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
  window.addEventListener("beforeunload", () => {
    stopCamera();
  });
})();
