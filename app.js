/**
 * Academic Job Board — app.js
 * Loads jobs.json, renders province-grouped job cards.
 * Ontario + BC shown first; other provinces behind an expand button.
 */

// ── Config ────────────────────────────────────────────────────────────────

const PRIORITY_PROVINCES = ["Ontario", "British Columbia"];

const PROVINCE_ORDER = [
  "Ontario", "British Columbia",
  "Alberta", "Quebec", "Manitoba", "Saskatchewan",
  "Nova Scotia", "New Brunswick", "Newfoundland and Labrador",
  "Prince Edward Island", "Northwest Territories", "Yukon", "Nunavut",
  "Unknown",
];

// ── State ─────────────────────────────────────────────────────────────────

let allJobs = [];
let activeMatchFilter = "all";
let activeSearch = "";

// ── Utilities ─────────────────────────────────────────────────────────────

/**
 * Format an ISO timestamp into a human-readable string.
 */
function formatTimestamp(iso) {
  if (!iso) return "never";
  const d = new Date(iso);
  return d.toLocaleString("en-CA", {
    timeZone: "America/Toronto",
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  }) + " EST";
}

/**
 * Classify a deadline string into urgency: "ok" | "warn" | "red" | "unknown"
 */
function deadlineUrgency(deadlineStr) {
  if (!deadlineStr) return "unknown";

  const now = new Date();
  const deadline = new Date(deadlineStr);
  if (isNaN(deadline.getTime())) return "unknown";

  const days = Math.ceil((deadline - now) / (1000 * 60 * 60 * 24));
  if (days < 0)  return "past";
  if (days <= 14) return "red";
  if (days <= 28) return "warn";
  return "ok";
}

/**
 * Format deadline for display. Returns an object { text, cssClass }.
 */
function formatDeadline(deadlineStr) {
  if (!deadlineStr) return { text: "Deadline: not listed", cssClass: "deadline-ok" };

  const urgency = deadlineUrgency(deadlineStr);

  if (urgency === "past") {
    return { text: `Closed: ${deadlineStr}`, cssClass: "deadline-ok" };
  }

  const classMap = { ok: "deadline-ok", warn: "deadline-warn", red: "deadline-red", unknown: "deadline-ok" };
  const prefixMap = {
    ok:      "Deadline:",
    warn:    "⚠ Deadline:",
    red:     "⚡ Deadline:",
    unknown: "Deadline:",
  };

  return {
    text: `${prefixMap[urgency] || "Deadline:"} ${deadlineStr}`,
    cssClass: classMap[urgency] || "deadline-ok",
  };
}

/**
 * Escape HTML to safely insert user-provided strings.
 */
function esc(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Filtering ─────────────────────────────────────────────────────────────

function filterJobs(jobs) {
  return jobs.filter((job) => {
    // Match filter
    if (activeMatchFilter === "strong" && job.match !== "strong") return false;
    if (activeMatchFilter === "strong,partial" && !["strong", "partial"].includes(job.match)) return false;

    // Keyword search
    if (activeSearch) {
      const q = activeSearch.toLowerCase();
      const haystack = [job.title, job.institution, job.location, job.province]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(q)) return false;
    }

    return true;
  });
}

// ── Rendering ─────────────────────────────────────────────────────────────

function renderBadge(match) {
  if (match === "strong") {
    return `<span class="badge badge-strong">Strong Match</span>`;
  }
  if (match === "partial") {
    return `<span class="badge badge-partial">Partial Match</span>`;
  }
  return "";
}

function renderJobCard(job) {
  const dl = formatDeadline(job.deadline);
  const applyUrl = esc(job.apply_url || job.url || "#");
  const postingUrl = esc(job.url || "#");
  const matchClass = job.match === "strong" ? "match-strong" : job.match === "partial" ? "match-partial" : "";

  return `
    <div class="job-card ${matchClass}">
      <div class="job-main">
        <div class="job-title">
          <a href="${postingUrl}" target="_blank" rel="noopener">${esc(job.title)}</a>
        </div>
        <div class="job-institution">${esc(job.institution || "Institution not listed")}</div>
        <div class="job-meta">
          ${job.location ? `<span class="job-location">📍 ${esc(job.location)}</span>` : ""}
          <span class="job-deadline ${dl.cssClass}">${esc(dl.text)}</span>
        </div>
      </div>
      <div class="job-actions">
        ${renderBadge(job.match)}
        <a class="btn-apply" href="${applyUrl}" target="_blank" rel="noopener">Apply →</a>
      </div>
    </div>
  `.trim();
}

function renderProvinceSection(province, jobs) {
  const cards = jobs.map(renderJobCard).join("\n");
  const count = jobs.length;

  return `
    <section class="province-section">
      <div class="province-header">
        <span class="province-name">${esc(province)}</span>
        <span class="province-count">${count} posting${count !== 1 ? "s" : ""}</span>
      </div>
      <div class="jobs-grid">
        ${cards}
      </div>
    </section>
  `.trim();
}

function groupByProvince(jobs) {
  const groups = {};
  for (const job of jobs) {
    const p = job.province || "Unknown";
    if (!groups[p]) groups[p] = [];
    groups[p].push(job);
  }
  return groups;
}

function render(jobs) {
  const app = document.getElementById("app");
  const filtered = filterJobs(jobs);

  // Update count
  document.getElementById("job-count").textContent =
    `${filtered.length} posting${filtered.length !== 1 ? "s" : ""} shown`;

  if (filtered.length === 0) {
    app.innerHTML = `
      <div class="empty-state">
        <p>No job postings match your current filters.</p>
        <p style="font-size:0.8rem;color:var(--text-dim)">
          Try broadening the match filter or clearing the search.
        </p>
      </div>
    `;
    return;
  }

  const groups = groupByProvince(filtered);

  // Split into priority (ON, BC) and others
  const prioritySections = [];
  const otherSections = [];

  // Sort provinces by PROVINCE_ORDER, with anything else alphabetically after
  const sortedProvinces = Object.keys(groups).sort((a, b) => {
    const ai = PROVINCE_ORDER.indexOf(a);
    const bi = PROVINCE_ORDER.indexOf(b);
    const an = ai === -1 ? 999 : ai;
    const bn = bi === -1 ? 999 : bi;
    if (an !== bn) return an - bn;
    return a.localeCompare(b);
  });

  for (const province of sortedProvinces) {
    const html = renderProvinceSection(province, groups[province]);
    if (PRIORITY_PROVINCES.includes(province)) {
      prioritySections.push(html);
    } else {
      otherSections.push(html);
    }
  }

  let html = prioritySections.join("\n");

  if (otherSections.length > 0) {
    const otherCount = otherSections.reduce((n, _, i) => {
      const match = otherSections[i].match(/class="province-count">(\d+)/);
      return n + (match ? parseInt(match[1]) : 0);
    }, 0);

    html += `
      <div class="expand-section">
        <button class="btn-expand" id="btn-expand">
          Show other provinces (${otherCount} more posting${otherCount !== 1 ? "s" : ""})
        </button>
      </div>
      <div class="other-provinces" id="other-provinces">
        ${otherSections.join("\n")}
      </div>
    `;
  }

  app.innerHTML = html;

  // Wire up expand button
  const btn = document.getElementById("btn-expand");
  const otherDiv = document.getElementById("other-provinces");
  if (btn && otherDiv) {
    btn.addEventListener("click", () => {
      otherDiv.classList.toggle("visible");
      if (otherDiv.classList.contains("visible")) {
        btn.textContent = "Hide other provinces";
      } else {
        btn.textContent = btn.textContent.replace("Hide", "Show");
      }
    });
  }
}

// ── Data Loading ──────────────────────────────────────────────────────────

async function loadJobs() {
  try {
    // Cache-bust so GitHub Pages doesn't serve stale jobs.json
    const url = `jobs.json?t=${Math.floor(Date.now() / 60000)}`;
    const resp = await fetch(url);

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    const data = await resp.json();

    // Update last-updated timestamp
    const lastUpdatedEl = document.getElementById("last-updated");
    if (data.last_updated) {
      lastUpdatedEl.textContent = `Updated: ${formatTimestamp(data.last_updated)}`;
    } else {
      lastUpdatedEl.textContent = "Not yet refreshed — trigger the GitHub Action manually";
    }

    allJobs = data.jobs || [];

    if (allJobs.length === 0) {
      document.getElementById("app").innerHTML = `
        <div class="empty-state">
          <p>No job postings found yet.</p>
          <p style="font-size:0.8rem;color:var(--text-dim)">
            The scraper may not have run yet. Go to your repository → Actions →
            "Refresh Job Listings" → Run workflow to trigger it manually.
          </p>
        </div>
      `;
      document.getElementById("job-count").textContent = "0 postings";
      return;
    }

    render(allJobs);

  } catch (err) {
    console.error("Failed to load jobs.json:", err);
    document.getElementById("app").innerHTML = `
      <div class="error-state">
        <p>Could not load job listings.</p>
        <p style="font-size:0.8rem;">${esc(err.message)}</p>
        <p style="font-size:0.75rem;color:var(--text-dim)">
          Make sure jobs.json exists in the repository root and GitHub Pages is enabled.
        </p>
      </div>
    `;
  }
}

// ── Filter Events ─────────────────────────────────────────────────────────

document.getElementById("filter-match").addEventListener("change", (e) => {
  activeMatchFilter = e.target.value;
  render(allJobs);
});

let searchTimer;
document.getElementById("filter-search").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    activeSearch = e.target.value.trim();
    render(allJobs);
  }, 250);
});

// ── Init ──────────────────────────────────────────────────────────────────

loadJobs();
