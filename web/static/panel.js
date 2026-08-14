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
  // `value` comes back from endpoints that resolve one (e.g. a reset to default).
  return { ok: resp.ok && data.ok, error: data.error, value: data.value };
}

// Searchable chip multi-select (list_role / list_channel). `save` receives the
// selected ids; used by both the cog parameters and the server settings page.
function bindMultiSelect(ms, save) {
  const chips = ms.querySelector(".ms-chips");
  const search = ms.querySelector(".ms-search");
  const opts = Array.from(ms.querySelectorAll(".ms-opt"));
  const selected = new Set(opts.filter((o) => o.dataset.selected === "1").map((o) => Number(o.dataset.id)));

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
      x.addEventListener("click", () => { selected.delete(Number(o.dataset.id)); render(); save([...selected]); });
      chip.appendChild(x);
      chips.appendChild(chip);
    });
    applyFilter();
  };
  opts.forEach((o) => o.addEventListener("click", () => {
    selected.add(Number(o.dataset.id));
    search.value = "";
    render();
    save([...selected]);
  }));
  search.addEventListener("input", applyFilter);
  render();
  return { set: (ids) => { selected.clear(); ids.forEach((id) => selected.add(Number(id))); render(); } };
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
    bindMultiSelect(ms, async (ids) => {
      const res = await post(`/api/guild/${guildId}/param`, { key, value: ids });
      flash(res.ok ? `${key} saved ✓` : (res.error || "Failed"), res.ok);
    });
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

// --- Settings page: guild settings + the log cog's own destinations ---
const _settingsPage = document.querySelector(".settingspage");
if (_settingsPage) {
  const guildId = _settingsPage.dataset.guild;
  const saveSetting = async (key, value) => {
    const res = await post(`/api/guild/${guildId}/setting`, { key, value });
    flash(res.ok ? `${key} saved ✓` : (res.error || "Failed"), res.ok);
    return res;
  };
  const markSet = (key, isSet) => {
    const row = _settingsPage.querySelector(`.setrow[data-key="${CSS.escape(key)}"]`);
    if (!row) return;
    const head = row.querySelector("b");
    const existing = row.querySelector("span.on");
    if (isSet && !existing) head.insertAdjacentHTML("afterend", ' <span class="on">set</span>');
    if (!isSet && existing) existing.remove();
  };

  _settingsPage.querySelectorAll(".setting").forEach((el) => {
    if (el.classList.contains("multiselect")) {
      const key = el.dataset.key;
      el._widget = bindMultiSelect(el, async (ids) => {
        const res = await saveSetting(key, ids);
        if (res.ok) markSet(key, true);
      });
      return;
    }
    el.addEventListener("change", async () => {
      const res = await saveSetting(el.dataset.key, el.value);
      if (res.ok) markSet(el.dataset.key, true);
    });
  });

  // Reset restores the built-in default and re-renders the control with it.
  _settingsPage.querySelectorAll(".setreset").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const key = btn.dataset.key;
      const res = await post(`/api/guild/${guildId}/setting`, { key, action: "reset" });
      if (!res.ok) { flash(res.error || "Failed", false); return; }
      flash(`${key} reset to default ✓`, true);
      markSet(key, false);
      const control = _settingsPage.querySelector(`.setrow[data-key="${CSS.escape(key)}"] .setting`);
      if (!control) return;
      if (control._widget) control._widget.set(res.value || []);
      else control.value = res.value === null || res.value === undefined ? "" : res.value;
    });
  });

  _settingsPage.querySelectorAll(".auditchannel").forEach((sel) => {
    sel.addEventListener("change", async () => {
      const res = await post(`/api/guild/${guildId}/setting`, { key: sel.dataset.key, value: sel.value });
      flash(res.ok ? "log channel saved ✓" : (res.error || "Failed"), res.ok);
    });
  });

  const setSearch = document.getElementById("setsearch");
  if (setSearch) {
    setSearch.addEventListener("input", () => {
      const q = setSearch.value.trim().toLowerCase();
      _settingsPage.querySelectorAll(".setrow").forEach((row) => {
        row.style.display = !q || row.textContent.toLowerCase().includes(q) ? "" : "none";
      });
      _settingsPage.querySelectorAll("details.group").forEach((group) => {
        const anyVisible = Array.from(group.querySelectorAll(".setrow")).some((r) => r.style.display !== "none");
        group.style.display = anyVisible ? "" : "none";
        if (q) group.open = true;
      });
    });
  }
}

// --- Events page: the "when X happens, do Y" rule constructor ---
const _eventsPage = document.querySelector(".eventspage");
if (_eventsPage) {
  const guildId = _eventsPage.dataset.guild;
  const api = (body) => post(`/api/guild/${guildId}/event-rule`, body);

  const readIds = (text) => (text.match(/\d{5,}/g) || []).map(Number);

  const bindRule = (card) => {
    const id = card.dataset.rule;
    let roleIds = null;
    const ms = card.querySelector(".ruleroles");
    if (ms) {
      const widget = bindMultiSelect(ms, (ids) => { roleIds = ids; });
      roleIds = null; // only send roles once the user actually touches them
      card._roles = widget;
    }
    const payload = () => {
      const body = {
        action: "update",
        id,
        name: card.querySelector(".rulename").value,
        event: card.querySelector(".ruleevent").value,
        channel_id: Number(card.querySelector(".rulechannel").value || 0),
        message: card.querySelector(".rulemessage").value,
        ping_user_ids: readIds(card.querySelector(".ruleusers").value),
      };
      if (roleIds !== null) body.ping_role_ids = roleIds;
      return body;
    };

    card.querySelector(".rulesave").addEventListener("click", async () => {
      const res = await api(payload());
      flash(res.ok ? "rule saved ✓" : (res.error || "Failed"), res.ok);
    });
    card.querySelector(".ruletoggle").addEventListener("change", async (event) => {
      const enabled = event.target.checked;
      const res = await api({ action: "update", id, enabled });
      flash(res.ok ? `rule ${enabled ? "enabled" : "disabled"} ✓` : (res.error || "Failed"), res.ok);
      if (res.ok) card.classList.toggle("off", !enabled);
      else event.target.checked = !enabled;
    });
    card.querySelector(".ruledelete").addEventListener("click", async () => {
      if (!confirm("Delete this rule?")) return;
      const res = await api({ action: "delete", id });
      if (res.ok) { card.remove(); flash("rule deleted ✓", true); }
      else flash(res.error || "Failed", false);
    });
  };

  _eventsPage.querySelectorAll(".rulecard").forEach(bindRule);

  document.getElementById("addrule").addEventListener("click", async () => {
    const res = await api({ action: "create", event: "member_join", name: "New rule", message: "" });
    if (!res.ok) { flash(res.error || "Failed", false); return; }
    location.reload(); // simplest way to render a fresh card with the full pickers
  });
}

// --- Guild page: panel access grants (owner-only card) ---
const _accessCard = document.getElementById("cat-access");
if (_accessCard) {
  const guildId = _accessCard.closest("[data-guild]").dataset.guild;
  const kind = document.getElementById("grantkind");
  const roleSel = document.getElementById("grantrole");
  const userInput = document.getElementById("grantuser");

  const syncKind = () => {
    const isRole = kind.value === "role";
    roleSel.style.display = isRole ? "" : "none";
    userInput.style.display = isRole ? "none" : "";
  };
  kind.addEventListener("change", syncKind);
  syncKind();

  document.getElementById("grantadd").addEventListener("click", async () => {
    const isRole = kind.value === "role";
    const target = isRole ? roleSel.value : (userInput.value.match(/\d{5,}/) || [""])[0];
    if (!target) { flash("Enter a user id", false); return; }
    const res = await post(`/api/guild/${guildId}/access`, {
      kind: kind.value, target_id: target, scope: document.getElementById("grantscope").value,
    });
    if (res.ok) { flash("access granted ✓", true); setTimeout(() => location.reload(), 500); }
    else flash(res.error || "Failed", false);
  });

  _accessCard.querySelectorAll(".grantdel").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const res = await post(`/api/guild/${guildId}/access`, {
        action: "remove", kind: btn.dataset.kind, target_id: btn.dataset.target,
      });
      if (res.ok) { flash("access removed ✓", true); btn.closest("tr").remove(); }
      else flash(res.error || "Failed", false);
    });
  });
}
