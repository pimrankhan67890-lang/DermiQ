(() => {
  function qs(id) {
    return document.getElementById(id);
  }

  let authConfig = null;
  let supabaseClient = null;
  let currentUser = null;
  let pendingRoutine = null;
  let authIntent = "signin";

  async function ensureSession() {
    return (await window.DermIQ?.ensureSession?.()) || "";
  }

  async function api(path, options) {
    const opts = options ? { ...options } : {};
    const headers = { ...(opts.headers || {}) };
    const sid = await ensureSession();
    if (sid) headers["X-Session-Id"] = sid;
    opts.headers = headers;
    return fetch(path, opts);
  }

  function show(el, on, display = "block") {
    if (!el) return;
    el.style.display = on ? display : "none";
  }

  function setAuthIntent(intent) {
    authIntent = intent === "signup" ? "signup" : "signin";
    if (qs("auth-mode-label")) qs("auth-mode-label").textContent = authIntent === "signup" ? "Sign up free" : "Sign in";
    if (qs("auth-title")) qs("auth-title").textContent = authIntent === "signup" ? "Start your DermIQ journey" : "Welcome back to DermIQ";
    if (qs("auth-copy")) {
      qs("auth-copy").textContent =
        authIntent === "signup"
          ? "Create your free account to keep scan history, product tracking, and weekly follow-ups across devices."
          : "Sign in to continue your skin journey, product tracking, and safer next steps.";
    }
  }

  function openAuth(intent) {
    setAuthIntent(intent);
    const modal = qs("auth-modal");
    if (!modal) return;
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
  }

  function closeAuth() {
    const modal = qs("auth-modal");
    if (!modal) return;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
  }

  function setNavState() {
    const signedIn = !!currentUser;
    show(qs("btn-signin"), !signedIn, "inline-flex");
    show(qs("btn-signup"), !signedIn, "inline-flex");
    show(qs("journey-link"), signedIn, "inline-flex");
    show(qs("btn-logout"), signedIn, "inline-flex");
    show(qs("user-name"), signedIn, "inline-flex");
    if (qs("user-name")) {
      qs("user-name").textContent = signedIn
        ? String(currentUser?.full_name || currentUser?.email || "Account").trim()
        : "";
    }
  }

  async function persistPendingState() {
    if (!currentUser) return;
    const cartState = window.DermIQ?.getCartState?.() || { product_ids: [], preferences: {} };
    const lastScan = window.DermIQ?.getLastScan?.() || {};
    const scanId = String(window.DermIQ?.getScanId?.() || pendingRoutine?.scan_id || "");

    const selectedProducts = Array.isArray(pendingRoutine?.selected_products)
      ? pendingRoutine.selected_products
      : Array.isArray(cartState.product_ids)
        ? cartState.product_ids
        : [];

    if (selectedProducts.length) {
      await api("/journey/product-track", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scan_id: scanId,
          selected_products: selectedProducts,
          preferences: pendingRoutine?.preferences || cartState.preferences || {},
          status: "planned",
        }),
      });
    }

    if (pendingRoutine?.plan) {
      await api("/journey/routine/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scan_id: scanId,
          top_label: pendingRoutine?.top_label || String(lastScan?.top_label || ""),
          plan: pendingRoutine.plan,
        }),
      });
    }
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
    setNavState();
    await persistPendingState().catch(() => {});
    closeAuth();
    if (qs("journey-prompt")) {
      qs("journey-prompt").innerHTML =
        `<div class="products-title">Saved to your DermIQ journey</div>` +
        `<div class="products-note">Your current scan, selected products, and routine are now attached to your account.</div>` +
        `<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:14px"><a class="btn-ghost" href="/journey">Open My Journey</a></div>`;
      qs("journey-prompt").style.display = "block";
    }
    window.setTimeout(() => {
      window.location.href = "/journey";
    }, 350);
  }

  async function initAuth() {
    try {
      const r = await fetch("/auth/config");
      authConfig = (await r.json().catch(() => null)) || { enabled: false };
    } catch {
      authConfig = { enabled: false };
    }

    if (!authConfig?.enabled || !window.supabase?.createClient) {
      setNavState();
      return;
    }

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
        setNavState();
      }
    });
    setNavState();
  }

  async function startGoogleLogin() {
    if (!supabaseClient) {
      alert("Google sign-in is not configured yet.");
      return;
    }
    await supabaseClient.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/`,
      },
    });
  }

  async function logout() {
    if (supabaseClient) await supabaseClient.auth.signOut();
    currentUser = null;
    setNavState();
  }

  document.addEventListener("dermiq:routine-ready", (event) => {
    pendingRoutine = event.detail || null;
    if (!currentUser && authConfig?.enabled && qs("journey-prompt")) {
      qs("journey-prompt").style.display = "block";
    }
  });

  document.addEventListener("dermiq:scan-result", () => {
    if (!currentUser && authConfig?.enabled && qs("journey-prompt")) {
      qs("journey-prompt").style.display = "block";
    }
  });

  qs("btn-signin")?.addEventListener("click", () => openAuth("signin"));
  qs("btn-signup")?.addEventListener("click", () => openAuth("signup"));
  qs("btn-google-auth-inline")?.addEventListener("click", () => openAuth("signup"));
  qs("auth-google")?.addEventListener("click", () => startGoogleLogin().catch(() => {}));
  qs("auth-close")?.addEventListener("click", closeAuth);
  qs("auth-dismiss")?.addEventListener("click", closeAuth);
  qs("btn-logout")?.addEventListener("click", () => logout().catch(() => {}));

  initAuth().catch(() => {
    setNavState();
  });
})();
