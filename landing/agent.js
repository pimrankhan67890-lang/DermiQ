(() => {
  function qs(id) {
    return document.getElementById(id);
  }

  const state = {
    sessionId: "",
    cameraStream: null,
    currentBlob: null,
    baselineBlob: null,
    currentFile: null,
    selectedSymptoms: new Set(),
    answers: {
      concern: "",
      duration_days: 0,
      severity: 0,
      body_zone: "",
      triggers: [],
      symptoms: [],
    },
    intakeStep: 0,
    recognition: null,
    listening: false,
    voiceReplyOn: true,
    selectedVoice: null,
    report: null,
  };

  const intakeFlow = [
    {
      key: "concern",
      question: "Hello — I’m your DermIQ AI doctor companion. Tell me what is bothering you most right now, in your own words.",
      placeholder: "For example: red itchy patches on my cheeks, painful pimples on my chin, or flaking around my scalp.",
      normalize: (text) => String(text || "").trim(),
      summary: "summary-concern",
    },
    {
      key: "duration_days",
      question: "How long has this been there? You can answer with days, weeks, or months.",
      placeholder: "For example: 10 days, 2 weeks, or about 3 months.",
      normalize: (text) => parseDurationDays(text),
      summary: "summary-duration",
      format: (value) => (value ? `${value} day${value === 1 ? "" : "s"}` : "Not shared yet"),
    },
    {
      key: "severity",
      question: "On a scale from 0 to 10, how strong or uncomfortable does it feel today?",
      placeholder: "For example: 3, 5, or 8.",
      normalize: (text) => parseSeverity(text),
      summary: "summary-severity",
      format: (value) => (Number.isFinite(value) && value > 0 ? `${value}/10` : "Not shared yet"),
    },
    {
      key: "body_zone",
      question: "Which body zone should I focus on? For example cheek, forehead, nose, scalp, neck, or chest.",
      placeholder: "For example: left cheek or scalp line.",
      normalize: (text) => String(text || "").trim(),
      summary: "summary-zone",
    },
    {
      key: "triggers",
      question: "Do you notice any triggers such as heat, sweat, stress, spicy food, shaving, or a new product?",
      placeholder: "For example: heat, sweat, and a new sunscreen.",
      normalize: (text) =>
        String(text || "")
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean),
    },
  ];

  function scrollMessages() {
    const wrap = qs("chat-messages");
    if (!wrap) return;
    wrap.scrollTop = wrap.scrollHeight;
  }

  function addMessage(role, text) {
    const wrap = qs("chat-messages");
    if (!wrap) return;
    const div = document.createElement("div");
    div.className = `bubble ${role}`;
    const who = role === "ai" ? "DermIQ AI doctor" : "You";
    div.innerHTML = `<small>${who}</small>${escapeHtml(String(text || "")).replace(/\n/g, "<br>")}`;
    wrap.appendChild(div);
    scrollMessages();
    if (role === "ai") speak(text);
  }

  function setConsultStage(text) {
    const el = qs("consult-stage");
    if (el) el.textContent = text;
  }

  function syncStructuredInputs() {
    if (qs("intake-duration")) qs("intake-duration").value = state.answers.duration_days || "";
    if (qs("intake-severity")) qs("intake-severity").value = state.answers.severity || "0";
    if (qs("intake-zone")) qs("intake-zone").value = state.answers.body_zone || "";
    if (qs("intake-triggers")) qs("intake-triggers").value = (state.answers.triggers || []).join(", ");
    document.querySelectorAll(".symptom[data-symptom]").forEach((btn) => {
      const name = String(btn.getAttribute("data-symptom") || "");
      btn.classList.toggle("on", state.selectedSymptoms.has(name));
    });
  }

  function updateQuickSummary() {
    const stepConcern = String(state.answers.concern || "").trim() || "Not shared yet";
    const duration = Number(state.answers.duration_days || 0);
    const severity = Number(state.answers.severity || 0);
    const zone = String(state.answers.body_zone || "").trim() || "Not shared yet";
    if (qs("summary-concern")) qs("summary-concern").textContent = stepConcern;
    if (qs("summary-duration")) qs("summary-duration").textContent = duration ? `${duration} days` : "Not shared yet";
    if (qs("summary-severity")) qs("summary-severity").textContent = severity ? `${severity}/10` : "Not shared yet";
    if (qs("summary-zone")) qs("summary-zone").textContent = zone;
  }

  function activeStep() {
    return intakeFlow[Math.min(state.intakeStep, intakeFlow.length - 1)] || null;
  }

  function askNextQuestion() {
    const step = intakeFlow[state.intakeStep];
    if (!step) {
      setConsultStage("Ready to analyse");
      addMessage(
        "ai",
        state.currentBlob
          ? "I have enough context to analyse this safely. Press Analyse now, or keep speaking if you want to add more detail."
          : "I have enough context to analyse this safely. Now capture or upload one clear close-up photo, then press Analyse now.",
      );
      if (qs("agent-input")) qs("agent-input").placeholder = "Add any extra detail or press Analyse now.";
      return;
    }
    setConsultStage(`Intake ${state.intakeStep + 1}/${intakeFlow.length}`);
    if (qs("agent-input")) qs("agent-input").placeholder = step.placeholder;
    addMessage("ai", step.question);
  }

  function hydrateAnswersFromStructuredInputs() {
    const duration = parseDurationDays(qs("intake-duration")?.value || "0");
    const severity = parseSeverity(qs("intake-severity")?.value || "0");
    const zone = String(qs("intake-zone")?.value || "").trim();
    const triggers = String(qs("intake-triggers")?.value || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);

    state.answers.duration_days = duration;
    state.answers.severity = severity;
    state.answers.body_zone = zone;
    state.answers.triggers = triggers;
    state.answers.symptoms = Array.from(state.selectedSymptoms);
    updateQuickSummary();
  }

  async function ensureSession() {
    if (state.sessionId) return state.sessionId;
    try {
      const fromStorage = String(window.localStorage.getItem("dermiq_session_id") || "").trim();
      if (fromStorage) {
        state.sessionId = fromStorage;
        return state.sessionId;
      }
    } catch {}

    try {
      const r = await fetch("/tracker/session", { method: "POST" });
      if (!r.ok) return "";
      const j = await r.json().catch(() => null);
      state.sessionId = String(j?.session_id || "").trim();
      if (state.sessionId) {
        try {
          window.localStorage.setItem("dermiq_session_id", state.sessionId);
        } catch {}
      }
      return state.sessionId;
    } catch {
      return "";
    }
  }

  async function api(path, options) {
    const opts = options ? { ...options } : {};
    const headers = { ...(opts.headers || {}) };
    const sid = await ensureSession();
    if (sid) headers["X-Session-Id"] = sid;
    opts.headers = headers;
    return fetch(path, opts);
  }

  function setCaptureGuidance(text) {
    const el = qs("capture-guidance");
    if (el) el.textContent = text;
  }

  function setCaptureStatus(label, isTeal) {
    const el = qs("capture-status");
    if (!el) return;
    el.textContent = label;
    el.classList.toggle("teal", !!isTeal);
  }

  function setCompareStatus(text, isTeal) {
    const el = qs("compare-status");
    if (!el) return;
    el.textContent = text;
    el.classList.toggle("teal", !!isTeal);
  }

  async function startCamera() {
    if (!navigator.mediaDevices?.getUserMedia) {
      addMessage("ai", "This browser does not support camera access. You can still upload a photo and continue the consultation.");
      return;
    }
    try {
      state.cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      const video = qs("agent-video");
      if (video) {
        video.srcObject = state.cameraStream;
        video.play().catch(() => {});
      }
      if (qs("capture-empty")) qs("capture-empty").style.display = "none";
      if (qs("agent-snapshot")) qs("agent-snapshot").style.display = "none";
      setCaptureStatus("Camera live", true);
      setCaptureGuidance("Camera is live. Move closer until one skin zone fills most of the frame, then capture.");
      addMessage("ai", "Camera is ready. Hold the same skin area steady and capture one clear frame when you’re ready.");
    } catch {
      addMessage("ai", "I could not access your camera. You can still upload a close-up photo and continue safely.");
      setCaptureStatus("Camera blocked", false);
    }
  }

  function stopCamera() {
    if (state.cameraStream) {
      state.cameraStream.getTracks().forEach((track) => track.stop());
      state.cameraStream = null;
    }
  }

  async function compareCurrentToBaseline(blob) {
    if (!blob || !state.baselineBlob) {
      setCompareStatus("No compare yet", false);
      return;
    }
    try {
      const fd = new FormData();
      fd.append("current_file", blob, "current.jpg");
      fd.append("baseline_file", state.baselineBlob, "baseline.jpg");
      const r = await fetch("/capture/compare", { method: "POST", body: fd });
      if (!r.ok) return;
      const j = await r.json().catch(() => null);
      const compare = j?.comparison || {};
      const summary = String(compare?.summary || "Comparison ready.").trim();
      setCompareStatus("Compare ready", true);
      setCaptureGuidance(summary);
      if (qs("report-changed") && state.report) qs("report-changed").textContent = summary;
    } catch {}
  }

  function blobToPreview(blob) {
    const img = qs("agent-snapshot");
    if (!img || !blob) return;
    img.src = URL.createObjectURL(blob);
    img.style.display = "block";
    if (qs("capture-empty")) qs("capture-empty").style.display = "none";
  }

  async function captureFrame() {
    const video = qs("agent-video");
    const canvas = qs("agent-canvas");
    if (!video || !canvas || !video.videoWidth || !video.videoHeight) {
      addMessage("ai", "Start the camera first, then capture a frame.");
      return;
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
    if (!blob) return;
    if (!state.baselineBlob) state.baselineBlob = blob;
    state.currentBlob = blob;
    state.currentFile = new File([blob], `agent-capture-${Date.now()}.jpg`, { type: "image/jpeg" });
    blobToPreview(blob);
    setCaptureStatus("Frame captured", true);
    setCaptureGuidance("Frame captured. Analyse now or capture again for a steadier crop.");
    await compareCurrentToBaseline(blob);
  }

  function resetCapture() {
    state.currentBlob = null;
    state.currentFile = null;
    const img = qs("agent-snapshot");
    if (img) {
      img.style.display = "none";
      img.removeAttribute("src");
    }
    if (!state.cameraStream && qs("capture-empty")) qs("capture-empty").style.display = "flex";
    setCaptureStatus("Awaiting image", false);
    setCompareStatus(state.baselineBlob ? "Baseline saved" : "No compare yet", !!state.baselineBlob);
    setCaptureGuidance("Tip: keep one skin area centered, use natural light, and fill most of the frame.");
  }

  async function handleUpload(file) {
    if (!file) return;
    state.currentFile = file;
    state.currentBlob = file;
    if (!state.baselineBlob) state.baselineBlob = file;
    blobToPreview(file);
    setCaptureStatus("Photo selected", true);
    setCaptureGuidance("Photo selected. Analyse now or upload a steadier, closer crop if needed.");
    await compareCurrentToBaseline(file);
  }

  function buildAnalysisFormData() {
    hydrateAnswersFromStructuredInputs();
    const fd = new FormData();
    fd.append("file", state.currentFile, state.currentFile?.name || "capture.jpg");
    fd.append("body_zone", String(state.answers.body_zone || ""));
    fd.append("duration_days", String(state.answers.duration_days || 0));
    fd.append("severity", String(state.answers.severity || 0));
    fd.append("symptoms", (state.answers.symptoms || []).join(","));
    fd.append("triggers", (state.answers.triggers || []).join(","));
    return fd;
  }

  function outboundHref(url, store, productId, scanId) {
    const target = String(url || "").trim();
    if (!target) return "#";
    const params = new URLSearchParams();
    params.set("url", target);
    if (store) params.set("store", String(store));
    if (productId) params.set("product_id", String(productId));
    if (scanId) params.set("scan_id", String(scanId));
    if (state.sessionId) params.set("session_id", state.sessionId);
    return `/out?${params.toString()}`;
  }

  function buildProtocolPayload(scan) {
    const shortlisted = Array.isArray(scan?.products) ? scan.products.slice(0, 3).map((product) => String(product?.id || "").trim()).filter(Boolean) : [];

    const lowerConcern = String(state.answers.concern || "").toLowerCase();
    const sensitiveSymptoms = ["burning", "itching", "redness", "flaking"].some((symptom) => state.selectedSymptoms.has(symptom));

    return {
      scan_id: String(scan?.scan_id || ""),
      top_label: String(scan?.top_label || "uncertain"),
      selected_products: shortlisted,
      preferences: {
        sensitive_skin: sensitiveSymptoms,
        fragrance_free: true,
        pregnancy_safe: false,
        preferred_store: "",
        note: lowerConcern ? `Consultation note: ${state.answers.concern}` : "",
      },
    };
  }

  async function analyseNow() {
    hydrateAnswersFromStructuredInputs();
    if (!state.answers.concern) {
      addMessage("ai", "Before analysing, tell me in one line what is bothering you most so I can keep the reasoning grounded.");
      return;
    }
    if (!state.currentFile) {
      addMessage("ai", "I still need one clear image. Capture a frame or upload a close-up first.");
      return;
    }

    setConsultStage("Analysing");
    addMessage("ai", "I’m analysing the image, combining it with your symptoms, and building a safer protocol. Give me a moment.");

    try {
      const analysisRes = await api("/capture/analyze", { method: "POST", body: buildAnalysisFormData() });
      const analysisJson = await analysisRes.json().catch(() => ({}));
      if (!analysisRes.ok) {
        const detail = analysisJson?.detail;
        if (detail?.message) {
          addMessage("ai", detail.message);
          setCaptureGuidance(detail.message);
          return;
        }
        addMessage("ai", "I could not analyse that image safely. Please try a clearer, closer photo.");
        return;
      }

      const protocolRes = await api("/protocol/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildProtocolPayload(analysisJson)),
      });
      const protocolJson = protocolRes.ok ? await protocolRes.json().catch(() => ({})) : {};

      state.report = {
        scan: analysisJson,
        protocol: protocolJson?.plan || {},
      };

      renderReport();
      setConsultStage("Report ready");
      addMessage(
        "ai",
        `${titleCase(analysisJson?.top_label || "uncertain")} looks like the main focus right now. I’ve built a protocol, matched product picks, and added rescan plus consultation guidance in the report.`,
      );

      document.dispatchEvent(
        new CustomEvent("dermiq:agent-report", {
          detail: {
            scan: analysisJson,
            plan: protocolJson?.plan || {},
            capture_context: { ...state.answers, symptoms: Array.from(state.selectedSymptoms) },
          },
        }),
      );
      try {
        window.localStorage.setItem(
          "dermiq_agent_report",
          JSON.stringify({
            saved_at: Date.now(),
            scan: analysisJson,
            plan: protocolJson?.plan || {},
            answers: { ...state.answers, symptoms: Array.from(state.selectedSymptoms) },
          }),
        );
      } catch {}
    } catch {
      addMessage("ai", "The consultation service did not finish cleanly. Please try again in a moment.");
    }
  }

  function renderList(containerId, values) {
    const wrap = qs(containerId);
    if (!wrap) return;
    const items = Array.isArray(values) ? values.filter(Boolean) : [];
    wrap.innerHTML = items.length
      ? items.map((item) => `<div class="report-item">${escapeHtml(String(item))}</div>`).join("")
      : `<div class="report-item">No guidance available yet.</div>`;
  }

  function renderReport() {
    const report = state.report;
    if (!report) return;
    const scan = report.scan || {};
    const plan = report.protocol || {};
    const reasoning = scan.reasoning || {};
    const esc = scan.escalation || {};

    if (qs("report-condition")) qs("report-condition").textContent = titleCase(scan.top_label || "uncertain");
    if (qs("report-summary")) {
      qs("report-summary").textContent = reasoning.what_changed || scan.notes || "DermIQ used the image plus your symptom context to keep this consultation conservative.";
    }
    if (qs("report-confidence-mode")) qs("report-confidence-mode").textContent = String(scan.confidence_mode || "watch").replaceAll("_", " ");
    if (qs("report-changed")) qs("report-changed").textContent = reasoning.what_changed || "No compare available yet.";
    if (qs("report-consult")) {
      qs("report-consult").textContent =
        String(plan.when_to_consult || esc.reason || "Consult a clinician if symptoms are severe, spreading, painful, bleeding, or you are worried.");
    }
    if (qs("report-rescan")) qs("report-rescan").textContent = String(plan.when_to_rescan || "Retake a clear close-up in one week.");

    const top3 = Array.isArray(scan.top3)
      ? scan.top3.map((item) => `${titleCase(item.label)} — ${Math.round(Number(item.prob || 0) * 100)}% match`)
      : [];
    renderList("report-top3", top3);

    const protocolItems = [
      ...(Array.isArray(plan.am) ? plan.am.slice(0, 2).map((item) => `AM: ${item}`) : []),
      ...(Array.isArray(plan.pm) ? plan.pm.slice(0, 2).map((item) => `PM: ${item}`) : []),
      ...(Array.isArray(plan.weekly) ? plan.weekly.slice(0, 2).map((item) => `Weekly: ${item}`) : []),
      String(plan.today_focus || "").trim() ? `Focus: ${plan.today_focus}` : "",
    ].filter(Boolean);
    renderList("report-protocol", protocolItems);

    const productItems = Array.isArray(scan.products)
      ? scan.products.slice(0, 4).map((product) => {
          const links = Array.isArray(product.buy_links) ? product.buy_links : [];
          const firstLink = links[0];
          const href = firstLink?.url ? outboundHref(firstLink.url, firstLink.name || "store", product.id, scan.scan_id) : "";
          const buy = href ? `<a class="btn-teal" style="margin-top:10px;width:max-content" target="_blank" rel="noreferrer" href="${escapeAttribute(href)}">Open ${escapeHtml(firstLink.name || "store")}</a>` : "";
          return `<div class="report-item"><strong style="display:block;margin-bottom:4px">${escapeHtml(product.name || "Product")}</strong><div style="color:var(--w3);font-size:.8rem;line-height:1.5">${escapeHtml(product.reason || product.description || "DermIQ matched this to the current concern.")}</div>${buy}</div>`;
        })
      : [];
    const productWrap = qs("report-products");
    if (productWrap) {
      productWrap.innerHTML = productItems.length ? productItems.join("") : `<div class="report-item">No product picks available for this result.</div>`;
    }
  }

  function parseDurationDays(input) {
    const text = String(input || "").trim().toLowerCase();
    if (!text) return 0;
    const direct = Number(text);
    if (Number.isFinite(direct) && direct >= 0) return Math.round(direct);
    const match = text.match(/(\d+(?:\.\d+)?)\s*(day|days|week|weeks|month|months)/);
    if (!match) return 0;
    const value = Number(match[1] || 0);
    const unit = match[2] || "days";
    if (!Number.isFinite(value)) return 0;
    if (unit.startsWith("week")) return Math.round(value * 7);
    if (unit.startsWith("month")) return Math.round(value * 30);
    return Math.round(value);
  }

  function parseSeverity(input) {
    const num = Number(String(input || "").trim());
    if (!Number.isFinite(num)) return 0;
    return Math.max(0, Math.min(10, Math.round(num)));
  }

  function escapeHtml(text) {
    return String(text || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function escapeAttribute(text) {
    return escapeHtml(text).replaceAll("`", "&#96;");
  }

  function titleCase(label) {
    return String(label || "")
      .split("_")
      .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
      .join(" ") || "Uncertain";
  }

  function syncVoiceLabel() {
    const name = state.selectedVoice?.name || "System voice";
    const el = qs("voice-name");
    if (el) el.textContent = name;
  }

  function chooseVoice() {
    const voices = window.speechSynthesis?.getVoices?.() || [];
    if (!voices.length) return null;
    const preferredNames = [
      "Google UK English Female",
      "Microsoft Heera",
      "Microsoft Zira",
      "Samantha",
      "Karen",
      "Aria",
      "Jenny",
    ];
    const exact = voices.find((voice) => preferredNames.some((name) => voice.name.includes(name)));
    if (exact) return exact;
    const preferredLang = voices.find((voice) => /en[-_]IN|en[-_]GB|en[-_]US/i.test(voice.lang || ""));
    return preferredLang || voices[0];
  }

  function speak(text) {
    if (!state.voiceReplyOn || !window.speechSynthesis) return;
    const content = String(text || "").trim();
    if (!content) return;
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(content);
      utterance.voice = state.selectedVoice || chooseVoice();
      utterance.lang = utterance.voice?.lang || "en-IN";
      utterance.rate = 0.98;
      utterance.pitch = 0.92;
      utterance.volume = 1;
      state.selectedVoice = utterance.voice || state.selectedVoice;
      syncVoiceLabel();
      window.speechSynthesis.speak(utterance);
    } catch {}
  }

  function stopSpeaking() {
    try {
      window.speechSynthesis?.cancel?.();
    } catch {}
  }

  function setupVoiceRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const voiceBtn = qs("voice-btn");
    if (!SpeechRecognition || !voiceBtn) {
      if (voiceBtn) {
        voiceBtn.disabled = true;
        voiceBtn.textContent = "Voice unavailable";
      }
      return;
    }
    state.recognition = new SpeechRecognition();
    state.recognition.continuous = false;
    state.recognition.interimResults = false;
    state.recognition.lang = "en-IN";
    state.recognition.onstart = () => {
      state.listening = true;
      voiceBtn.classList.add("on");
      voiceBtn.textContent = "Listening...";
    };
    state.recognition.onend = () => {
      state.listening = false;
      voiceBtn.classList.remove("on");
      voiceBtn.textContent = "Voice input";
    };
    state.recognition.onerror = () => {
      state.listening = false;
      voiceBtn.classList.remove("on");
      voiceBtn.textContent = "Voice input";
    };
    state.recognition.onresult = (event) => {
      const transcript = Array.from(event.results || [])
        .map((result) => result[0]?.transcript || "")
        .join(" ")
        .trim();
      if (!transcript) return;
      const input = qs("agent-input");
      if (input) input.value = transcript;
    };
  }

  function toggleVoiceInput() {
    if (!state.recognition) return;
    if (state.listening) {
      state.recognition.stop();
    } else {
      state.recognition.start();
    }
  }

  function toggleVoiceReply() {
    state.voiceReplyOn = !state.voiceReplyOn;
    qs("voice-reply-btn")?.classList.toggle("on", state.voiceReplyOn);
    qs("voice-reply-btn").textContent = state.voiceReplyOn ? "Doctor voice on" : "Doctor voice off";
    if (!state.voiceReplyOn) stopSpeaking();
  }

  function consumeInput(text) {
    const trimmed = String(text || "").trim();
    if (!trimmed) return;
    addMessage("user", trimmed);

    const step = activeStep();
    if (step) {
      const normalized = step.normalize(trimmed);
      state.answers[step.key] = normalized;
      if (step.key === "triggers") state.answers.triggers = Array.isArray(normalized) ? normalized : [];
      state.answers.symptoms = Array.from(state.selectedSymptoms);
      updateQuickSummary();
      syncStructuredInputs();
      state.intakeStep += 1;
      askNextQuestion();
      return;
    }

    state.answers.concern = state.answers.concern || trimmed;
    updateQuickSummary();
    addMessage("ai", "Got it. You can add more detail, update the structured fields, or press Analyse now when you’re ready.");
  }

  function bindEvents() {
    qs("btn-camera-start")?.addEventListener("click", () => startCamera().catch(() => {}));
    qs("btn-camera-capture")?.addEventListener("click", () => captureFrame().catch(() => {}));
    qs("btn-camera-reset")?.addEventListener("click", () => resetCapture());
    qs("agent-upload")?.addEventListener("change", (event) => {
      const file = event.target?.files?.[0];
      handleUpload(file).catch(() => {});
    });
    qs("btn-send")?.addEventListener("click", () => {
      const input = qs("agent-input");
      if (!input) return;
      const text = input.value;
      input.value = "";
      consumeInput(text);
    });
    qs("agent-input")?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        qs("btn-send")?.click();
      }
    });
    qs("btn-analyse-now")?.addEventListener("click", () => analyseNow().catch(() => {}));
    qs("btn-print-report")?.addEventListener("click", () => window.print());
    qs("voice-btn")?.addEventListener("click", () => toggleVoiceInput());
    qs("voice-reply-btn")?.addEventListener("click", () => toggleVoiceReply());
    qs("intake-duration")?.addEventListener("input", () => {
      state.answers.duration_days = parseDurationDays(qs("intake-duration")?.value || "0");
      updateQuickSummary();
    });
    qs("intake-severity")?.addEventListener("change", () => {
      state.answers.severity = parseSeverity(qs("intake-severity")?.value || "0");
      updateQuickSummary();
    });
    qs("intake-zone")?.addEventListener("input", () => {
      state.answers.body_zone = String(qs("intake-zone")?.value || "").trim();
      updateQuickSummary();
    });
    qs("intake-triggers")?.addEventListener("input", () => {
      state.answers.triggers = String(qs("intake-triggers")?.value || "")
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
    });
    document.querySelectorAll(".symptom[data-symptom]").forEach((btn) =>
      btn.addEventListener("click", () => {
        const symptom = String(btn.getAttribute("data-symptom") || "");
        if (!symptom) return;
        if (state.selectedSymptoms.has(symptom)) {
          state.selectedSymptoms.delete(symptom);
        } else {
          state.selectedSymptoms.add(symptom);
        }
        state.answers.symptoms = Array.from(state.selectedSymptoms);
        btn.classList.toggle("on", state.selectedSymptoms.has(symptom));
      }),
    );
    window.addEventListener("beforeunload", () => {
      stopCamera();
      stopSpeaking();
    });
    window.speechSynthesis?.addEventListener?.("voiceschanged", () => {
      state.selectedVoice = chooseVoice();
      syncVoiceLabel();
    });
  }

  function init() {
    ensureSession().catch(() => {});
    state.selectedVoice = chooseVoice();
    syncVoiceLabel();
    setupVoiceRecognition();
    bindEvents();
    updateQuickSummary();
    askNextQuestion();
  }

  init();
})();
