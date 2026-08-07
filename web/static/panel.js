"use strict";

const statusEl = () => document.getElementById("status");

function flash(message, ok) {
  const el = statusEl();
  if (!el) return;
  el.textContent = message;
  el.className = "status show " + (ok ? "ok" : "err");
  setTimeout(() => { el.className = "status"; }, 2500);
}

async function post(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data = {};
  try { data = await resp.json(); } catch (_) { /* ignore */ }
  return { ok: resp.ok && data.ok, error: data.error };
}

// --- Dashboard: process-wide cog load/reload/unload ---
document.querySelectorAll(".cogbtns button").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const action = btn.dataset.action;
    const cog = btn.dataset.cog;
    btn.disabled = true;
    const res = await post("/api/cog", { action, cog });
    btn.disabled = false;
    if (res.ok) {
      flash(`${action} ${cog} ✓`, true);
      setTimeout(() => location.reload(), 600);
    } else {
      flash(res.error || `Failed to ${action} ${cog}`, false);
    }
  });
});

// --- Guild page: per-cog enable toggle ---
document.querySelectorAll(".cogcard").forEach((card) => {
  const guildId = card.closest("[data-guild]").dataset.guild;
  const cog = card.dataset.cog;

  const toggle = card.querySelector(".cogtoggle");
  if (toggle) {
    toggle.addEventListener("change", async () => {
      const res = await post(`/api/guild/${guildId}/cog`, { cog, enabled: toggle.checked });
      flash(res.ok ? `${cog} ${toggle.checked ? "enabled" : "disabled"} ✓` : (res.error || "Failed"), res.ok);
      if (!res.ok) toggle.checked = !toggle.checked;
    });
  }

  // --- Guild page: per-listener feature toggles ---
  card.querySelectorAll(".featrow .feattoggle").forEach((toggle) => {
    const feature = toggle.closest(".featrow").dataset.feature;
    toggle.addEventListener("change", async () => {
      const res = await post(`/api/guild/${guildId}/feature`, { feature, enabled: toggle.checked });
      if (res.ok) {
        flash(`${feature} ${toggle.checked ? "on" : "off"} ✓`, true);
      } else {
        flash(res.error || "Failed", false);
        toggle.checked = !toggle.checked;
      }
    });
  });

  // --- Guild page: per-server parameters ---
  card.querySelectorAll(".param").forEach((el) => {
    const key = el.dataset.key;
    const type = el.dataset.type;
    const readValue = () => {
      if (type === "bool") return el.checked;
      if (type === "list_role" || type === "list_channel") return Array.from(el.selectedOptions).map((o) => Number(o.value));
      if (type === "int" || type === "float" || type === "role" || type === "channel") return Number(el.value);
      return el.value; // str, secret, text, list_str, list_int — server coerces
    };
    el.addEventListener("change", async () => {
      // Never overwrite a stored secret with an empty field.
      if (type === "secret" && !el.value) return;
      const res = await post(`/api/guild/${guildId}/param`, { key, value: readValue() });
      flash(res.ok ? `${key} saved ✓` : (res.error || "Failed"), res.ok);
      if (type === "secret" && res.ok) { el.value = ""; el.placeholder = "•••••• set (blank keeps it)"; }
    });
  });

    // --- Guild page: searchable chip multi-selects (list_role / list_channel) ---
  card.querySelectorAll(".multiselect").forEach((ms) => {
    const key = ms.dataset.key;
    const chips = ms.querySelector(".ms-chips");
    const search = ms.querySelector(".ms-search");
    const opts = Array.from(ms.querySelectorAll(".ms-opt"));
    const selected = new Set(opts.filter((o) => o.dataset.selected === "1").map((o) => Number(o.dataset.id)));

    const save = async () => {
      const res = await post(`/api/guild/${guildId}/param`, { key, value: [...selected] });
      flash(res.ok ? `${key} saved ✓` : (res.error || "Failed"), res.ok);
    };
    const applyFilter = () => {
      const q = search.value.trim().toLowerCase();
      opts.forEach((o) => {
        const hidden = selected.has(Number(o.dataset.id)) || (q && !o.dataset.name.toLowerCase().includes(q));
        o.style.display = hidden ? "none" : "";
      });
    };
    const render = () => {
      chips.innerHTML = "";
      opts.forEach((o) => {
        if (!selected.has(Number(o.dataset.id))) return;
        const chip = document.createElement("span");
        chip.className = "ms-chip";
        chip.textContent = o.dataset.name + " ";
        const x = document.createElement("b");
        x.textContent = "×";
        x.addEventListener("click", () => { selected.delete(Number(o.dataset.id)); render(); save(); });
        chip.appendChild(x);
        chips.appendChild(chip);
      });
      applyFilter();
    };
    opts.forEach((o) => o.addEventListener("click", () => {
      selected.add(Number(o.dataset.id));
      search.value = "";
      render();
      save();
    }));
    search.addEventListener("input", applyFilter);
    render();
  });

  // --- Guild page: per-command visibility level ---
  card.querySelectorAll("select.level").forEach((sel) => {
    let previous = sel.value;
    sel.addEventListener("change", async () => {
      const command = sel.dataset.command;
      const res = await post(`/api/guild/${guildId}/command`, { command, level: sel.value });
      if (res.ok) {
        flash(`${command} → ${sel.value} ✓`, true);
        previous = sel.value;
      } else {
        flash(res.error || "Failed", false);
        sel.value = previous;
      }
    });
  });
});

// --- Guild page: category master toggle (turns all member cogs on/off) ---
document.querySelectorAll(".cattoggle").forEach((toggle) => {
  const guildEl = toggle.closest("[data-guild]");
  if (!guildEl) return;
  const guildId = guildEl.dataset.guild;
  const category = toggle.dataset.category;
  if (toggle.dataset.state === "mixed") toggle.indeterminate = true;

  toggle.addEventListener("change", async () => {
    const enabled = toggle.checked;
    const res = await post(`/api/guild/${guildId}/category`, { category, enabled });
    if (res.ok) {
      flash(`${category} ${enabled ? "enabled" : "disabled"} ✓`, true);
      toggle.indeterminate = false;
      // Reflect on the member cog toggles inside this category.
      toggle.closest(".catcard").querySelectorAll(".cogtoggle").forEach((c) => { c.checked = enabled; });
    } else {
      flash(res.error || "Failed", false);
      toggle.checked = !toggle.checked;
    }
  });
});

// --- Guild page: sidebar convenience (expand/collapse all + cog filter) ---
const _expandAll = document.getElementById("expandall");
const _collapseAll = document.getElementById("collapseall");
if (_expandAll) _expandAll.addEventListener("click", () =>
  document.querySelectorAll(".content .catbody").forEach((d) => (d.open = true)));
if (_collapseAll) _collapseAll.addEventListener("click", () =>
  document.querySelectorAll(".content .catbody").forEach((d) => (d.open = false)));

const _cogFilter = document.getElementById("cogfilter");
if (_cogFilter) {
  _cogFilter.addEventListener("input", () => {
    const q = _cogFilter.value.trim().toLowerCase();
    document.querySelectorAll(".content .cogcard").forEach((card) => {
      card.style.display = !q || card.dataset.cog.toLowerCase().includes(q) ? "" : "none";
    });
    document.querySelectorAll(".cognav .navcat").forEach((navcat) => {
      let any = false;
      navcat.querySelectorAll(".navcog").forEach((row) => {
        const m = !q || row.dataset.cog.toLowerCase().includes(q);
        row.style.display = m ? "" : "none";
        if (m) any = true;
      });
      navcat.style.display = any ? "" : "none";
    });
    document.querySelectorAll(".content .catcard").forEach((cat) => {
      const visible = [...cat.querySelectorAll(".cogcard")].some((c) => c.style.display !== "none");
      cat.style.display = visible ? "" : "none";
      if (q && visible) { const b = cat.querySelector(".catbody"); if (b) b.open = true; }
    });
  });
}

// --- Guild sidebar: per-cog Reload / Unload↔Load (process-wide cog lifecycle) ---
document.querySelectorAll(".navbtns button").forEach((btn) => {
  btn.addEventListener("click", async (event) => {
    event.preventDefault();
    const action = btn.dataset.action;
    const cog = btn.dataset.cog;
    btn.disabled = true;
    const res = await post("/api/cog", { action, cog });
    btn.disabled = false;
    if (!res.ok) {
      flash(res.error || `Failed to ${action} ${cog}`, false);
      return;
    }
    flash(`${action} ${cog} ✓`, true);
    // Unload↔Load toggles; Reload stays Reload.
    if (action === "unload") { btn.dataset.action = "load"; btn.textContent = "Load"; btn.title = "Load"; }
    else if (action === "load") { btn.dataset.action = "unload"; btn.textContent = "Unload"; btn.title = "Unload"; }
  });
});

// A command's card border reflects its level live when the selector changes.
document.querySelectorAll(".cmdcard select.level").forEach((sel) => {
  sel.addEventListener("change", () => {
    const card = sel.closest(".cmdcard");
    card.classList.remove("lvl-visible", "lvl-admin", "lvl-owner");
    card.classList.add("lvl-" + sel.value);
  });
});

// --- Strings page: edit / reset user-facing strings ---
document.querySelectorAll("#langlist .langrow").forEach((row) => {
  const key = row.dataset.key;
  const isList = row.dataset.list === "1";
  const ta = row.querySelector("textarea");

  row.querySelector('button[data-do="save"]').addEventListener("click", async () => {
    const res = await post("/api/lang", { key, value: ta.value, is_list: isList });
    if (res.ok) {
      flash(`${key} saved ✓`, true);
      row.classList.add("saved");
    } else {
      flash(res.error || "Failed", false);
    }
  });

  row.querySelector('button[data-do="reset"]').addEventListener("click", async () => {
    const res = await post("/api/lang", { key, action: "reset" });
    if (res.ok) {
      flash(`${key} reset ✓`, true);
      setTimeout(() => location.reload(), 500);
    } else {
      flash(res.error || "Failed", false);
    }
  });
});

// --- Strings page: live filter ---
const langSearch = document.getElementById("langsearch");
if (langSearch) {
  langSearch.addEventListener("input", () => {
    const q = langSearch.value.trim().toLowerCase();
    document.querySelectorAll("#langlist .group").forEach((group) => {
      let anyVisible = false;
      group.querySelectorAll(".langrow").forEach((row) => {
        const match = !q || row.dataset.search.includes(q);
        row.style.display = match ? "" : "none";
        if (match) anyVisible = true;
      });
      group.style.display = anyVisible ? "" : "none";
      if (q && anyVisible) group.open = true;
    });
  });
}
