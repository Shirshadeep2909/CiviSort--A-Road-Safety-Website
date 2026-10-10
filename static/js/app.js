(() => {
  const bounds = window.CIVISORT.bounds;
  const state = {
    role: "resident",
    rain: false,
    night: false,
    school_hours: false,
    budget: 70000,
    reports: [],
    selectedId: null,
    plan: null,
    map: null,
    markers: {},
    tileErrors: 0,
    usingSchematic: false,
  };

  const $ = (id) => document.getElementById(id);
  const listEl = $("list");
  const detailEl = $("detail");
  const planEl = $("plan");
  const toastEl = $("toast");

  function toast(msg) {
    toastEl.hidden = false;
    toastEl.textContent = msg;
    setTimeout(() => { toastEl.hidden = true; }, 4200);
  }

  function headers(extra) {
    return Object.assign({ "X-CiviSort-Role": state.role }, extra || {});
  }

  function qs(extra) {
    const p = new URLSearchParams({
      rain: state.rain,
      night: state.night,
      school_hours: state.school_hours,
      category: $("filter-category").value,
      evidence_status: $("filter-evidence").value,
      repair_status: $("filter-repair").value,
    });
    return p.toString();
  }

  function labelCat(c) {
    return {
      pothole: "Pothole",
      drainage: "Drainage",
      streetlight: "Streetlight",
      crossing: "Crossing / access",
    }[c] || c;
  }

  function repairLabel(s) {
    return {
      reported: "Reported",
      verified: "Verified",
      planned: "Planned",
      repair_claimed: "Repair claimed",
      closed: "Closed",
    }[s] || s;
  }

  function evidenceLabel(s) {
    return { unverified: "Unverified", verified: "Verified", disputed: "Disputed" }[s] || s;
  }

  function pill(kind, text) {
    return `<span class="pill"><i class="dot ${kind}"></i>${text}</span>`;
  }

  function escapeText(value) {
    const el = document.createElement("div");
    el.textContent = value == null ? "" : String(value);
    return el.innerHTML;
  }

  async function api(url, options) {
    const opts = options || {};
    opts.headers = headers(opts.headers);
    const res = await fetch(url, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Request failed");
    return data;
  }

  function latLngToSchematic(lat, lng) {
    const x = ((lng - bounds.min_lng) / (bounds.max_lng - bounds.min_lng)) * 100;
    const y = (1 - (lat - bounds.min_lat) / (bounds.max_lat - bounds.min_lat)) * 100;
    return { x: Math.min(96, Math.max(4, x)), y: Math.min(96, Math.max(4, y)) };
  }

  function initMap() {
    const southWest = L.latLng(bounds.min_lat, bounds.min_lng);
    const northEast = L.latLng(bounds.max_lat, bounds.max_lng);
    state.map = L.map("map", { scrollWheelZoom: true }).setView(bounds.center, 17);
    state.map.setMaxBounds(L.latLngBounds(southWest, northEast).pad(0.2));
    const tiles = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    });
    tiles.on("tileerror", () => {
      state.tileErrors += 1;
      if (state.tileErrors >= 4) showSchematic("OpenStreetMap tiles failed to load.");
    });
    tiles.addTo(state.map);
    state.map.on("click", (ev) => {
      $("form-lat").value = ev.latlng.lat.toFixed(6);
      $("form-lng").value = ev.latlng.lng.toFixed(6);
    });
  }

  function showSchematic(reason) {
    if (state.usingSchematic) return;
    state.usingSchematic = true;
    $("map").classList.add("hidden");
    $("schematic").hidden = false;
    $("schematic").classList.remove("hidden");
    $("map-status").textContent = reason + " Using the labelled local schematic.";
    renderSchematic();
  }

  function bindSchematicPlacement() {
    const stage = document.querySelector(".schematic-stage");
    if (!stage) return;
    stage.addEventListener("click", (ev) => {
      if (ev.target.closest(".schematic-pin")) return;
      const rect = stage.getBoundingClientRect();
      const x = (ev.clientX - rect.left) / rect.width;
      const y = (ev.clientY - rect.top) / rect.height;
      $("form-lng").value = (bounds.min_lng + x * (bounds.max_lng - bounds.min_lng)).toFixed(6);
      $("form-lat").value = (bounds.max_lat - y * (bounds.max_lat - bounds.min_lat)).toFixed(6);
      toast("Location set. Choose Report a hazard to continue.");
    });
  }

  function renderSchematic() {
    const wrap = $("schematic-pins");
    wrap.replaceChildren();
    state.reports.forEach((r) => {
      const pos = latLngToSchematic(r.lat, r.lng);
      const btn = document.createElement("button");
      btn.className = "schematic-pin" + (r.id === state.selectedId ? " active" : "");
      btn.style.left = pos.x + "%";
      btn.style.top = pos.y + "%";
      btn.type = "button";
      const span = document.createElement("span");
      span.textContent = r.public_code;
      btn.appendChild(span);
      btn.addEventListener("click", () => selectReport(r.id));
      wrap.appendChild(btn);
    });
  }

  function markerIcon(active) {
    const color = active ? "#c8891a" : "#2a6f6f";
    return L.divIcon({
      className: "pin",
      html: `<svg width="22" height="28" viewBox="0 0 22 28"><path fill="${color}" d="M11 0C5 0 1 5 1 11c0 8 10 17 10 17s10-9 10-17C21 5 17 0 11 0z"/><circle cx="11" cy="11" r="4" fill="#fffcf7"/></svg>`,
      iconSize: [22, 28],
      iconAnchor: [11, 28],
    });
  }

  function renderMap() {
    Object.values(state.markers).forEach((m) => m.remove());
    state.markers = {};
    if (!state.map) return;
    state.reports.forEach((r) => {
      const marker = L.marker([r.lat, r.lng], { icon: markerIcon(r.id === state.selectedId), title: r.public_code });
      marker.on("click", () => selectReport(r.id));
      marker.addTo(state.map);
      state.markers[r.id] = marker;
    });
    if (state.usingSchematic) renderSchematic();
  }

  function renderList() {
    $("list-status").textContent = state.reports.length ? `${state.reports.length} records` : "No reports match these filters.";
    listEl.replaceChildren();
    if (!state.reports.length) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.style.padding = "16px";
      empty.textContent = "No reports in this view. Clear filters or add a resident report.";
      listEl.appendChild(empty);
      return;
    }
    state.reports.forEach((r) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "card" + (r.id === state.selectedId ? " active" : "");
      btn.addEventListener("click", () => selectReport(r.id));
      const score = r.score ? r.score.total_display : "—";
      btn.innerHTML = `
        <div class="card-top"><span class="code">${escapeText(r.public_code)}</span><span class="score">${escapeText(score)}</span></div>
        <div>${escapeText(labelCat(r.category))}</div>
        <div class="labels">${pill(r.evidence_status, "Evidence: " + evidenceLabel(r.evidence_status))}${pill(r.repair_status, "Repair: " + repairLabel(r.repair_status))}</div>
        ${r.is_synthetic ? '<div class="dup-note">Synthetic demonstration data</div>' : ""}
        ${r.inspect_flag ? '<div class="inspect">Needs inspection — unverified and scoring at least 70.</div>' : ""}
        ${r.linked_duplicates && r.linked_duplicates.length ? `<div class="dup-note">+${r.linked_duplicates.length} linked duplicate report${r.linked_duplicates.length > 1 ? "s" : ""} (history)</div>` : ""}
      `;
      listEl.appendChild(btn);
    });
  }

  function bar(label, value, cap) {
    const pct = Math.min(100, (Number(value) / cap) * 100);
    return `<div class="bar-row"><span>${escapeText(label)}</span><div class="bar"><i style="width:${pct}%"></i></div><span>${Number(value).toFixed(1)}</span></div>`;
  }

  function scenarioExplain(score) {
    if (!score.applicable_scenarios.length) return "No active scenario currently applies to this hazard.";
    const names = score.applicable_scenarios.map((s) => s.replace("_", " ")).join(", ");
    return `Applicable now: ${names}. Extra condition points stay at 15 even if more than one switch matches.`;
  }

  async function selectReport(id) {
    state.selectedId = id;
    renderList();
    renderMap();
    detailEl.innerHTML = '<p class="loading">Loading report…</p>';
    try {
      const r = await api(`/api/reports/${id}?${qs()}`);
      renderDetail(r);
    } catch (err) {
      detailEl.innerHTML = `<p class="error">${escapeText(err.message)}</p>`;
    }
  }

  function renderDetail(r) {
    const score = r.score;
    const photos = [];
    if (r.photo_filename) photos.push(`<img class="photo" alt="Before evidence" src="/media/${encodeURIComponent(r.photo_filename)}">`);
    if (r.after_photo_filename) photos.push(`<img class="photo" alt="After evidence" src="/media/${encodeURIComponent(r.after_photo_filename)}">`);
    const dups = (r.possible_duplicates || []).map((d) =>
      `${escapeText(d.public_code)} (${d.distance_m} m)`
    ).join(", ") || "None flagged within 50 m.";
    const events = (r.events || []).map((e) =>
      `<li><strong>${escapeText(e.event_type)}</strong> · ${escapeText(e.actor_role)} · ${escapeText(e.created_at)}<br>${escapeText(e.detail)}</li>`
    ).join("");
    const reviewer = state.role === "reviewer";
    const st = r.repair_status;
    const linkedHtml = !r.is_primary
      ? `<p class="dup-note">Linked duplicate of ${escapeText(r.primary_public_code || "a primary report")}. Kept as history; excluded from ranking, map pins and planning.</p>`
      : (r.linked_duplicates && r.linked_duplicates.length
        ? `<h3>Linked duplicate reports (history)</h3><ul class="history">${r.linked_duplicates.map((d) =>
          `<li><button type="button" class="linklike" data-open="${Number(d.id)}">${escapeText(d.public_code)}</button> · ${escapeText(d.created_at)}<br>${escapeText(d.description)}${d.photo_filename ? `<br><img class="photo" alt="Linked evidence ${escapeText(d.public_code)}" src="/media/${encodeURIComponent(d.photo_filename)}">` : ""}</li>`).join("")}</ul>`
        : "");
    let repairHtml = "";
    if (r.is_primary && st === "planned") {
      repairHtml = `<label>Completion note <textarea id="claim-note" placeholder="What was repaired?"></textarea></label>
        <label>After photo <input id="claim-photo" type="file" accept="image/jpeg,image/png,image/webp,image/gif"></label>
        <div class="dialog-actions"><button class="btn small" type="button" id="claim-btn">Claim repair</button></div>`;
    } else if (r.is_primary) {
      repairHtml = `<p class="field-help">Repair status: ${escapeText(repairLabel(st))}. ${st === "repair_claimed" ? "Waiting for reviewer confirmation." : st === "closed" ? "Closed and out of the active repair queue." : "A repair can be claimed once the report is in a saved plan."}</p>`;
    }
    const reviewerHtml = `
      <div>
        <h3>Reviewer controls</h3>
        <p class="field-help">Severity 1–5: how serious the defect is. Exposure 1–5: how many people meet it. Vulnerable-user context 0 / 0.5 / 1: none, moderate or high (for example a school crossing). School-access marks ContextShift. Cost is a positive INR estimate used only after verification.</p>
        <label>Severity <input id="rv-sev" type="number" min="1" max="5" value="${r.severity ?? 3}"></label>
        <label>Exposure <input id="rv-exp" type="number" min="1" max="5" value="${r.exposure ?? 3}"></label>
        <label>Vulnerable-user context
          <select id="rv-vul"><option value="0">0 none</option><option value="0.5">0.5 moderate</option><option value="1">1 high</option></select>
        </label>
        <label class="check"><input id="rv-school" type="checkbox" ${r.school_access ? "checked" : ""}> School-access hazard</label>
        <label>Estimated cost (INR) <input id="rv-cost" type="number" min="1" value="${r.estimated_cost ?? ""}"></label>
        <div class="dialog-actions" style="margin-top:8px">
          <button class="btn small" type="button" id="rv-save">Save assessment</button>
          ${["reported", "verified"].includes(st) ? '<button class="btn small primary" type="button" id="rv-verify">Verify evidence</button><button class="btn small" type="button" id="rv-dispute">Dispute evidence</button>' : ""}
        </div>
        <div id="dup-actions"></div>
        ${st === "repair_claimed" ? '<div class="dialog-actions"><button class="btn small primary" type="button" id="rv-close">Confirm closure</button></div>' : ""}
        ${["repair_claimed", "closed"].includes(st) ? '<label>Reopen reason <input id="reopen-reason" placeholder="Why is this still unresolved?"></label><button class="btn small" type="button" id="rv-reopen">Reopen (back to Planned)</button>' : ""}
      </div>`;
    detailEl.innerHTML = `
      <p class="code">${escapeText(r.public_code)} · ${escapeText(labelCat(r.category))}</p>
      ${r.is_synthetic ? "<p class='dup-note'>Synthetic demonstration data</p>" : ""}
      <p>${escapeText(r.description)}</p>
      ${photos.join("")}
      <div class="labels">${pill(r.evidence_status, "Evidence: " + evidenceLabel(r.evidence_status))}${pill(r.repair_status, "Repair: " + repairLabel(r.repair_status))}</div>
      ${r.inspect_flag ? '<p class="inspect">Unverified and scoring at least 70 — still shown for inspection. Evidence status is not urgency.</p>' : ""}
      <h3 style="margin-top:16px">Priority breakdown · ${escapeText(score.total_display)} / 100</h3>
      <div class="bars">
        ${bar("Severity", score.severity_points, 35)}
        ${bar("Exposure", score.exposure_points, 25)}
        ${bar("Vulnerability", score.vulnerability_points, 20)}
        ${bar("Conditions", score.conditions_points, 15)}
        ${bar("Age", score.age_points, 5)}
      </div>
      <p class="field-help">${escapeText(scenarioExplain(score))} ${escapeText(score.caveat)}</p>
      <div class="kv">
        <span>Location</span><span>${r.lat.toFixed(5)}, ${r.lng.toFixed(5)}</span>
        <span>School-access</span><span>${r.school_access ? "Yes" : "No"}</span>
        <span>Est. cost</span><span>${r.estimated_cost ? "INR " + Number(r.estimated_cost).toLocaleString("en-IN") : "Not set"}</span>
        <span>Unresolved days</span><span>${Number(r.days_unresolved).toFixed(1)}</span>
        <span>Possible duplicates</span><span>${dups}</span>
      </div>
      ${linkedHtml}
      <h3>Repair receipt</h3>
      <p class="field-help">Reported → Verified → Planned → Repair claimed → Closed. Evidence status is separate from repair status. A claim needs an after-photo or note; only the reviewer confirms closure or reopens a repair.</p>
      ${repairHtml}
      ${reviewer && r.is_primary ? reviewerHtml : (reviewer ? "" : '<p class="field-help">Switch to Reviewer demo mode to assess, verify, merge or close reports.</p>')}
      <h3>History</h3>
      <ul class="history">${events || "<li>No events yet.</li>"}</ul>
    `;
    detailEl.querySelectorAll("[data-open]").forEach((el) => { el.onclick = () => selectReport(Number(el.dataset.open)); });
    if ($("claim-btn")) $("claim-btn").onclick = () => postClaim(r.id);
    if (reviewer && r.is_primary) {
      $("rv-vul").value = String(r.vulnerability ?? 0);
      $("rv-save").onclick = () => postReview(r.id, {});
      if ($("rv-verify")) $("rv-verify").onclick = () => postReview(r.id, { evidence_action: "verify" });
      if ($("rv-dispute")) $("rv-dispute").onclick = () => postReview(r.id, { evidence_action: "dispute" });
      if ($("rv-close")) $("rv-close").onclick = () => act(`/api/reports/${r.id}/close`);
      if ($("rv-reopen")) $("rv-reopen").onclick = () => act(`/api/reports/${r.id}/reopen`, { reason: $("reopen-reason").value });
      const mergeWrap = $("dup-actions");
      (r.possible_duplicates || []).forEach((d) => {
        if (d.id === r.id || !d.is_primary) return;
        const b = document.createElement("button");
        b.className = "btn small";
        b.type = "button";
        b.textContent = `Confirm merge: ${d.public_code} is a duplicate of this report`;
        b.onclick = () => act(`/api/reports/${r.id}/merge`, { child_id: d.id });
        mergeWrap.appendChild(b);
      });
    }
  }

  async function postReview(id, extra) {
    const body = Object.assign({
      severity: Number($("rv-sev").value),
      exposure: Number($("rv-exp").value),
      vulnerability: Number($("rv-vul").value),
      school_access: $("rv-school").checked,
      estimated_cost: $("rv-cost").value ? Number($("rv-cost").value) : null,
      rain: state.rain,
      night: state.night,
      school_hours: state.school_hours,
    }, extra);
    try {
      await api(`/api/reports/${id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      toast("Review saved.");
      await refresh();
      selectReport(id);
    } catch (err) {
      toast(err.message);
    }
  }

  async function postClaim(id) {
    const fd = new FormData();
    fd.append("note", $("claim-note").value);
    const file = $("claim-photo").files[0];
    if (file) fd.append("after_photo", file);
    try {
      await api(`/api/reports/${id}/claim`, { method: "POST", body: fd });
      toast("Repair claimed.");
      await refresh();
      selectReport(id);
    } catch (err) {
      toast(err.message);
    }
  }

  async function act(url, body) {
    try {
      await api(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({
          rain: state.rain, night: state.night, school_hours: state.school_hours,
        }, body || {})),
      });
      toast("Updated.");
      await refresh();
      if (state.selectedId) selectReport(state.selectedId);
    } catch (err) {
      toast(err.message);
    }
  }

  function reasonCopy(reason) {
    return {
      unverified: "Unverified — not eligible for a repair bundle.",
      disputed: "Disputed evidence — not eligible.",
      resolved: "Closed — left the active repair queue.",
      duplicate: "Duplicate child — the same hazard is not counted twice.",
      missing_cost: "Missing a positive cost estimate.",
      not_selected: "Eligible, but not in this BudgetMix bundle (not necessarily individually unaffordable).",
      repair_in_progress: "Repair already claimed — left this planning round.",
    }[reason] || reason;
  }

  function renderPlan() {
    const p = state.plan;
    if (!p) {
      planEl.innerHTML = '<p class="loading">Calculating a suggested bundle…</p>';
      return;
    }
    const mix = p.budgetmix;
    const base = p.baseline;
    const selected = mix.selected.map((i) => `<li>${escapeText(i.public_code)} · ${Number(i.points).toFixed(1)} pts · INR ${Number(i.cost).toLocaleString("en-IN")}</li>`).join("");
    const baseline = base.selected.map((i) => `<li>${escapeText(i.public_code)} · ${Number(i.points).toFixed(1)} pts · INR ${Number(i.cost).toLocaleString("en-IN")}</li>`).join("");
    const excluded = p.excluded.map((e) => `<li>${escapeText(e.public_code)}: ${escapeText(reasonCopy(e.reason))}</li>`).join("");
    planEl.innerHTML = `
      <p>${escapeText(p.rounding)}</p>
      <p><strong>BudgetMix</strong> ${Number(mix.total_points).toFixed(1)} points · spend INR ${Number(mix.actual_spend).toLocaleString("en-IN")} · remaining INR ${Number(mix.remaining).toLocaleString("en-IN")}</p>
      <ul>${selected || "<li>Nothing fits this budget.</li>"}</ul>
      <h3>Priority-first baseline</h3>
      <ul>${baseline || "<li>Nothing selected.</li>"}</ul>
      <p class="field-help">${escapeText(p.note)} Brochure check: A 90 / ₹60,000, B 70 / ₹40,000, C 65 / ₹30,000 at ₹70,000 chooses B+C (135) while greedy takes A. That isolated case is covered in tests; this panel uses every currently eligible report.</p>
      <h3>Why reports are listed as excluded (${p.excluded.length})</h3>
      <ul class="excluded-list">${excluded}</ul>
      <button class="btn primary" type="button" id="save-plan">Save this plan snapshot</button>
      <div id="saved-plans"></div>
    `;
    $("save-plan").onclick = async () => {
      if (state.role !== "reviewer") { toast("Switch to Reviewer demo mode to save a plan."); return; }
      try {
        await api("/api/plan/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ budget: state.budget, rain: state.rain, night: state.night, school_hours: state.school_hours }),
        });
        toast("Plan snapshot saved. Selected verified reports moved to Planned.");
        await refresh();
      } catch (err) { toast(err.message); }
    };
    loadPlans();
  }

  async function loadPlans() {
    try {
      const data = await api("/api/plans");
      const box = $("saved-plans");
      if (!box) return;
      if (!data.plans.length) {
        box.innerHTML = "<p class='muted'>No saved snapshots yet.</p>";
        return;
      }
      box.innerHTML = "<h3>Saved snapshots</h3>" + data.plans.map((pl) => {
        const snap = pl.snapshot || {};
        const sc = [pl.rain ? "Rain" : "", pl.night ? "Night" : "", pl.school_hours ? "School Hours" : ""].filter(Boolean).join(", ") || "none";
        const rows = (snap.selected || []).map((i) => {
          const b = i.score || {};
          return `<li>${escapeText(i.public_code)} · ${Number(i.points).toFixed(1)} pts · INR ${Number(i.cost).toLocaleString("en-IN")} (S ${b.severity_display} + E ${b.exposure_display} + V ${b.vulnerability_display} + C ${b.conditions_display} + A ${b.age_display})</li>`;
        }).join("");
        return `<details class="snapshot"><summary>#${pl.id}${pl.label ? " · " + escapeText(pl.label) : ""} · INR ${Number(pl.budget).toLocaleString("en-IN")} · ${Number(pl.total_points).toFixed(1)} pts · spend INR ${Number(pl.actual_spend).toLocaleString("en-IN")}</summary>
          <p class="muted">Saved ${escapeText(pl.created_at)} · scenarios: ${escapeText(sc)} · remaining INR ${Number(pl.remaining).toLocaleString("en-IN")}</p>
          <ul>${rows || "<li>No reports selected.</li>"}</ul></details>`;
      }).join("");
    } catch (_e) { /* ignore */ }
  }

  async function refresh() {
    listEl.innerHTML = '<p class="loading" style="padding:16px">Loading reports…</p>';
    try {
      const data = await api(`/api/reports?${qs()}`);
      state.reports = data.reports;
      renderList();
      renderMap();
      const plan = await api("/api/plan/suggest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ budget: state.budget, rain: state.rain, night: state.night, school_hours: state.school_hours }),
      });
      state.plan = plan;
      renderPlan();
    } catch (err) {
      listEl.innerHTML = `<p class="error" style="padding:16px">${escapeText(err.message)}</p>`;
      planEl.innerHTML = `<p class="error">${escapeText(err.message)}</p>`;
    }
  }

  function bind() {
    const err0 = $("form-error");
    document.querySelectorAll("input[name=role]").forEach((el) => {
      el.addEventListener("change", () => { state.role = el.value; if (state.selectedId) selectReport(state.selectedId); });
    });
    ["rain", "night", "school"].forEach((id) => {
      $(id).addEventListener("change", () => {
        state.rain = $("rain").checked;
        state.night = $("night").checked;
        state.school_hours = $("school").checked;
        refresh().then(() => { if (state.selectedId) selectReport(state.selectedId); });
      });
    });
    const syncBudget = (value) => {
      state.budget = Math.max(0, Number(value) || 0);
      $("budget").value = state.budget;
      $("budget-range").value = Math.min(150000, state.budget);
      refresh();
    };
    $("budget").addEventListener("change", () => syncBudget($("budget").value));
    $("budget-range").addEventListener("input", () => syncBudget($("budget-range").value));
    ["filter-category", "filter-evidence", "filter-repair"].forEach((id) => {
      $(id).addEventListener("change", refresh);
    });
    $("open-report").onclick = () => {
      err0.hidden = true;
      $("report-dialog").showModal();
    };
    $("cancel-report").onclick = () => $("report-dialog").close();
    $("report-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const err = $("form-error");
      err.hidden = true;
      const fd = new FormData($("report-form"));
      const submit = $("report-form").querySelector("button[type=submit]");
      submit.disabled = true;
      try {
        const created = await api("/api/reports", { method: "POST", body: fd });
        $("report-dialog").close();
        $("report-form").reset();
        toast(created.possible_duplicates && created.possible_duplicates.length
          ? "Report saved. Nearby same-category pins were flagged for reviewer merge."
          : "Report saved as unverified.");
        await refresh();
        selectReport(created.id);
      } catch (ex) {
        err.hidden = false;
        err.textContent = ex.message;
      } finally {
        submit.disabled = false;
      }
    });
  }

  window.addEventListener("load", () => {
    initMap();
    bindSchematicPlacement();
    bind();
    refresh();
    setTimeout(() => {
      if (state.tileErrors === 0) {
        fetch("https://tile.openstreetmap.org/0/0/0.png", { mode: "no-cors" }).catch(() => {
          showSchematic("The map tile network could not be reached.");
        });
      }
    }, 4000);
  });
})();
