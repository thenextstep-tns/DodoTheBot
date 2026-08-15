"use strict";

// Discord ids are 64-bit and exceed JavaScript's safe integer range, so they
// are kept as STRINGS everywhere in this file. Number("1418516519297912852")
// silently becomes ...800 — a different, non-existent id. Python parses the
// strings back to ints server-side.

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
  // Pass the whole payload through: endpoints also return `value`, `rows`,
  // `summary`, … and dropping them silently turns a full answer into a blank one.
  return { ...data, ok: resp.ok && data.ok, error: data.error };
}

// Searchable chip multi-select (list_role / list_channel). `save` receives the
// selected ids; used by both the cog parameters and the server settings page.
function bindMultiSelect(ms, save) {
  const chips = ms.querySelector(".ms-chips");
  const search = ms.querySelector(".ms-search");
  const opts = Array.from(ms.querySelectorAll(".ms-opt"));
  const selected = new Set(opts.filter((o) => o.dataset.selected === "1").map((o) => o.dataset.id));

  const applyFilter = () => {
    const q = search.value.trim().toLowerCase();
    opts.forEach((o) => {
      const hidden = selected.has(o.dataset.id) || (q && !o.dataset.name.toLowerCase().includes(q));
      o.style.display = hidden ? "none" : "";
    });
  };
  const render = () => {
    chips.innerHTML = "";
    opts.forEach((o) => {
      if (!selected.has(o.dataset.id)) return;
      const chip = document.createElement("span");
      chip.className = "ms-chip";
      chip.textContent = o.dataset.name + " ";
      const x = document.createElement("b");
      x.textContent = "×";
      x.addEventListener("click", () => { selected.delete(o.dataset.id); render(); save([...selected]); });
      chip.appendChild(x);
      chips.appendChild(chip);
    });
    applyFilter();
  };
  opts.forEach((o) => o.addEventListener("click", () => {
    selected.add(o.dataset.id);
    search.value = "";
    render();
    save([...selected]);
  }));
  search.addEventListener("input", applyFilter);
  render();
  return { set: (ids) => { selected.clear(); ids.forEach((id) => selected.add(String(id))); render(); } };
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
      if (type === "list_role" || type === "list_channel") return Array.from(el.selectedOptions).map((o) => o.value);
      if (type === "role" || type === "channel") return el.value;          // id: string
      if (type === "int" || type === "float") return Number(el.value);
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

  const readIds = (text) => (text.match(/\d{5,}/g) || []);

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
        channel_id: card.querySelector(".rulechannel").value || "0",
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

// --- Guild page: set every command in a cog to one level ---
document.querySelectorAll("select.coglevel").forEach((sel) => {
  const card = sel.closest(".cogcard");
  const guildId = card.closest("[data-guild]").dataset.guild;
  const cog = card.dataset.cog;
  let previous = sel.value;
  sel.addEventListener("change", async () => {
    if (sel.value === "custom") { sel.value = previous; return; }  // derived, not settable
    const res = await post(`/api/guild/${guildId}/cog-level`, { cog, level: sel.value });
    if (res.ok) {
      flash(`${cog} → all ${sel.value} ✓`, true);
      previous = sel.value;
      // Every command card in this cog now shows the new level.
      card.querySelectorAll("select.level").forEach((cmd) => {
        if (cmd.querySelector(`option[value="${sel.value}"]`)) cmd.value = sel.value;
      });
      const customOpt = sel.querySelector('option[value="custom"]');
      if (customOpt) customOpt.remove();
    } else {
      flash(res.error || "Failed", false);
      sel.value = previous;
    }
  });
});

// --- Tribes page: recursive condition builder ---
const _tribesPage = document.querySelector(".tribespage");
if (_tribesPage) {
  const guildId = _tribesPage.dataset.guild;
  const roleOpts = JSON.parse(document.getElementById("tribe-role-options").textContent || "[]");
  const chanOpts = JSON.parse(document.getElementById("tribe-channel-options").textContent || "[]");

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const picker = (options, selected, multiple) => {
    const sel = el("select", "cond-ids");
    if (multiple) sel.multiple = true;
    options.forEach((o) => {
      const opt = el("option", null, o.name);
      opt.value = o.id;
      if ((selected || []).map(String).includes(String(o.id))) opt.selected = true;
      sel.appendChild(opt);
    });
    if (multiple) sel.size = Math.min(6, Math.max(3, options.length));
    return sel;
  };

  // Render one condition; the element carries read(), which rebuilds its JSON.
  function renderNode(node, onRemove) {
    node = node || { type: "has_role", role_ids: [], mode: "all" };
    const box = el("div", "condnode");
    const head = el("div", "condhead");
    const kind = el("select", "condtype");
    [["all", "ALL of"], ["any", "ANY of"], ["not", "NONE of"], ["has_role", "Has role(s)"],
     ["member_for", "On server for ≥ days"], ["account_for", "Account older than days"],
     ["metric_min", "At least N messages/threads"], ["metric_top", "Top N by messages/threads"]]
      .forEach(([v, label]) => { const o = el("option", null, label); o.value = v; kind.appendChild(o); });
    kind.value = node.type;
    head.appendChild(kind);
    if (onRemove) {
      const del = el("button", "ghost condremove", "×");
      del.addEventListener("click", onRemove);
      head.appendChild(del);
    }
    box.appendChild(head);
    const body = el("div", "condbody");
    box.appendChild(body);

    const build = () => {
      body.innerHTML = "";
      const type = kind.value;
      if (["all", "any", "not"].includes(type)) {
        const kids = el("div", "condkids");
        body.appendChild(kids);
        const addChild = (child) => {
          const wrap = renderNode(child, () => wrap.remove());
          kids.appendChild(wrap);
        };
        (node.children || []).forEach(addChild);
        const add = el("button", "ghost", "+ condition");
        add.addEventListener("click", () => addChild(null));
        body.appendChild(add);
        box.read = () => ({ type: type, children: Array.from(kids.children).map((c) => c.read()) });
      } else if (type === "has_role") {
        const mode = el("select", "condmode");
        [["all", "has ALL of"], ["any", "has ANY of"]].forEach(([v, l]) => {
          const o = el("option", null, l); o.value = v; mode.appendChild(o);
        });
        mode.value = node.mode || "all";
        const ids = picker(roleOpts, node.role_ids, true);
        body.append(mode, ids);
        box.read = () => ({ type: type, mode: mode.value,
                            role_ids: Array.from(ids.selectedOptions).map((o) => o.value) });
      } else if (type === "member_for" || type === "account_for") {
        const days = el("input", "conddays");
        days.type = "number"; days.min = "0"; days.value = node.days != null ? node.days : 30;
        body.append(days, el("span", "muted small", " days"));
        box.read = () => ({ type: type, days: Number(days.value || 0) });
      } else {
        const metric = el("select", "condmetric");
        [["messages", "messages sent"], ["threads", "threads created"]].forEach(([v, l]) => {
          const o = el("option", null, l); o.value = v; metric.appendChild(o);
        });
        metric.value = node.metric || "messages";
        const num = el("input", "condnum");
        num.type = "number"; num.min = "1";
        num.value = type === "metric_min" ? (node.min != null ? node.min : 100)
                                          : (node.n != null ? node.n : 10);
        const chans = picker(chanOpts, node.channel_ids, true);
        const hint = el("span", "muted small", " (no channels selected = whole server)");
        body.append(num, metric, chans, hint);
        box.read = () => {
          const out = { type: type, metric: metric.value,
                        channel_ids: Array.from(chans.selectedOptions).map((o) => o.value) };
          if (type === "metric_min") { out.min = Number(num.value || 0); }
          else { out.n = Number(num.value || 1); }
          return out;
        };
      }
    };
    kind.addEventListener("change", () => { node = { type: kind.value }; build(); });
    build();
    return box;
  }

  _tribesPage.querySelectorAll(".rulebuilder").forEach((holder) => {
    const condition = JSON.parse(holder.dataset.condition || '{"type":"all","children":[]}');
    const root = renderNode(condition, null);
    holder.appendChild(root);
    holder._read = () => root.read();
  });

  const bindTribe = (card) => {
    const id = card.dataset.tribe;
    let roleIds = null;
    const ms = card.querySelector(".triberoles");
    if (ms) card._roles = bindMultiSelect(ms, (ids) => { roleIds = ids; });
    const payload = () => {
      const mode = card._mode ? card._mode() : "condition";
      const body = {
        action: "update", id: id, mode: mode,
        name: card.querySelector(".tribename").value,
        remove_when_unmatched: card.querySelector(".triberemove").value === "1",
      };
      if (mode === "points" && card._points) {
        const pts = card._points();
        body.sources = pts.sources; body.tiers = pts.tiers; body.exclusive = pts.exclusive;
      } else {
        body.condition = card.querySelector(".rulebuilder")._read();
      }
      if (roleIds !== null) body.role_ids = roleIds;
      return body;
    };
    card.querySelector(".tribesave").addEventListener("click", async () => {
      const res = await post(`/api/guild/${guildId}/tribe`, payload());
      flash(res.ok ? "tribe saved ✓" : (res.error || "Failed"), res.ok);
      if (res.ok) setTimeout(() => location.reload(), 600);
    });
    card.querySelector(".tribetoggle").addEventListener("change", async (e) => {
      const res = await post(`/api/guild/${guildId}/tribe`,
                             { action: "update", id: id, enabled: e.target.checked });
      flash(res.ok ? "saved ✓" : (res.error || "Failed"), res.ok);
      if (res.ok) { card.classList.toggle("off", !e.target.checked); }
      else { e.target.checked = !e.target.checked; }
    });
    card.querySelector(".tribedelete").addEventListener("click", async () => {
      if (!confirm("Delete this tribe? Members keep any roles already granted.")) return;
      const res = await post(`/api/guild/${guildId}/tribe`, { action: "delete", id: id });
      if (res.ok) { card.remove(); flash("tribe deleted ✓", true); }
      else { flash(res.error || "Failed", false); }
    });
  };
  _tribesPage.querySelectorAll(".tribecard").forEach(bindTribe);

  document.getElementById("addtribe").addEventListener("click", async () => {
    const res = await post(`/api/guild/${guildId}/tribe`, { action: "create", name: "New tribe" });
    if (res.ok) { location.reload(); } else { flash(res.error || "Failed", false); }
  });
  document.getElementById("runtribes").addEventListener("click", async (e) => {
    e.target.disabled = true;
    flash("running sweep…", true);
    const res = await post(`/api/guild/${guildId}/tribe`, { action: "run" });
    e.target.disabled = false;
    if (res.ok) { flash("sweep finished ✓", true); setTimeout(() => location.reload(), 800); }
    else { flash(res.error || "Failed", false); }
  });
}

// --- Tribes page: points constructor (role -> points, and the rank ladder) ---
document.querySelectorAll(".pointsbuilder").forEach((box) => {
  const card = box.closest(".tribecard");
  const roleOptions = JSON.parse(document.getElementById("tribe-role-options").textContent || "[]");
  const sourceRows = box.querySelector(".sourcerows");
  const tierRows = box.querySelector(".tierrows");

  const roleSelect = (selected) => {
    const sel = document.createElement("select");
    sel.className = "pt-role";
    roleOptions.forEach((o) => {
      const opt = document.createElement("option");
      opt.value = o.id; opt.textContent = o.name;
      if (String(selected) === String(o.id)) opt.selected = true;
      sel.appendChild(opt);
    });
    return sel;
  };
  const numberInput = (cls, value, placeholder) => {
    const input = document.createElement("input");
    input.type = "number"; input.className = cls;
    input.value = value; input.placeholder = placeholder || "";
    return input;
  };
  const removeButton = (row) => {
    const btn = document.createElement("button");
    btn.className = "ghost pt-remove"; btn.textContent = "×";
    btn.addEventListener("click", () => row.remove());
    return btn;
  };

  const addSource = (src) => {
    src = src || {};
    const row = document.createElement("div");
    row.className = "ptrow";
    row.append(roleSelect(src.role_id), numberInput("pt-points", src.points != null ? src.points : 10));
    const label = document.createElement("span");
    label.className = "muted small"; label.textContent = "points";
    row.append(label, removeButton(row));
    sourceRows.appendChild(row);
  };

  const addTier = (tier) => {
    tier = tier || {};
    const row = document.createElement("div");
    row.className = "ptrow";
    const name = document.createElement("input");
    name.className = "pt-name"; name.value = tier.name || ""; name.placeholder = "Rank name";
    const at = document.createElement("span");
    at.className = "muted small"; at.textContent = "at";
    const pts = numberInput("pt-min", tier.min_points != null ? tier.min_points : 0);
    const grants = document.createElement("span");
    grants.className = "muted small"; grants.textContent = "pts →";
    row.append(name, at, pts, grants, roleSelect(tier.role_id), removeButton(row));
    tierRows.appendChild(row);
  };

  (JSON.parse(box.dataset.sources || "[]")).forEach(addSource);
  (JSON.parse(box.dataset.tiers || "[]")).forEach(addTier);
  box.querySelector(".addsource").addEventListener("click", () => addSource(null));
  box.querySelector(".addtier").addEventListener("click", () => addTier(null));

  box._read = () => ({
    sources: Array.from(sourceRows.children).map((row) => ({
      kind: "role",
      role_id: row.querySelector(".pt-role").value,
      points: Number(row.querySelector(".pt-points").value || 0),
    })),
    tiers: Array.from(tierRows.children).map((row) => ({
      name: row.querySelector(".pt-name").value,
      min_points: Number(row.querySelector(".pt-min").value || 0),
      role_id: row.querySelector(".pt-role").value,
    })),
    exclusive: box.querySelector(".tribeexclusive").checked,
  });

  // Mode switch shows one builder or the other; the save handler reads whichever is active.
  card.querySelectorAll('.modeswitch input[type="radio"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      const points = radio.value === "points" && radio.checked;
      box.hidden = !points;
      card.querySelector(".rulebuilder").hidden = points;
    });
  });
  card._mode = () => (card.querySelector('.modeswitch input:checked') || {}).value || "condition";
  card._points = () => box._read();
});

// --- Trial ranking page ---
const _trialsPage = document.querySelector(".trialspage");
if (_trialsPage) {
  const guildId = _trialsPage.dataset.guild;

  // Type-to-find inside each section.
  _trialsPage.querySelectorAll(".rolefilter").forEach((box) => {
    const target = document.getElementById(box.dataset.target);
    box.addEventListener("input", () => {
      const q = box.value.trim().toLowerCase();
      target.querySelectorAll(".scorerow").forEach((row) => {
        row.style.display = !q || (row.dataset.search || "").includes(q) ? "" : "none";
      });
    });
  });

  // Flag a clear/achievement the moment it gets a value (or loses one).
  _trialsPage.querySelectorAll(".rolepoints").forEach((input) => {
    input.addEventListener("input", () => {
      const row = input.closest(".scorerow");
      const has = Number(input.value) !== 0 && input.value !== "";
      row.classList.toggle("unpriced", !has);
      const flag = row.querySelector(".nopoints");
      if (flag) flag.style.display = has ? "none" : "";
    });
  });


  const readSetup = () => {
    const points = {};
    _trialsPage.querySelectorAll(".rolepoints").forEach((input) => {
      const value = Number(input.value);
      if (input.value !== "" && value !== 0) points[input.dataset.role] = value;
    });
    const ranks = [];
    _trialsPage.querySelectorAll(".ladderrow").forEach((row) => {
      const roleId = (row.querySelector(".rolepick-id") || {}).value || "0";
      if (roleId === "0") return;  // this rank is left empty
      ranks.push({ tier: row.dataset.tier, role_id: roleId,
                   min_points: Number(row.querySelector(".rankmin").value || 0) });
    });
    return {
      action: "save", points: points, ranks: ranks,
      trials: window.readTrialMap ? window.readTrialMap() : [],
      enabled: document.getElementById("trialsenabled").checked,
      exclusive: document.getElementById("trialsexclusive").checked,
    };
  };

  document.getElementById("trialsave").addEventListener("click", async () => {
    const res = await post(`/api/guild/${guildId}/trials`, readSetup());
    flash(res.ok ? "trial ranking saved ✓" : (res.error || "Failed"), res.ok);
  });

}

// --- Trial ranking: balance sandbox (dry runs) + push to live ---
const _sandbox = document.querySelector(".trialspage .sandbox");
if (_sandbox) {
  const guildId = document.querySelector(".trialspage").dataset.guild;
  const out = document.getElementById("previewout");

  // Read the weights currently on screen — the whole point is previewing
  // edits that haven't been saved.
  const draft = () => {
    const points = {};
    document.querySelectorAll(".rolepoints").forEach((input) => {
      const value = Number(input.value);
      if (input.value !== "" && value !== 0) points[input.dataset.role] = value;
    });
    const ranks = [];
    document.querySelectorAll(".ladderrow").forEach((row) => {
      const roleId = (row.querySelector(".rolepick-id") || {}).value || "0";
      if (roleId === "0") return;  // this rank is left empty
      ranks.push({ tier: row.dataset.tier, role_id: roleId,
                   min_points: Number(row.querySelector(".rankmin").value || 0) });
    });
    return { points: points, ranks: ranks,
             trials: window.readTrialMap ? window.readTrialMap() : [],
             enabled: document.getElementById("trialsenabled").checked,
             exclusive: document.getElementById("trialsexclusive").checked };
  };

  const tip = (row) => {
    if (!row.breakdown || !row.breakdown.length) return "no scoring roles";
    // A superseded role is shown, not hidden: seeing why a total is lower
    // than the roles held is the whole point of the hover.
    return row.breakdown
      .map((b) => b.counted === false
        ? `${b.name}: ${b.points} (superseded — same trial)`
        : `${b.name}: ${b.points}`)
      .join("
") + `
— total ${row.score}`;
  };

  const render = (rows, meta) => {
    out.innerHTML = "";
    if (!rows.length) {
      out.innerHTML = meta
        ? '<p class="muted">Nobody scored any points with these weights.</p>'
        : '<p class="muted">No names to look up.</p>';
      return;
    }
    if (meta) {
      const head = document.createElement("p");
      head.className = "muted small";
      head.textContent = `${meta.total} member(s) with points`
        + (meta.moving ? ` · ${meta.moving} would change rank` : " · nobody changes rank")
        + (rows.length < meta.total ? ` · showing the top ${rows.length}` : "");
      out.appendChild(head);
    }
    const table = document.createElement("table");
    table.className = "stats previewtable";
    table.innerHTML = "<thead><tr><th>#</th><th>Player</th><th class='num'>Points</th>"
      + "<th>Rank now</th><th>Would be</th></tr></thead>";
    const body = document.createElement("tbody");
    rows.forEach((row, index) => {
      const tr = document.createElement("tr");
      if (row.missing) {
        tr.innerHTML = `<td class="muted">—</td><td colspan="4" class="muted">`
          + `no member matched “${row.query}”</td>`;
        body.appendChild(tr);
        return;
      }
      if (row.changed) tr.className = "moved";
      // Hover shows where the points came from — on demand, not on screen.
      tr.title = tip(row) + (row.cleanup ? `
(${row.cleanup} superseded role(s) would come off)` : "");
      const cells = [
        String(index + 1),
        row.name,
        String(row.score),
        row.current || "—",
        row.rank || "—",
      ];
      cells.forEach((text, i) => {
        const td = document.createElement("td");
        if (i === 2) td.className = "num";
        td.textContent = text;
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
    table.appendChild(body);
    out.appendChild(table);
  };

  const ask = async (body, button) => {
    button.disabled = true;
    const res = await post(`/api/guild/${guildId}/trials`, body);
    button.disabled = false;
    if (!res.ok) { flash(res.error || "Failed", false); return null; }
    return res;
  };

  document.getElementById("trialpreview").addEventListener("click", async (e) => {
    const names = document.getElementById("trialnames").value
      .split(/[,\n]/).map((n) => n.trim()).filter(Boolean).slice(0, 10);
    if (!names.length) { flash("Type a name or two first", false); return; }
    const res = await ask({ action: "preview", names: names, ...draft() }, e.target);
    if (res) render(res.rows || [], null);
  });

  document.getElementById("trialpreviewall").addEventListener("click", async (e) => {
    flash("scoring everyone…", true);
    const res = await ask({ action: "preview_all", ...draft() }, e.target);
    if (res) render(res.rows || [], { total: res.total, moving: res.moving });
  });

  document.getElementById("trialpush").addEventListener("click", async (e) => {
    if (!confirm("Save these weights and apply the ranks to everyone now?")) return;
    flash("pushing live…", true);
    const res = await ask({ action: "push", ...draft() }, e.target);
    if (res) {
      const s = res.summary || {};
      flash(`live ✓ ${s.ranked || 0} ranked, ${s.granted || 0} granted, ${s.removed || 0} replaced`, true);
      setTimeout(() => location.reload(), 1200);
    }
  });
}

// --- Type-to-pick role selector -------------------------------------------
// A text box that filters the server's roles as you type. The hidden field
// holds the id, so half-typed text is never mistaken for a selection.
function bindRolePickers(root, roles) {
  root.querySelectorAll(".rolepick").forEach((pick) => {
    const text = pick.querySelector(".rolepick-text");
    const hidden = pick.querySelector(".rolepick-id");
    const list = pick.querySelector(".rolepick-list");
    const clear = pick.querySelector(".rolepick-clear");
    let active = -1;

    const chosen = () => String(hidden.value || "0");
    const announce = () => pick.dispatchEvent(new CustomEvent("rolechange", { bubbles: true }));

    const close = () => { list.hidden = true; active = -1; };
    const commit = (role) => {
      hidden.value = role ? role.id : 0;
      text.value = role ? role.name : "";
      close();
      announce();
    };

    const render = () => {
      const q = text.value.trim().toLowerCase().replace(/^@/, "");
      const matches = roles
        .filter((r) => !q || r.name.toLowerCase().replace(/^@/, "").includes(q))
        .slice(0, 40);
      list.innerHTML = "";
      if (!matches.length) {
        const empty = document.createElement("div");
        empty.className = "rolepick-empty";
        empty.textContent = "No role matches that";
        list.appendChild(empty);
      }
      matches.forEach((role, index) => {
        const item = document.createElement("div");
        item.className = "rolepick-item" + (index === active ? " active" : "");
        item.textContent = role.name;
        // mousedown, not click: blur would close the list first.
        item.addEventListener("mousedown", (e) => { e.preventDefault(); commit(role); });
        list.appendChild(item);
      });
      list.hidden = false;
    };

    text.addEventListener("focus", () => { active = -1; render(); });
    text.addEventListener("input", () => { active = -1; render(); });
    text.addEventListener("keydown", (e) => {
      const items = Array.from(list.querySelectorAll(".rolepick-item"));
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (list.hidden) { render(); return; }
        active += e.key === "ArrowDown" ? 1 : -1;
        active = Math.max(0, Math.min(items.length - 1, active));
        items.forEach((el, i) => el.classList.toggle("active", i === active));
        if (items[active]) items[active].scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter") {
        e.preventDefault();
        const q = text.value.trim().toLowerCase().replace(/^@/, "");
        const visible = roles.filter((r) => !q || r.name.toLowerCase().replace(/^@/, "").includes(q));
        const role = visible[active >= 0 ? active : 0];
        if (role) commit(role);
      } else if (e.key === "Escape") {
        close();
      }
    });
    // Leaving without choosing restores whatever was actually selected, so the
    // box can never show a role that isn't stored.
    text.addEventListener("blur", () => {
      setTimeout(() => {
        const role = roles.find((r) => String(r.id) === chosen());
        text.value = role ? role.name : "";
        close();
      }, 120);
    });
    clear.addEventListener("click", () => { commit(null); text.focus(); });
  });
}

// Wire the trial-rank pickers and keep each row's on/off state in step.
const _trialRoles = document.getElementById("all-roles");
if (_trialRoles) {
  const roles = JSON.parse(_trialRoles.textContent || "[]");
  const page = document.querySelector(".trialspage");
  bindRolePickers(page, roles);
  page.addEventListener("rolechange", (e) => {
    const row = e.target.closest(".ladderrow");
    if (row) row.classList.toggle("mapped", (e.target.querySelector(".rolepick-id").value || "0") !== "0");
  });
}

// --- Trial ranking: mapping which roles belong to which trial ---------------
const _trialMap = document.getElementById("trialmap");
if (_trialMap) {
  const roles = JSON.parse(document.getElementById("all-roles").textContent || "[]");
  const SLOTS = JSON.parse(document.getElementById("trial-slots").textContent || "[]");
  const SUGGESTIONS = JSON.parse(document.getElementById("trial-suggestions").textContent || "[]");
  const LABELS = {
    veteran: "Veteran clear", partial1: "Partial HM 1", partial2: "Partial HM 2",
    full_hm: "Full hardmode", trifecta: "Trifecta", extra: "Extra achievement",
  };

  const roleName = (id) => {
    const found = roles.find((r) => String(r.id) === String(id));
    return found ? found.name : "";
  };

  const addRow = (trial) => {
    trial = trial || { name: "", slots: {} };
    const index = _trialMap.children.length;
    const row = document.createElement("div");
    row.className = "trialrow";
    row.dataset.index = String(index);

    const head = document.createElement("div");
    head.className = "trialhead";
    const name = document.createElement("input");
    name.className = "trialname";
    name.value = trial.name || "";
    name.placeholder = "Trial name (e.g. Kyne's Aegis)";
    const del = document.createElement("button");
    del.className = "ghost trialdel";
    del.textContent = "×";
    del.title = "Remove this trial";
    del.addEventListener("click", () => row.remove());
    head.append(name, del);

    const grid = document.createElement("div");
    grid.className = "slotgrid";
    SLOTS.forEach((slot) => {
      const cell = document.createElement("label");
      cell.className = "slotcell";
      const label = document.createElement("span");
      label.className = "slotlabel";
      label.textContent = LABELS[slot] || slot;
      const pick = document.createElement("div");
      pick.className = "rolepick";
      pick.dataset.key = slot;
      const chosen = (trial.slots || {})[slot];
      pick.innerHTML =
        `<input class="rolepick-text" placeholder="—" autocomplete="off" spellcheck="false"` +
        ` value="${chosen ? roleName(chosen).replace(/"/g, "&quot;") : ""}">` +
        `<input type="hidden" class="rolepick-id" value="${chosen || 0}">` +
        `<button type="button" class="rolepick-clear" title="Clear">×</button>` +
        `<div class="rolepick-list" hidden></div>`;
      cell.append(label, pick);
      grid.appendChild(cell);
    });

    row.append(head, grid);
    _trialMap.appendChild(row);
    bindRolePickers(row, roles);   // the new pickers need wiring too
    return row;
  };

  document.getElementById("addtrial").addEventListener("click", () => addRow(null));

  document.getElementById("suggesttrials").addEventListener("click", () => {
    if (_trialMap.children.length &&
        !confirm("Add suggested trials to what's already mapped?")) return;
    const existing = new Set(
      Array.from(_trialMap.querySelectorAll(".trialname")).map((i) => i.value.trim().toLowerCase())
    );
    let added = 0;
    SUGGESTIONS.forEach((trial) => {
      if (existing.has((trial.name || "").trim().toLowerCase())) return;
      addRow(trial);
      added += 1;
    });
    flash(added ? `${added} trial(s) suggested — check them, then Push to live` : "nothing new to suggest", true);
  });

  // Read the mapping back out for save/preview.
  window.readTrialMap = () => Array.from(_trialMap.querySelectorAll(".trialrow")).map((row) => {
    const slots = {};
    row.querySelectorAll(".rolepick").forEach((pick) => {
      const id = (pick.querySelector(".rolepick-id") || {}).value || "0";
      if (id !== "0") slots[pick.dataset.key] = id;   // ids stay strings
    });
    return { name: row.querySelector(".trialname").value.trim(), slots: slots };
  }).filter((trial) => Object.keys(trial.slots).length);
}
