/**
 * Academic Job Board — app.js
 * Loads jobs.json, renders province-grouped tables in Cat Alert style.
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
let activeSourceFilter = "all";
let activeSearch = "";

// ── Dark mode ─────────────────────────────────────────────────────────────

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const btn = document.getElementById("theme-toggle");
  if (btn) btn.textContent = theme === "dark" ? "☀️ Light" : "🌙 Dark";
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme");
  const next = current === "dark" ? "light" : "dark";
  applyTheme(next);
  localStorage.setItem("acad-job-theme", next);
}

// Expose globally for onclick
window.toggleTheme = toggleTheme;

// ── Helpers ───────────────────────────────────────────────────────────────

function esc(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtTimestamp(iso) {
  if (!iso) return "never";
  const d = new Date(iso);
  return d.toLocaleString("en-CA", {
    timeZone: "America/Toronto",
    month: "short", day: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  }) + " ET";
}

function fmtRelative(iso) {
  if (!iso) return "";
  const diff = Math.round((Date.now() - new Date(iso)) / 1000);
  if (diff < 90)    return `${diff}s ago`;
  if (diff < 3600)  return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

function deadlineClass(deadlineStr) {
  if (!deadlineStr) return "dl-none";
  const d = new Date(deadlineStr);
  if (isNaN(d)) return "dl-none";
  const days = Math.ceil((d - Date.now()) / 86400000);
  if (days < 0)  return "dl-ok";   // past — show grey
  if (days <= 14) return "dl-red";
  if (days <= 28) return "dl-warn";
  return "dl-ok";
}

function deadlineLabel(deadlineStr) {
  if (!deadlineStr) return '<span class="dl-none">Deadline: not listed</span>';
  const cls = deadlineClass(deadlineStr);
  const d = new Date(deadlineStr);
  const days = isNaN(d) ? null : Math.ceil((d - Date.now()) / 86400000);
  let prefix = "Deadline:";
  if (days !== null && days >= 0 && days <= 14) prefix = "⚡ Deadline:";
  else if (days !== null && days >= 0 && days <= 28) prefix = "⚠ Deadline:";
  return `<span class="${cls}">${prefix} ${esc(deadlineStr)}</span>`;
}

// ── Filtering ─────────────────────────────────────────────────────────────

function filterJobs(jobs) {
  return jobs.filter((j) => {
    if (activeMatchFilter === "strong" && j.match !== "strong") return false;
    if (activeMatchFilter === "strong,partial" && !["strong", "partial"].includes(j.match)) return false;
    if (activeSourceFilter !== "all" && j.source !== activeSourceFilter) return false;
    if (activeSearch) {
      const q = activeSearch.toLowerCase();
      const hay = [j.title, j.institution, j.location, j.province, j.source].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

// ── Rendering ─────────────────────────────────────────────────────────────

function renderBadge(match) {
  if (match === "strong")  return `<span class="badge badge-strong">Strong Match</span>`;
  if (match === "partial") return `<span class="badge badge-partial">Partial Match</span>`;
  return "";
}

function renderJobRow(job) {
  const applyUrl = esc(job.apply_url || job.url || "#");
  const postUrl  = esc(job.url || "#");
  const source   = esc(job.source || "");
  const inst     = esc(job.institution || "Institution not listed");

  return `
    <tr>
      <td class="col-title">
        <a class="job-title-link" href="${postUrl}" target="_blank" rel="noopener">${esc(job.title)}</a>
        ${source ? `<div class="job-source">via ${source}</div>` : ""}
      </td>
      <td class="col-inst">${inst}</td>
      <td class="col-dl">${deadlineLabel(job.deadline)}</td>
      <td class="col-match">${renderBadge(job.match)}</td>
      <td class="col-apply">
        <a class="btn-apply" href="${applyUrl}" target="_blank" rel="noopener">Apply →</a>
      </td>
    </tr>
  `.trim();
}

function renderProvinceSection(province, jobs) {
  const rows = jobs.map(renderJobRow).join("\n");
  return `
    <section class="province-section">
      <div class="section-title">
        ${esc(province)}
        <span class="province-count">${jobs.length} posting${jobs.length !== 1 ? "s" : ""}</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>Position</th>
            <th>Institution</th>
            <th>Deadline</th>
            <th>Match</th>
            <th></th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </section>
  `.trim();
}

function groupByProvince(jobs) {
  const groups = {};
  for (const j of jobs) {
    const p = j.province || "Unknown";
    (groups[p] = groups[p] || []).push(j);
  }
  return groups;
}

function render(jobs) {
  const app = document.getElementById("app");
  const filtered = filterJobs(jobs);

  // Update summary cards
  document.getElementById("val-total").textContent   = filtered.length;
  document.getElementById("val-strong").textContent  = filtered.filter(j => j.match === "strong").length;
  document.getElementById("val-partial").textContent = filtered.filter(j => j.match === "partial").length;

  if (filtered.length === 0) {
    app.innerHTML = `
      <div class="empty-state">
        <p>No job postings match your current filters.</p>
        <p>Try broadening the match filter, clearing the search, or triggering a manual scrape.</p>
      </div>
    `;
    return;
  }

  const groups = groupByProvince(filtered);

  const sortedProvinces = Object.keys(groups).sort((a, b) => {
    const ai = PROVINCE_ORDER.indexOf(a);
    const bi = PROVINCE_ORDER.indexOf(b);
    return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi) || a.localeCompare(b);
  });

  const priorityHTML = [];
  const otherHTML    = [];
  let   otherCount   = 0;

  for (const p of sortedProvinces) {
    const html = renderProvinceSection(p, groups[p]);
    if (PRIORITY_PROVINCES.includes(p)) {
      priorityHTML.push(html);
    } else {
      otherHTML.push(html);
      otherCount += groups[p].length;
    }
  }

  let out = priorityHTML.join("\n");

  if (otherHTML.length) {
    out += `
      <div class="expand-section">
        <button class="btn-expand" id="btn-expand">
          Show other provinces (${otherCount} posting${otherCount !== 1 ? "s" : ""})
        </button>
      </div>
      <div class="other-provinces" id="other-provinces">
        ${otherHTML.join("\n")}
      </div>
    `;
  }

  app.innerHTML = out;

  // Wire expand button
  const btn = document.getElementById("btn-expand");
  const div = document.getElementById("other-provinces");
  if (btn && div) {
    btn.addEventListener("click", () => {
      div.classList.toggle("visible");
      btn.textContent = div.classList.contains("visible")
        ? "Hide other provinces"
        : `Show other provinces (${otherCount} posting${otherCount !== 1 ? "s" : ""})`;
    });
  }
}

// ── Populate source filter dropdown ───────────────────────────────────────

function populateSourceFilter(jobs) {
  const select = document.getElementById("filter-source");
  const sources = [...new Set(jobs.map(j => j.source || "Unknown"))].sort();
  sources.forEach((src) => {
    const opt = document.createElement("option");
    opt.value = src;
    opt.textContent = src;
    select.appendChild(opt);
  });
}

// ── Data loading ──────────────────────────────────────────────────────────

async function load() {
  try {
    const resp = await fetch(`jobs.json?t=${Math.floor(Date.now() / 60000)}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    // Timestamps
    const updatedEl = document.getElementById("val-updated");
    const subEl     = document.getElementById("sub-updated");
    if (data.last_updated) {
      updatedEl.textContent = fmtRelative(data.last_updated);
      subEl.textContent     = fmtTimestamp(data.last_updated);
    } else {
      updatedEl.textContent = "—";
      subEl.textContent     = "Not yet scraped";
    }

    // Sources count
    const srcVal = document.getElementById("val-sources");
    const srcSub = document.getElementById("sub-sources");
    if (data.sources_checked !== undefined) {
      srcVal.textContent = `${data.sources_successful ?? "?"} / ${data.sources_checked}`;
      srcSub.textContent = "returned results";
    }

    allJobs = data.jobs || [];

    if (allJobs.length === 0) {
      document.getElementById("val-total").textContent   = "0";
      document.getElementById("val-strong").textContent  = "0";
      document.getElementById("val-partial").textContent = "0";
      document.getElementById("app").innerHTML = `
        <div class="empty-state">
          <p>No job postings found yet.</p>
          <p>Click <strong>Run Scraper Now</strong> above to trigger the first scrape,<br>
             then reload this page after ~2 minutes.</p>
        </div>
      `;
      return;
    }

    populateSourceFilter(allJobs);
    render(allJobs);

  } catch (err) {
    console.error(err);
    document.getElementById("app").innerHTML = `
      <div class="empty-state">
        <p>Could not load jobs.json — ${esc(err.message)}</p>
        <p>Make sure GitHub Pages is enabled and the scraper has run at least once.</p>
      </div>
    `;
  }
}

// ── Filter event listeners ────────────────────────────────────────────────

document.getElementById("filter-match").addEventListener("change", (e) => {
  activeMatchFilter = e.target.value;
  render(allJobs);
});

document.getElementById("filter-source").addEventListener("change", (e) => {
  activeSourceFilter = e.target.value;
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

// Restore saved theme preference (default: dark)
applyTheme(localStorage.getItem("acad-job-theme") || "dark");

load();
setInterval(load, 60_000);
