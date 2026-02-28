/**
 * AdvisorIQ — Frontend
 * Login, onboarding, and advisor dashboard.
 */

const API_BASE = "http://localhost:8001";
const TOKEN_KEY = "advisoriq_token";

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function fetchAPI(path, options = {}) {
  const headers = { ...options.headers };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    showLogin();
    throw new Error("Session expired");
  }
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

function showLogin() {
  document.getElementById("loginScreen").style.display = "block";
  document.getElementById("appScreen").style.display = "none";
}

function showApp() {
  document.getElementById("loginScreen").style.display = "none";
  document.getElementById("appScreen").style.display = "block";
}

function showView(view) {
  const dashboard = document.getElementById("dashboardSections");
  const onboarding = document.getElementById("onboardingView");
  if (view === "onboarding") {
    dashboard.style.display = "none";
    onboarding.style.display = "block";
  } else {
    dashboard.style.display = "block";
    onboarding.style.display = "none";
  }
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function renderClientCard(portfolio) {
  const c = portfolio.client;
  const iv = portfolio.iv_adjusted_optimal;
  const currentVol = portfolio.current_annual_vol;
  const targetVol = c.target_annual_vol;
  let statusClass = "";

  if (typeof currentVol === "number" && typeof targetVol === "number" && targetVol > 0) {
    const ratio = currentVol / targetVol;
    if (ratio <= 1.1 && !portfolio.misaligned_with_profile) {
      statusClass = "client-card--good";
    } else if (ratio >= 1.3 || portfolio.misaligned_with_profile) {
      statusClass = "client-card--risk";
    }
  }

  const hasUpdate = portfolio.has_recent_update || !!portfolio.last_updated;
  const driftEntries = Object.entries(portfolio.drift_from_optimal)
    .filter(([, v]) => Math.abs(v) > 0.01)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, 3);
  const driftStr = driftEntries.length
    ? driftEntries.map(([s, v]) => `${s} ${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}%`).join(", ")
    : "—";

  return `
    <article class="client-card ${statusClass} ${portfolio.misaligned_with_profile ? "misaligned" : ""}" data-client-id="${c.client_id}">
      <div class="client-card-header">
        <div class="client-card-name">${escapeHtml(c.name)}</div>
        ${hasUpdate ? '<span class="client-card-updated">Updated</span>' : ""}
      </div>
      <div class="client-card-risk">${c.risk_label} · target vol ${(c.target_annual_vol * 100).toFixed(1)}%</div>
      <div class="client-card-stats">
        <div class="client-card-stat">
          <span>Current vol</span>
          <span>${(portfolio.current_annual_vol * 100).toFixed(1)}%</span>
        </div>
        <div class="client-card-stat">
          <span>IV-adj Sharpe</span>
          <span>${iv.sharpe.toFixed(2)}</span>
        </div>
        <div class="client-card-stat">
          <span>Drift</span>
          <span>${driftStr}</span>
        </div>
      </div>
      ${portfolio.misaligned_with_profile ? '<div class="client-card-alert">Risk profile misaligned</div>' : ""}
    </article>
  `;
}

function renderSignalsTable(signals) {
  return signals
    .map(
      (s) => `
    <tr>
      <td><strong>${escapeHtml(s.symbol)}</strong></td>
      <td>${(s.iv * 100).toFixed(1)}%</td>
      <td>${(s.predicted_hv * 100).toFixed(1)}%</td>
      <td>${s.ivr.toFixed(2)}</td>
      <td>${(s.iv_percentile * 100).toFixed(0)}%</td>
      <td>${escapeHtml(s.regime)}</td>
      <td class="${s.fear_level === "HIGH_FEAR" ? "fear-high" : s.fear_level === "ELEVATED_FEAR" ? "fear-elevated" : ""}">${escapeHtml(s.fear_level)}</td>
      <td>${escapeHtml(s.recommended_action)}</td>
    </tr>
  `
    )
    .join("");
}

function renderStressCard(scenario) {
  const lossCur = (scenario.portfolio_loss_pct_current * 100).toFixed(1);
  const lossIv = (scenario.portfolio_loss_pct_iv_adjusted * 100).toFixed(1);
  return `
    <div class="stress-card">
      <div class="stress-card-name">${escapeHtml(scenario.name.replace(/_/g, " "))}</div>
      <div class="stress-card-desc">${escapeHtml(scenario.description)}</div>
      <div class="stress-card-losses">
        <div class="stress-loss">
          <div class="stress-loss-label">Current</div>
          <div class="stress-loss-value negative">${lossCur}%</div>
        </div>
        <div class="stress-loss">
          <div class="stress-loss-label">IV-adjusted</div>
          <div class="stress-loss-value negative">${lossIv}%</div>
        </div>
      </div>
    </div>
  `;
}

function showModal(html) {
  const modal = document.getElementById("modal");
  const body = document.getElementById("modalBody");
  body.innerHTML = html;
  modal.setAttribute("aria-hidden", "false");
}

function hideModal() {
  document.getElementById("modal").setAttribute("aria-hidden", "true");
}

async function openClientNarrative(clientId) {
  try {
    const data = await fetchAPI(`/api/explain/${clientId}`);
    const fearList =
      data.top_fear_signals?.length > 0
        ? `<ul class="narrative-fear-list">${data.top_fear_signals
            .map(
              (s) =>
                `<li><strong>${escapeHtml(s.symbol)}</strong> IVR ${s.ivr.toFixed(2)} — ${escapeHtml(s.recommended_action)}</li>`
            )
            .join("")}</ul>`
        : "<p>No elevated fear signals for this client.</p>";

    const html = `
      <h3 class="narrative-title">${escapeHtml(data.title)}</h3>
      <div class="narrative-regime">Regime: ${escapeHtml(data.regime)}</div>
      <div class="narrative-body">${escapeHtml(data.body)}</div>
      <ul class="narrative-points">${(data.key_points || []).map((p) => `<li>${escapeHtml(p)}</li>`).join("")}</ul>
      <div class="narrative-fear">
        <div class="narrative-fear-title">Top fear signals</div>
        ${fearList}
      </div>
    `;
    showModal(html);
  } catch (e) {
    showModal(`<p class="error">Failed to load narrative: ${escapeHtml(e.message)}</p>`);
  }
}

async function loadDashboard() {
  const regimeEl = document.getElementById("regimeBadge");
  const clientGrid = document.getElementById("clientGrid");
  const signalsBody = document.getElementById("signalsBody");
  const stressGrid = document.getElementById("stressGrid");
  const metricRegimeEl = document.getElementById("metricRegime");
  const metricAvgIvEl = document.getElementById("metricAvgIv");
  const metricHighFearEl = document.getElementById("metricHighFear");
  const metricMaxIvrEl = document.getElementById("metricMaxIvr");

  regimeEl.textContent = "Loading…";
  clientGrid.innerHTML = '<p class="loading">Loading…</p>';
  signalsBody.innerHTML = "";
  stressGrid.innerHTML = '<p class="loading">Loading…</p>';

  try {
    const [universeRes, signalsRes, portfoliosRes, stressRes] = await Promise.all([
      fetchAPI("/api/universe"),
      fetchAPI("/api/signals"),
      fetchAPI("/api/portfolios"),
      fetchAPI("/api/stress-tests"),
    ]);

    const regime = universeRes.regime || signalsRes.regime || "—";
    regimeEl.textContent = regime;

    const signals = signalsRes.signals || [];
    if (metricRegimeEl) metricRegimeEl.textContent = regime;

    if (signals.length > 0) {
      const avgIv =
        signals.reduce((sum, s) => sum + (typeof s.iv === "number" ? s.iv : 0), 0) /
        signals.filter((s) => typeof s.iv === "number").length;
      const highFearCount = signals.filter(
        (s) => s.fear_level === "HIGH_FEAR" || s.fear_level === "ELEVATED_FEAR"
      ).length;
      const maxIvr = Math.max(
        ...signals
          .map((s) => s.ivr)
          .filter((v) => typeof v === "number" && Number.isFinite(v))
      );

      if (metricAvgIvEl && Number.isFinite(avgIv)) {
        metricAvgIvEl.textContent = `${(avgIv * 100).toFixed(1)}%`;
      }
      if (metricHighFearEl) {
        metricHighFearEl.textContent = String(highFearCount);
      }
      if (metricMaxIvrEl && Number.isFinite(maxIvr)) {
        metricMaxIvrEl.textContent = maxIvr.toFixed(2);
      }
    } else {
      if (metricAvgIvEl) metricAvgIvEl.textContent = "—";
      if (metricHighFearEl) metricHighFearEl.textContent = "—";
      if (metricMaxIvrEl) metricMaxIvrEl.textContent = "—";
    }

    clientGrid.innerHTML = (portfoliosRes.portfolios || []).map(renderClientCard).join("");
    clientGrid.querySelectorAll(".client-card").forEach((card) => {
      card.addEventListener("click", () => openClientNarrative(card.dataset.clientId));
    });

    signalsBody.innerHTML = renderSignalsTable(signalsRes.signals || []);

    stressGrid.innerHTML = (stressRes.scenarios || []).map(renderStressCard).join("");
  } catch (e) {
    if (e.message !== "Session expired") {
      regimeEl.textContent = "—";
      clientGrid.innerHTML = `<p class="error">API unreachable. Start backend: <code>cd backend && uvicorn app.main:app --reload --port 8001</code></p>`;
      signalsBody.innerHTML = "";
      stressGrid.innerHTML = "";
    }
  }
}

async function init() {
  const token = getToken();
  if (!token) {
    showLogin();
    return;
  }

  try {
    await fetchAPI("/api/auth/me");
    showApp();
    showView("dashboard");
    await loadDashboard();
  } catch (e) {
    showLogin();
  }
}

// Login form
document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const email = form.email.value.trim();
  const password = form.password.value;
  const errEl = document.getElementById("loginError");

  errEl.style.display = "none";
  try {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      errEl.textContent = data.detail || "Invalid email or password";
      errEl.style.display = "block";
      return;
    }
    setToken(data.token);
    showApp();
    showView("dashboard");
    await loadDashboard();
  } catch (e) {
    errEl.textContent = e.message || "Connection failed";
    errEl.style.display = "block";
  }
});

// Logout
document.getElementById("logoutBtn").addEventListener("click", () => {
  clearToken();
  showLogin();
});

// Nav links
document.querySelectorAll('[data-view]').forEach((a) => {
  a.addEventListener("click", (e) => {
    e.preventDefault();
    showView(a.dataset.view);
  });
});

// Onboarding form
document.getElementById("onboardingForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const name = form.name.value.trim();
  const risk_label = form.risk_label.value;
  const target_annual_vol = parseFloat(form.target_annual_vol.value) / 100;
  const errEl = document.getElementById("onboardingError");
  const successEl = document.getElementById("onboardingSuccess");

  errEl.style.display = "none";
  successEl.style.display = "none";

  try {
    const client = await fetchAPI("/api/clients", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, risk_label, target_annual_vol }),
    });
    successEl.textContent = `Added ${escapeHtml(client.name)} (${client.client_id}). They will appear in the dashboard.`;
    successEl.style.display = "block";
    form.reset();
    document.getElementById("targetVol").value = 12;
    await loadDashboard();
  } catch (e) {
    errEl.textContent = e.message || "Failed to add client";
    errEl.style.display = "block";
  }
});

// Risk profile -> default target vol
document.getElementById("riskLabel").addEventListener("change", (e) => {
  const defaults = { CONSERVATIVE: 8, MODERATE: 12, AGGRESSIVE: 18 };
  document.getElementById("targetVol").value = defaults[e.target.value] || 12;
});

document.getElementById("modalBackdrop").addEventListener("click", hideModal);
document.getElementById("modalClose").addEventListener("click", hideModal);

init();
