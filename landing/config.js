// Optional deployment configuration for the static landing site.
// - For production, edit these values (or generate this file during deploy).
// - Keep this file committed if you want a simple "edit config, redeploy" workflow.

// Backend API base URL used by the demo uploader on the landing page.
// Example (separate backend): "https://api.yourdomain.com"
// Default: empty, which means "use the same origin as this page".
window.DERMIQ_API_BASE = window.DERMIQ_API_BASE || "";

// Where the "GitHub" footer link should point.
window.DERMIQ_GITHUB_URL = window.DERMIQ_GITHUB_URL || "";

// Public support/contact email.
window.DERMIQ_CONTACT_EMAIL = window.DERMIQ_CONTACT_EMAIL || "support@example.com";

// Optional: basic telemetry + feedback (disabled by default).
// If you enable it, also set ENABLE_TELEMETRY=1 on the backend.
window.DERMIQ_ENABLE_TELEMETRY = window.DERMIQ_ENABLE_TELEMETRY || false;
