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
                            role_ids: Array.from(ids.selectedOptions).map((o) => Number(o.value)) });
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
                        channel_ids: Array.from(chans.selectedOptions).map((o) => Number(o.value)) };
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
      role_id: Number(row.querySelector(".pt-role").value),
      points: Number(row.querySelector(".pt-points").value || 0),
    })),
    tiers: Array.from(tierRows.children).map((row) => ({
      name: row.querySelector(".pt-name").value,
      min_points: Number(row.querySelector(".pt-min").value || 0),
      role_id: Number(row.querySelector(".pt-role").value),
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
  _trialsPage.querySelectorAll(".rankmin").forEach((input) => {
    input.addEventListener("input", () => {
      input.closest(".scorerow").classList.toggle("isrank", input.value !== "");
    });
  });

  const readSetup = () => {
    const points = {};
    _trialsPage.querySelectorAll(".rolepoints").forEach((input) => {
      const value = Number(input.value);
      if (input.value !== "" && value !== 0) points[input.dataset.role] = value;
    });
    const ranks = [];
    _trialsPage.querySelectorAll(".rankmin").forEach((input) => {
      if (input.value === "") return;
      ranks.push({
        role_id: Number(input.dataset.role),
        min_points: Number(input.value),
        name: input.closest(".scorerow").querySelector(".rolename").textContent.trim(),
      });
    });
    return {
      action: "save", points: points, ranks: ranks,
      enabled: document.getElementById("trialsenabled").checked,
      exclusive: document.getElementById("trialsexclusive").checked,
    };
  };

  document.getElementById("trialsave").addEventListener("click", async () => {
    const res = await post(`/api/guild/${guildId}/trials`, readSetup());
    flash(res.ok ? "trial ranking saved ✓" : (res.error || "Failed"), res.ok);
  });

  document.getElementById("trialrun").addEventListener("click", async (e) => {
    e.target.disabled = true;
    flash("recalculating…", true);
    const res = await post(`/api/guild/${guildId}/trials`, { action: "run" });
    e.target.disabled = false;
    if (res.ok) { flash("ranks recalculated ✓", true); setTimeout(() => location.reload(), 900); }
    else { flash(res.error || "Failed", false); }
  });
}
