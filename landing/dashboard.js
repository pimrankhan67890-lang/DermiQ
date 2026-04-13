(() => {
  function qs(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function titleize(value) {
    return String(value || "")
      .trim()
      .split("_")
      .filter(Boolean)
      .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
      .join(" ");
  }

  function fmtDate(ts) {
    const n = Number(ts);
    if (!Number.isFinite(n) || !n) return "—";
    return new Date(n * 1000).toLocaleDateString();
  }

  let supabaseClient = null;
  let authConfig = null;

  async function ensureSession() {
    let sid = "";
    try {
      sid = String(window.localStorage.getItem("dermiq_session_id") || "").trim();
    } catch {}
    if (sid) return sid;
    try {
      const r = await fetch("/tracker/session", { method: "POST" });
      const j = await r.json().catch(() => null);
      sid = String(j?.session_id || "").trim();
      if (sid) window.localStorage.setItem("dermiq_session_id", sid);
    } catch {}
    return sid;
  }

  async function api(path, options) {
    const opts = options ? { ...options } : {};
    const headers = { ...(opts.headers || {}) };
    const sid = await ensureSession();
    if (sid) headers["X-Session-Id"] = sid;
    opts.headers = headers;
    return fetch(path, opts);
  }

  function renderList(id, arr) {
    const el = qs(id);
    if (!el) return;
    const list = Array.isArray(arr) ? arr : [];
    el.innerHTML =
      list.map((item) => `<div class="routine-li">• ${escapeHtml(item)}</div>`).join("") ||
      `<div class="empty">No items saved yet.</div>`;
  }

  function setCaseSignals(caseState) {
    const confidence = String(caseState?.confidence_mode || "uncertain");
    const trend = String(caseState?.response_trend || "unknown");
    const severity = Number(caseState?.symptom_severity || 0);
    const irritants = Array.isArray(caseState?.irritation_flags) ? caseState.irritation_flags : [];

    if (qs("case-focus")) qs("case-focus").textContent = titleize(caseState?.focus_condition || "unknown");
    if (qs("case-confidence")) qs("case-confidence").textContent = titleize(confidence);
    if (qs("case-trend")) qs("case-trend").textContent = titleize(trend);
    if (qs("case-severity")) qs("case-severity").textContent = `${severity.toFixed(1)}/10`;

    if (qs("case-focus-copy")) {
      qs("case-focus-copy").textContent = caseState?.last_scan_at
        ? `Latest saved scan on ${fmtDate(caseState.last_scan_at)} sets this current focus.`
        : "Run and save a scan to give DermIQ a current focus condition.";
    }
    if (qs("case-confidence-copy")) {
      const labels = {
        confident: "DermIQ sees a clearer pattern right now.",
        watch: "DermIQ sees a possible pattern, so it keeps the protocol conservative.",
        uncertain: "DermIQ wants a clearer photo or more follow-up data before acting strongly.",
        escalate: "DermIQ thinks the safer next step is clinician support.",
      };
      qs("case-confidence-copy").textContent = labels[confidence] || labels.uncertain;
    }
    if (qs("case-trend-copy")) {
      qs("case-trend-copy").textContent = irritants.length
        ? `Recent irritation flags: ${irritants.slice(0, 2).join(", ")}.`
        : "Weekly check-ins turn this into improving, steady, or worsening.";
    }
    if (qs("case-severity-copy")) {
      qs("case-severity-copy").textContent =
        severity >= 7
          ? "High severity should keep the protocol simple and may justify a consult."
          : "Keep this updated weekly so the protocol adapts safely.";
    }
  }

  function renderJourney(data) {
    const stats = data?.stats || {};
    const scans = Array.isArray(data?.recent_scans) ? data.recent_scans : [];
    const products = Array.isArray(data?.products) ? data.products : [];
    const routine = data?.routine?.plan || {};
    const escalation = data?.escalation || {};
    const caseState = data?.case_state || {};
    const profile = data?.profile || {};

    if (qs("journey-user")) qs("journey-user").textContent = String(profile.full_name || profile.email || "").trim();
    if (qs("journey-copy")) {
      qs("journey-copy").textContent = routine?.headline
        ? `${routine.headline} Track whether it helps, what irritates, and when it is time to escalate.`
        : "DermIQ keeps routines, products, and follow-ups together so you can spot improvement and know when to seek care.";
    }
    if (qs("routine-headline-copy")) {
      qs("routine-headline-copy").textContent = String(routine?.today_focus || "Generate and save a routine from the landing page to see your current plan here.");
    }

    if (qs("journey-stat-scans")) qs("journey-stat-scans").textContent = String(stats.total_scans || 0);
    if (qs("journey-stat-products")) qs("journey-stat-products").textContent = String(stats.tracked_products || 0);
    if (qs("journey-stat-active")) qs("journey-stat-active").textContent = String(stats.active_products || 0);
    if (qs("journey-stat-followups")) qs("journey-stat-followups").textContent = String(stats.follow_ups || 0);

    setCaseSignals(caseState);

    renderList("routine-am", routine.am);
    renderList("routine-pm", routine.pm);
    renderList("routine-weekly", [...(Array.isArray(routine.weekly) ? routine.weekly : []), routine.when_to_rescan].filter(Boolean));
    renderList("routine-avoid", [...(Array.isArray(routine.avoid) ? routine.avoid : []), routine.when_to_consult].filter(Boolean));

    const level = String(escalation.level || "none");
    const levelEl = qs("journey-escalation-level");
    if (levelEl) {
      levelEl.textContent = titleize(level);
      levelEl.className = `status-chip${level === "urgent" ? " urgent" : level === "caution" ? " caution" : ""}`;
    }
    if (qs("journey-escalation-reason")) {
      qs("journey-escalation-reason").textContent =
        [escalation.reason, escalation.next_step].filter(Boolean).join(" ") || "No warning signs in your saved journey yet.";
    }
    const ctaWrap = qs("journey-escalation-cta-wrap");
    const cta = qs("journey-escalation-cta");
    if (ctaWrap) ctaWrap.style.display = level !== "none" ? "flex" : "none";
    if (cta) {
      cta.textContent = String(escalation.consult_label || "Consult a clinician");
      cta.href = String(escalation.consult_url || "/");
    }

    const productsWrap = qs("journey-products");
    if (productsWrap) {
      productsWrap.innerHTML =
        products
          .map((item) => {
            const status = String(item?.status || "planned");
            const productId = escapeHtml(item?.product_id || "");
            const buttons = ["planned", "active", "helped", "neutral", "irritated", "inconsistent", "stopped"]
              .map(
                (choice) =>
                  `<button class="status-btn${choice === status ? " on" : ""}" type="button" data-product-status="${choice}" data-product-id="${productId}">${titleize(choice)}</button>`,
              )
              .join("");
            return `<div class="row">
              <div class="row-top">
                <div>
                  <div class="card-title" style="font-size:1rem">${escapeHtml(item?.name || item?.product_id || "Product")}</div>
                  <div class="item-sub">${escapeHtml(item?.category || "General")} · ${escapeHtml(item?.store_preference || "Any store")} · Updated ${fmtDate(item?.updated_at)}</div>
                </div>
                <span class="status-chip">${escapeHtml(titleize(status))}</span>
              </div>
              <div class="copy">${escapeHtml(item?.notes || "No extra notes yet.")}</div>
              <div class="product-statuses">${buttons}</div>
            </div>`;
          })
          .join("") || `<div class="empty">No tracked products yet. Save a routine from the landing page to start your journey.</div>`;
    }

    const scansWrap = qs("journey-scans");
    if (scansWrap) {
      scansWrap.innerHTML =
        scans
          .map(
            (scan) => `<div class="item">
          <div class="item-top">
            <div class="card-title" style="font-size:1rem">${escapeHtml(titleize(scan?.top_label || "Unknown"))}</div>
            <span class="status-chip">${escapeHtml(titleize(scan?.confidence_level || "uncertain"))}</span>
          </div>
          <div class="item-sub">${fmtDate(scan?.created_at)} · ${escapeHtml(scan?.backend || "model")} · ${Math.round(Number(scan?.top_prob || 0) * 100)}% confidence</div>
        </div>`,
          )
          .join("") || `<div class="empty">No saved scans yet. Go back to the landing page and analyse a photo.</div>`;
    }
  }

  async function refreshJourney() {
    const r = await api("/journey/summary");
    if (r.status === 401) {
      window.location.href = "/";
      return;
    }
    if (!r.ok) throw new Error("Could not load journey.");
    const j = await r.json().catch(() => null);
    if (j) renderJourney(j);
  }

  async function changeProductStatus(productId, status) {
    const r = await api("/journey/product-status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product_id: productId, status }),
    });
    if (!r.ok) return;
    await refreshJourney();
  }

  async function saveFollowUp() {
    const payload = {
      severity: Number(qs("followup-severity")?.value || 0),
      notes: String(qs("followup-notes")?.value || "").trim(),
      flags: {
        fever: !!qs("flag-fever")?.checked,
        spreading_fast: !!qs("flag-spreading")?.checked,
        bleeding: !!qs("flag-bleeding")?.checked,
        eye_involvement: !!qs("flag-eye")?.checked,
        severe_pain: !!qs("flag-pain")?.checked,
      },
    };
    const r = await api("/journey/follow-up", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      alert("Could not save your follow-up right now.");
      return;
    }
    if (qs("followup-msg")) qs("followup-msg").style.display = "block";
    await refreshJourney();
  }

  async function deleteJourney() {
    if (!window.confirm("Delete your DermIQ journey data? This cannot be undone.")) return;
    const r = await api("/journey/delete", { method: "POST" });
    if (!r.ok) {
      alert("Could not delete your data right now.");
      return;
    }
    if (supabaseClient) await supabaseClient.auth.signOut();
    window.location.href = "/";
  }

  async function initAuth() {
    const res = await fetch("/auth/config");
    authConfig = await res.json().catch(() => ({}));
    if (!authConfig?.enabled || !window.supabase?.createClient) {
      window.location.href = "/";
      return;
    }
    supabaseClient = window.supabase.createClient(authConfig.url, authConfig.anon_key, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    });
    const { data } = await supabaseClient.auth.getSession();
    if (!data?.session?.access_token) {
      window.location.href = "/";
      return;
    }
    const linkResp = await api("/auth/session/exchange", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: String(data.session.access_token || "") }),
    });
    if (!linkResp.ok) {
      window.location.href = "/";
      return;
    }
    await refreshJourney();
  }

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const status = String(target.getAttribute("data-product-status") || "").trim();
    const productId = String(target.getAttribute("data-product-id") || "").trim();
    if (status && productId) changeProductStatus(productId, status).catch(() => {});
  });

  qs("btn-followup-save")?.addEventListener("click", () => saveFollowUp().catch(() => {}));
  qs("btn-journey-delete")?.addEventListener("click", () => deleteJourney().catch(() => {}));
  qs("journey-logout")?.addEventListener("click", async () => {
    if (supabaseClient) await supabaseClient.auth.signOut();
    window.location.href = "/";
  });

  initAuth().catch(() => {
    window.location.href = "/";
  });
})();
