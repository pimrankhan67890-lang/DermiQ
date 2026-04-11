(() => {
  function qs(id) {
    return document.getElementById(id);
  }

  function titleize(value) {
    return String(value || "")
      .trim()
      .split("_")
      .filter(Boolean)
      .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
      .join(" ");
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function fmtDate(ts) {
    const n = Number(ts);
    if (!Number.isFinite(n) || !n) return "—";
    return new Date(n * 1000).toLocaleDateString();
  }

  let authConfig = null;
  let supabaseClient = null;
  let currentUser = null;
  let pendingRoutine = null;

  async function api(path, options) {
    const opts = options ? { ...options } : {};
    const headers = { ...(opts.headers || {}) };
    try {
      const sid = await window.DermIQ?.ensureSession?.();
      if (sid) headers["X-Session-Id"] = sid;
    } catch {}
    opts.headers = headers;
    return fetch(path, opts);
  }

  function show(el, on) {
    if (!el) return;
    if (!on) {
      el.style.display = "none";
      return;
    }
    if (
      el.classList.contains("auth-pill") ||
      el.classList.contains("auth-link") ||
      el.tagName === "BUTTON"
    ) {
      el.style.display = "inline-flex";
      return;
    }
    el.style.display = "block";
  }

  function setAuthUi() {
    const authPill = qs("auth-pill");
    const signInTop = qs("btn-google-auth");
    const signInInline = qs("btn-google-auth-inline");
    const logoutBtn = qs("btn-logout");
    const journeyLink = qs("journey-link");
    const journeyWrap = qs("journey");
    const prompt = qs("journey-prompt");

    const enabled = !!authConfig?.enabled;
    const signedIn = !!currentUser;

    if (authPill) authPill.style.display = "inline-flex";
    if (authPill) authPill.textContent = signedIn ? `Signed in${currentUser?.full_name ? ` as ${currentUser.full_name}` : ""}` : "Anonymous mode";
    show(signInTop, enabled && !signedIn);
    show(signInInline, enabled && !signedIn);
    show(logoutBtn, enabled && signedIn);
    show(journeyLink, signedIn);
    show(journeyWrap, signedIn);
    if (!signedIn) show(prompt, !!pendingRoutine && enabled);
  }

  async function exchangeSession(session) {
    const token = String(session?.access_token || "").trim();
    if (!token) return;
    const r = await api("/auth/session/exchange", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: token }),
    });
    if (!r.ok) throw new Error("Could not link auth session.");
    const j = await r.json().catch(() => null);
    currentUser = j?.user || null;
    setAuthUi();
    if (j?.journey) renderJourney(j.journey);
    if (pendingRoutine) {
      await persistJourneyState();
    }
  }

  async function initAuth() {
    try {
      const r = await fetch("/auth/config");
      authConfig = (await r.json().catch(() => null)) || { enabled: false };
    } catch {
      authConfig = { enabled: false };
    }
    setAuthUi();

    if (!authConfig?.enabled || !window.supabase?.createClient) return;
    supabaseClient = window.supabase.createClient(authConfig.url, authConfig.anon_key, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    });

    const { data } = await supabaseClient.auth.getSession();
    if (data?.session?.access_token) {
      await exchangeSession(data.session).catch(() => {});
    }
    supabaseClient.auth.onAuthStateChange((_event, session) => {
      if (session?.access_token) {
        exchangeSession(session).catch(() => {});
      } else {
        currentUser = null;
        setAuthUi();
      }
    });
  }

  async function startGoogleLogin() {
    if (!supabaseClient) {
      alert("Google sign-in is not configured yet.");
      return;
    }
    await supabaseClient.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}${window.location.pathname}${window.location.hash || "#journey"}`,
      },
    });
  }

  async function logoutJourney() {
    if (supabaseClient) {
      await supabaseClient.auth.signOut();
    }
    currentUser = null;
    setAuthUi();
  }

  async function refreshJourney() {
    if (!currentUser) return;
    const r = await api("/journey/summary");
    if (!r.ok) return;
    const j = await r.json().catch(() => null);
    if (j) renderJourney(j);
  }

  function renderJourney(data) {
    const stats = data?.stats || {};
    const products = Array.isArray(data?.products) ? data.products : [];
    const scans = Array.isArray(data?.recent_scans) ? data.recent_scans : [];
    const escalation = data?.escalation || {};
    const routine = data?.routine?.plan || {};

    const scanStat = qs("journey-stat-scans");
    const prodStat = qs("journey-stat-products");
    const activeStat = qs("journey-stat-active");
    const followStat = qs("journey-stat-followups");
    if (scanStat) scanStat.textContent = String(stats.total_scans || 0);
    if (prodStat) prodStat.textContent = String(stats.tracked_products || 0);
    if (activeStat) activeStat.textContent = String(stats.active_products || 0);
    if (followStat) followStat.textContent = String(stats.follow_ups || 0);

    const copy = qs("journey-copy");
    if (copy) {
      copy.textContent = routine?.headline
        ? `${routine.headline} Keep tracking weekly so DermIQ can look for improvement and safer next steps.`
        : "Track progress, routine adherence, and when it’s time to seek care.";
    }

    const escLevel = String(escalation.level || "none");
    const escReason = String(escalation.reason || "No warning signs in your saved journey yet.");
    const escNext = String(escalation.next_step || "");
    const escPill = qs("journey-escalation-level");
    const escText = qs("journey-escalation-reason");
    if (escPill) {
      escPill.textContent = escLevel;
      escPill.className = `status-chip${escLevel === "urgent" ? " urgent" : escLevel === "caution" ? " caution" : ""}`;
    }
    if (escText) escText.textContent = [escReason, escNext].filter(Boolean).join(" ");
    const escWrap = qs("journey-escalation-cta-wrap");
    const escCta = qs("journey-escalation-cta");
    const shouldConsult = escLevel !== "none";
    show(escWrap, shouldConsult);
    if (escCta) {
      escCta.textContent = String(escalation.consult_label || "Consult a clinician");
      escCta.href = String(escalation.consult_url || "#safety");
    }

    const productsWrap = qs("journey-products");
    if (productsWrap) {
      if (!products.length) {
        productsWrap.innerHTML = `<div class="journey-item"><div class="journey-copy">No tracked products yet. After you build a routine, DermIQ will save them here.</div></div>`;
      } else {
        productsWrap.innerHTML = products
          .map((item) => {
            const status = String(item?.status || "planned");
            const productId = escapeHtml(item?.product_id || "");
            const buttons = ["planned", "active", "helped", "irritated", "stopped"]
              .map((choice) => `<button class="status-btn${choice === status ? " on" : ""}" type="button" data-product-status="${choice}" data-product-id="${productId}">${titleize(choice)}</button>`)
              .join("");
            return `<div class="product-track-row">
              <div class="product-track-top">
                <div>
                  <div class="products-title" style="font-size:1rem">${escapeHtml(item?.name || item?.product_id || "Product")}</div>
                  <div class="journey-item-sub">${escapeHtml(item?.category || "General")} · ${escapeHtml(item?.store_preference || "Any store")} · Updated ${fmtDate(item?.updated_at)}</div>
                </div>
                <span class="status-chip">${escapeHtml(status)}</span>
              </div>
              <div class="journey-copy">${escapeHtml(item?.notes || "No extra notes yet.")}</div>
              <div class="product-statuses">${buttons}</div>
            </div>`;
          })
          .join("");
      }
    }

    const scansWrap = qs("journey-scans");
    if (scansWrap) {
      if (!scans.length) {
        scansWrap.innerHTML = `<div class="journey-item"><div class="journey-copy">Sign in and scan again to start your cross-device history.</div></div>`;
      } else {
        scansWrap.innerHTML = scans
          .map(
            (scan) => `<div class="journey-item">
              <div class="journey-item-top">
                <div class="products-title" style="font-size:1rem">${escapeHtml(titleize(scan?.top_label || "Unknown"))}</div>
                <span class="status-chip">${Math.round(Number(scan?.top_prob || 0) * 100)}% confidence</span>
              </div>
              <div class="journey-item-sub">${fmtDate(scan?.created_at)} · ${escapeHtml(scan?.backend || "model")}</div>
            </div>`,
          )
          .join("");
      }
    }

    show(qs("journey"), true);
  }

  async function persistJourneyState() {
    if (!currentUser || !pendingRoutine) return;
    await api("/journey/product-track", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scan_id: pendingRoutine.scan_id || window.DermIQ?.getScanId?.() || "",
        selected_products: Array.isArray(pendingRoutine.selected_products) ? pendingRoutine.selected_products : [],
        preferences: pendingRoutine.preferences || {},
        status: "planned",
      }),
    });
    await api("/journey/routine/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scan_id: pendingRoutine.scan_id || window.DermIQ?.getScanId?.() || "",
        top_label: pendingRoutine.top_label || window.DermIQ?.getLastScan?.()?.top_label || "",
        plan: pendingRoutine.plan || {},
      }),
    });
    show(qs("journey-prompt"), false);
    await refreshJourney();
  }

  async function saveFollowUp() {
    if (!currentUser) {
      alert("Sign in first to save weekly follow-ups.");
      return;
    }
    const severity = Number(qs("followup-severity")?.value || 0);
    const notes = String(qs("followup-notes")?.value || "").trim();
    const scan = window.DermIQ?.getLastScan?.() || {};
    const payload = {
      scan_id: String(scan?.scan_id || ""),
      severity,
      notes,
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
      alert("Could not save the follow-up right now.");
      return;
    }
    const msg = qs("followup-msg");
    if (msg) msg.style.display = "block";
    await refreshJourney();
  }

  async function changeProductStatus(productId, status) {
    if (!currentUser) return;
    const r = await api("/journey/product-status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product_id: productId, status }),
    });
    if (!r.ok) return;
    await refreshJourney();
  }

  async function deleteJourney() {
    if (!currentUser) return;
    if (!window.confirm("Delete your DermIQ journey data? This cannot be undone.")) return;
    const r = await api("/journey/delete", { method: "POST" });
    if (!r.ok) {
      alert("Could not delete data right now.");
      return;
    }
    await logoutJourney();
    alert("Your DermIQ journey data was deleted.");
  }

  document.addEventListener("dermiq:routine-ready", (event) => {
    pendingRoutine = event.detail || null;
    if (currentUser) {
      persistJourneyState().catch(() => {});
      return;
    }
    if (authConfig?.enabled) {
      show(qs("journey-prompt"), true);
    }
  });

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const status = String(target.getAttribute("data-product-status") || "").trim();
    const productId = String(target.getAttribute("data-product-id") || "").trim();
    if (status && productId) {
      changeProductStatus(productId, status).catch(() => {});
    }
  });

  qs("btn-google-auth")?.addEventListener("click", () => startGoogleLogin().catch(() => {}));
  qs("btn-google-auth-inline")?.addEventListener("click", () => startGoogleLogin().catch(() => {}));
  qs("btn-logout")?.addEventListener("click", () => logoutJourney().catch(() => {}));
  qs("btn-followup-save")?.addEventListener("click", () => saveFollowUp().catch(() => {}));
  qs("btn-journey-delete")?.addEventListener("click", () => deleteJourney().catch(() => {}));

  initAuth().catch(() => {});
})();
