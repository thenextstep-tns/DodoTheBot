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
  let raw = "";
  try { raw = await resp.text(); data = JSON.parse(raw); } catch (_) { /* not JSON */ }
  const ok = resp.ok && data.ok;
  // A non-JSON reply (a 500 page, a 404 from the scope check, a proxy error)
  // used to surface as a bare "Failed" with the cause thrown away, which made
  // every such bug unreportable. Say what actually came back.
  let error = data.error;
  if (!ok && !error) {
    error = "HTTP " + resp.status + (raw ? ": " + raw.slice(0, 200).trim() : "");
  }
  // Pass the whole payload through: endpoints also return `value`, `rows`,
  // `summary`, … and dropping them silently turns a full answer into a blank one.
  return { ...data, ok: ok, error: error };
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

  // --- side menu: one panel at a time ---
  // Panels are hidden, never removed: Save and Push read every input on the
  // page, so a detached panel would silently drop its values.
  const navItems = Array.from(_trialsPage.querySelectorAll(".trialnavitem"));
  const panels = Array.from(_trialsPage.querySelectorAll(".trialpanel"));
  if (navItems.length) {
    const show = (key) => {
      if (!panels.some((p) => p.dataset.panel === key)) key = panels[0].dataset.panel;
      panels.forEach((p) => { p.hidden = p.dataset.panel !== key; });
      navItems.forEach((a) => a.classList.toggle("active", a.dataset.panel === key));
      return key;
    };
    navItems.forEach((item) => {
      item.addEventListener("click", (e) => {
        e.preventDefault();
        const key = show(item.dataset.panel);
        // Replace rather than push: the back button should leave the page, not
        // walk you through every tab you glanced at.
        history.replaceState(null, "", `#${key}`);
      });
    });
    // Deep links and reloads land where you left off.
    show((location.hash || "").replace("#", "") || panels[0].dataset.panel);
  }

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
    return {
      action: "save", points: points, ranks: window.readRanks(),
      trials: window.readTrialMap ? window.readTrialMap() : [],
      exclusive: document.getElementById("trialsexclusive").checked,
    };
  };

  document.getElementById("trialsave").addEventListener("click", async () => {
    const res = await post(`/api/guild/${guildId}/trials`, readSetup());
    flash(res.ok ? "trial ranking saved ✓" : (res.error || "Failed"), res.ok);
  });

  // Re-apply the *saved* setup to everyone enrolled. Separate from "Push to
  // live" on purpose: after fixing a role hierarchy you want to retry, not to
  // overwrite the stored weights with whatever the page happens to show.
  const run = document.getElementById("trialrun");
  if (run) {
    run.addEventListener("click", async () => {
      run.disabled = true;
      const res = await post(`/api/guild/${guildId}/trials`, { action: "run" });
      run.disabled = false;
      if (!res.ok) { flash(res.error || "Failed", false); return; }
      const s = res.summary || {};
      if (s.errors && s.errors.length) {
        alert(`Recalculated ${s.members || 0} member(s), but roles could not be changed:\n\n`
              + s.errors.map((e) => `• ${e.replace(/\*\*/g, "")}`).join("\n"));
      } else {
        flash(`recalculated: ${s.ranked || 0} ranked, ${s.granted || 0} granted, `
              + `${s.removed || 0} replaced ✓`, true);
      }
    });
  }

  // --- presets: a named copy of the whole ruleset ---
  const presetPick = document.getElementById("presetpick");
  if (presetPick) {
    const currentRuleset = () => ({
      points: (() => {
        const out = {};
        _trialsPage.querySelectorAll(".rolepoints").forEach((i) => {
          const v = Number(i.value);
          if (i.value !== "" && v !== 0 && i.dataset.role !== "0") out[i.dataset.role] = v;
        });
        return out;
      })(),
      ranks: window.readRanks(),
      trials: window.readTrialMap ? window.readTrialMap() : [],
    });

    const saveBtn = document.getElementById("presetsave");
    const saveNewBtn = document.getElementById("presetsavenew");
    const delBtn = document.getElementById("presetdel");
    const viewer = _trialsPage.dataset.uid || "0";

    // Overwrite is only offered on your own presets; everyone else gets "Save
    // as new". The server enforces the same rule — this just stops you finding
    // out by being refused.
    const syncOwnership = () => {
      const opt = presetPick.options[presetPick.selectedIndex];
      const author = (opt && opt.dataset.author) || "0";
      // "0" is a preset saved before authorship existed — nobody owns it, and
      // the server lets anyone claim it, so hiding Save here contradicted what
      // saving would actually do.
      const mine = presetPick.value !== "" && (author === viewer || author === "0");
      saveBtn.hidden = !mine;
      delBtn.hidden = !mine;
    };
    presetPick.addEventListener("change", syncOwnership);
    syncOwnership();

    const save = async (name) => {
      const res = await post(`/api/guild/${guildId}/trials`,
                             { action: "preset_save", name: name, ...currentRuleset() });
      if (!res.ok) { flash(res.error || "Failed", false); return; }
      flash(`preset “${res.name}” saved ✓`, true);
      setTimeout(() => location.reload(), 900);
    };

    saveBtn.addEventListener("click", () => {
      const name = presetPick.value;
      if (!name) return;
      if (confirm(`Overwrite “${name}” with what's on screen?`)) save(name);
    });

    saveNewBtn.addEventListener("click", () => {
      const name = prompt("Name for the new preset:", "");
      if (!name || !name.trim()) return;
      save(name.trim());
    });

    document.getElementById("presetload").addEventListener("click", async () => {
      const name = presetPick.value;
      if (!name) { flash("Pick a preset first", false); return; }
      if (!confirm(`Load “${name}”? This replaces what's on screen — nothing is saved `
                   + "until you press Save draft or Push to live.")) return;
      const res = await post(`/api/guild/${guildId}/trials`,
                             { action: "preset_load", name: name });
      if (!res.ok) { flash(res.error || "Failed", false); return; }
      flash(`loaded “${name}” — review, then Save draft to keep it`, true);
      applyPreset(res.preset);
    });

    delBtn.addEventListener("click", async () => {
      const name = presetPick.value;
      if (!name) { flash("Pick a preset first", false); return; }
      if (!confirm(`Delete the preset “${name}”? The live setup is untouched.`)) return;
      const res = await post(`/api/guild/${guildId}/trials`,
                             { action: "preset_delete", name: name });
      if (!res.ok) { flash(res.error || "Failed", false); return; }
      flash("preset deleted ✓", true);
      setTimeout(() => location.reload(), 700);
    });
  }

  // Fill the on-screen editor from a preset. Points are keyed by role id, so
  // every box that names a role it prices gets its value; anything the preset
  // doesn't mention is cleared rather than left behind from the old ruleset.
  function applyPreset(preset) {
    const points = preset.points || {};
    const trials = preset.trials || [];
    // Rebuild the editors *first*. Filling the boxes before this ran meant
    // setTrialMap immediately replaced every one of them with a fresh empty
    // input — which is why a loaded preset showed "pts" everywhere.
    if (window.setTrialMap) {
      // Slot boxes are built with their value, so the map needs the prices.
      window.setTrialMap(trials.map((t) => ({ ...t, points: points })));
    }
    if (window.setRanks) window.setRanks(preset.ranks || []);
    if (window.setExtras) window.setExtras(points, trials);
    // Then set every remaining box from the preset, and clear anything it
    // doesn't mention rather than leaving the old ruleset's number behind.
    _trialsPage.querySelectorAll(".rolepoints").forEach((input) => {
      const id = input.dataset.role;
      input.value = (id && id !== "0" && points[id] !== undefined) ? points[id] : "";
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }

  // --- the rollout: turning it on for one person at a time ---
  const enrol = document.getElementById("pilotenrol");
  if (enrol) {
    const tag = document.getElementById("pilottag");
    const run = async () => {
      const value = tag.value.trim();
      if (!value) { flash("Type a user tag first", false); return; }
      enrol.disabled = true;
      const res = await post(`/api/guild/${guildId}/trials`, { action: "enrol", tag: value });
      enrol.disabled = false;
      if (res.ok && res.errors && res.errors.length) {
        // Enrolled, rank worked out, roles refused. Saying "done ✓" over that
        // is exactly how it went unnoticed the first time.
        tag.value = "";
        alert(`${res.member.name} is enrolled and scores ${res.score} `
              + `(${res.rank || "no rank"}), but their roles were NOT changed:\n\n`
              + res.errors.map((e) => `• ${e.replace(/\*\*/g, "")}`).join("\n")
              + "\n\nFix that, then press Recalculate to apply it.");
        setTimeout(() => window.location.reload(), 500);
      } else if (res.ok) {
        tag.value = "";
        flash(`${res.member.name} is on: ${res.score} pts → ${res.rank || "no rank yet"}`
              + (res.cleared ? `, ${res.cleared} stale clear role(s) removed` : ""), true);
        // The roster, the counters and the log all move at once; a reload is
        // the honest way to show that rather than patching one row in place.
        setTimeout(() => window.location.reload(), 1200);
      } else flash(res.error || "Failed", false);
    };
    enrol.addEventListener("click", run);
    tag.addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });
  }

  const rosterBody = document.getElementById("pilotrows");
  if (rosterBody) {
    rosterBody.addEventListener("click", async (e) => {
      if (!e.target.classList.contains("pilotdel")) return;
      const userId = e.target.dataset.user;
      if (!confirm("Take this person off automatic ranking? Their roles stay as they are.")) return;
      const res = await post(`/api/guild/${guildId}/trials`,
                             { action: "unenrol", user_id: userId });
      if (res.ok) { e.target.closest("tr").remove(); flash("taken off ✓", true); }
      else flash(res.error || "Failed", false);
    });
  }

  // Saved on change rather than with the rest of the setup: it sits in the
  // rollout section, nowhere near the Save button, so waiting for one would
  // quietly lose the choice.
  const logChannel = document.getElementById("triallogchannel");
  if (logChannel) {
    logChannel.addEventListener("change", async () => {
      const res = await post(`/api/guild/${guildId}/trials`,
                             { action: "log_channel", channel_id: logChannel.value });
      flash(res.ok ? (res.channel ? `logging to #${res.channel} ✓` : "logging cleared")
                   : (res.error || "Failed"), res.ok);
    });
  }

  const announce = document.getElementById("announcepost");
  if (announce) {
    announce.addEventListener("click", async () => {
      const channel = document.getElementById("announcechannel");
      const name = channel.options[channel.selectedIndex].text;
      if (!confirm(`Post the announcement in ${name}? Everyone there will see it.`)) return;
      announce.disabled = true;
      const res = await post(`/api/guild/${guildId}/trials`,
                             { action: "announce", channel_id: channel.value });
      announce.disabled = false;
      flash(res.ok ? `posted in #${res.channel} ✓` : (res.error || "Failed"), res.ok);
    });
  }
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
    return { points: points, ranks: window.readRanks(),
             trials: window.readTrialMap ? window.readTrialMap() : [],
             exclusive: document.getElementById("trialsexclusive").checked };
  };

  // The preview table. Filters live above it; the breakdown opens on click
  // rather than on hover, because a tooltip you have to discover isn't an
  // answer to "why is my score that".
  let allRows = [];

  const breakdownRow = (row) => {
    const tr = document.createElement("tr");
    tr.className = "pvdetail";
    const td = document.createElement("td");
    td.colSpan = 7;
    if (!row.breakdown || !row.breakdown.length) {
      td.className = "muted";
      td.textContent = "No scoring roles.";
    } else {
      const list = document.createElement("div");
      list.className = "pvbreak";
      row.breakdown.forEach((b) => {
        const item = document.createElement("span");
        item.className = "pvchip" + (b.counted === false ? " superseded" : "");
        item.textContent = b.counted === false
          ? `${b.name} · ${b.points} (superseded)` : `${b.name} · ${b.points}`;
        list.appendChild(item);
      });
      if (row.bonus) {
        const rec = document.createElement("span");
        rec.className = "pvchip record";
        rec.textContent = `World records · ${row.bonus}`;
        list.appendChild(rec);
      }
      const total = document.createElement("div");
      total.className = "muted small";
      total.textContent = `Total ${row.score}`
        + (row.cleanup ? ` · ${row.cleanup} superseded role(s) would come off` : "");
      td.append(list, total);
    }
    tr.appendChild(td);
    return tr;
  };

  const render = (rows, meta) => {
    out.innerHTML = "";
    if (!rows.length) {
      out.innerHTML = '<p class="muted">Nobody matches.</p>';
      return;
    }
    const table = document.createElement("table");
    table.className = "stats previewtable";
    table.innerHTML = "<thead><tr><th>#</th><th>Player</th><th class='num'>Points</th>"
      + "<th>Rank now</th><th>Would be</th><th></th><th></th></tr></thead>";
    const body = document.createElement("tbody");
    rows.forEach((row, index) => {
      const tr = document.createElement("tr");
      if (row.direction === "up") tr.className = "promoted";
      else if (row.direction === "down") tr.className = "demoted";

      const num = document.createElement("td");
      num.textContent = String(index + 1);

      // Display name on top, the account tag under it — the tag is what you
      // search for and the display name is what you recognise.
      const who = document.createElement("td");
      const disp = document.createElement("div");
      disp.textContent = row.medals ? row.name + " " + row.medals : row.name;
      const tag = document.createElement("span");
      tag.className = "pvtag";
      tag.textContent = "@" + (row.tag || "");
      who.append(disp, tag);

      const pts = document.createElement("td");
      pts.className = "num";
      pts.textContent = String(row.score);
      // Where the total came from, so a record holder's score isn't a mystery.
      if (row.bonus) pts.title = `${row.score - row.bonus} from clears + ${row.bonus} from records`;
      const now = document.createElement("td");
      now.textContent = row.current || "—";
      const next = document.createElement("td");
      next.textContent = row.rank || "—";
      const arrow = document.createElement("td");
      arrow.className = "pvmove";
      arrow.textContent = row.direction === "up" ? "▲" : (row.direction === "down" ? "▼" : "");

      // Anywhere on the row opens the breakdown. Hanging it off the username
      // alone meant the one obvious thing to click — the row — did nothing.
      const chev = document.createElement("td");
      chev.className = "pvchev";
      chev.textContent = "▸";

      tr.append(num, who, pts, now, next, arrow, chev);
      tr.title = "Click for the clears behind this score";
      body.appendChild(tr);

      // Named `after`, not `next`: `next` is already the "would be" cell just
      // above, and two meanings of one word in ten lines is how bugs get in.
      tr.addEventListener("click", () => {
        const after = tr.nextElementSibling;
        if (after && after.classList.contains("pvdetail")) {
          after.remove();
          tr.classList.remove("open");
          chev.textContent = "▸";
          return;
        }
        tr.after(breakdownRow(row));
        tr.classList.add("open");
        chev.textContent = "▾";
      });
    });
    table.appendChild(body);
    out.appendChild(table);
  };

  // --- filters ---
  const filters = document.querySelector(".previewfilters");
  const fName = document.getElementById("pvname");
  const fRank = document.getElementById("pvrank");
  const fRole = document.getElementById("pvrole");
  const fMove = document.getElementById("pvmove");
  const counter = document.getElementById("pvcount");

  const fillOptions = (select, values, keep) => {
    select.innerHTML = "";
    const any = document.createElement("option");
    any.value = "";
    any.textContent = keep;
    select.appendChild(any);
    values.forEach((v) => {
      const o = document.createElement("option");
      o.value = v;
      o.textContent = v;
      select.appendChild(o);
    });
  };

  const applyFilters = () => {
    const q = (fName.value || "").trim().toLowerCase();
    const rank = fRank.value, role = fRole.value, move = fMove.value;
    const shown = allRows.filter((row) => {
      if (q && !(`${row.name} ${row.tag || ""}`.toLowerCase().includes(q))) return false;
      if (rank && row.rank !== rank && row.current !== rank) return false;
      if (role && !(row.breakdown || []).some((b) => b.name === role)) return false;
      if (move === "up" && row.direction !== "up") return false;
      if (move === "down" && row.direction !== "down") return false;
      if (move === "any" && !row.changed) return false;
      return true;
    });
    counter.textContent = `${shown.length} of ${allRows.length}`;
    render(shown, null);
  };

  [fName, fRank, fRole, fMove].forEach((el) => {
    el.addEventListener("input", applyFilters);
    el.addEventListener("change", applyFilters);
  });

  const ask = async (body, button) => {
    button.disabled = true;
    const res = await post(`/api/guild/${guildId}/trials`, body);
    button.disabled = false;
    if (!res.ok) { flash(res.error || "Failed", false); return null; }
    return res;
  };

  document.getElementById("trialpreviewall").addEventListener("click", async (e) => {
    flash("scoring everyone…", true);
    const res = await ask({ action: "preview_all", ...draft() }, e.target);
    if (!res) return;
    allRows = res.rows || [];
    // Offer only the ranks and roles that actually occur, so the filters can't
    // point at something with no rows behind it.
    const ranks = [...new Set(allRows.flatMap((r) => [r.current, r.rank]).filter(Boolean))].sort();
    const roles = [...new Set(allRows.flatMap(
      (r) => (r.breakdown || []).map((b) => b.name)))].sort();
    fillOptions(fRank, ranks, "Any rank");
    fillOptions(fRole, roles, "Any clear role");
    filters.hidden = false;
    flash(`${res.total} scored · ${res.moving} would change rank`, true);
    applyFilters();
  });

  // Owner-only, so it isn't on the page for everyone — an unguarded lookup here
  // would throw and take every later handler on the page down with it.
  const pushBtn = document.getElementById("trialpush");
  if (pushBtn) pushBtn.addEventListener("click", async (e) => {
    if (!confirm("Save these weights and apply the ranks to everyone now?")) return;
    flash("pushing live…", true);
    const res = await ask({ action: "push", ...draft() }, e.target);
    if (res) {
      const s = res.summary || {};
      flash(`live ✓ ${s.ranked || 0} ranked, ${s.granted || 0} granted, ${s.removed || 0} replaced`
            + (s.cleared ? `, ${s.cleared} superseded role(s) removed` : ""), true);
      document.querySelector(".trialspage")
        .dispatchEvent(new CustomEvent("trialspushed", { bubbles: true }));
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

// --- Trial ranking: the ladder is whatever rows you build -------------------
// No fixed rungs: a rank is a role, a threshold, an optional blurb and an
// optional badge. Rows are read in DOM order and the server sorts them by
// points, so nothing here has to care about ordering.
const _trialRoles = document.getElementById("all-roles");
if (_trialRoles) {
  const roles = JSON.parse(_trialRoles.textContent || "[]");
  const page = document.querySelector(".trialspage");
  const rankRows = document.getElementById("rankrows");
  const guildId = page.dataset.guild;
  bindRolePickers(page, roles);

  const renumber = () => {
    rankRows.querySelectorAll(".rankrow").forEach((row, index) => {
      row.querySelector(".rankindex").textContent = String(index + 1);
    });
  };

  const roleIdOf = (row) => (row.querySelector(".rolepick-id") || {}).value || "0";

  // ---- the badge: upload, preview, remove ----
  const imageCell = (row) => row.querySelector(".rankimg");

  const showPicture = (cell, url) => {
    const old = cell.querySelector(".rankimg-preview, .rankimg-empty");
    const img = document.createElement("img");
    img.className = "rankimg-preview";
    img.alt = "";
    img.src = `${url}?v=${Date.now()}`;    // bust the cache after a re-upload
    if (old) old.replaceWith(img); else cell.prepend(img);
    cell.dataset.has = "1";
    cell.querySelector(".rankimg-del").hidden = false;
  };

  const showEmpty = (cell) => {
    const old = cell.querySelector(".rankimg-preview, .rankimg-empty");
    const span = document.createElement("span");
    span.className = "rankimg-empty";
    span.textContent = "no picture";
    if (old) old.replaceWith(span); else cell.prepend(span);
    cell.dataset.has = "0";
    cell.querySelector(".rankimg-del").hidden = true;
  };

  rankRows.addEventListener("click", async (e) => {
    const row = e.target.closest(".rankrow");
    if (!row) return;
    if (e.target.classList.contains("rankdel")) {
      row.remove();
      renumber();
      return;
    }
    if (e.target.classList.contains("rankimg-pick")) {
      if (roleIdOf(row) === "0") { flash("Pick the rank's role first", false); return; }
      row.querySelector(".rankimg-file").click();
      return;
    }
    if (e.target.classList.contains("rankimg-del")) {
      const roleId = roleIdOf(row);
      if (roleId === "0") return;
      const res = await fetch(`/api/guild/${guildId}/trials/image/${roleId}`, { method: "DELETE" })
        .then((r) => r.json()).catch(() => ({ ok: false }));
      if (res.ok) { showEmpty(imageCell(row)); flash("picture removed ✓", true); }
      else flash(res.error || "Failed", false);
    }
  });

  rankRows.addEventListener("change", async (e) => {
    if (!e.target.classList.contains("rankimg-file")) return;
    const row = e.target.closest(".rankrow");
    const roleId = roleIdOf(row);
    const file = e.target.files && e.target.files[0];
    e.target.value = "";                     // let the same file be picked again
    if (!file || roleId === "0") return;
    const body = new FormData();
    body.append("image", file, file.name);
    const res = await fetch(`/api/guild/${guildId}/trials/image/${roleId}`,
                            { method: "POST", body: body })
      .then((r) => r.json()).catch(() => ({ ok: false, error: "Upload failed" }));
    if (res.ok) { showPicture(imageCell(row), res.url); flash("picture saved ✓", true); }
    else flash(res.error || "Failed", false);
  });

  const addRank = (rank) => {
    rank = rank || {};
    const row = document.createElement("div");
    row.className = "rankrow";
    const main = document.createElement("div");
    main.className = "rankmain";

    const index = document.createElement("span");
    index.className = "rankindex";

    // Built with DOM calls rather than markup: role names are arbitrary text.
    const pick = document.createElement("div");
    pick.className = "rolepick";
    pick.dataset.key = "rank";
    const text = document.createElement("input");
    text.className = "rolepick-text";
    text.placeholder = "Type a role name…";
    text.autocomplete = "off";
    text.spellcheck = false;
    const hiddenId = document.createElement("input");
    hiddenId.type = "hidden";
    hiddenId.className = "rolepick-id";
    hiddenId.value = rank.role_id || "0";
    text.value = rank.role_id ? (roles.find(
      (r) => String(r.id) === String(rank.role_id)) || {}).name || "" : "";
    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "rolepick-clear";
    clearBtn.title = "Clear";
    clearBtn.textContent = "×";
    const list = document.createElement("div");
    list.className = "rolepick-list";
    list.hidden = true;
    pick.append(text, hiddenId, clearBtn, list);

    const at = document.createElement("span");
    at.className = "rankmid";
    at.textContent = "at";
    const min = document.createElement("input");
    min.type = "number";
    min.className = "rankmin";
    min.placeholder = "0";
    if (rank.min_points !== undefined) min.value = rank.min_points;
    const pts = document.createElement("span");
    pts.className = "rankmid";
    pts.textContent = "points";

    const cell = document.createElement("div");
    cell.className = "rankimg";
    cell.dataset.has = "0";
    const empty = document.createElement("span");
    empty.className = "rankimg-empty";
    empty.textContent = "no picture";
    const file = document.createElement("input");
    file.type = "file";
    file.className = "rankimg-file";
    file.accept = "image/png,image/jpeg,image/webp,image/gif";
    file.hidden = true;
    const pickBtn = document.createElement("button");
    pickBtn.type = "button";
    pickBtn.className = "ghost rankimg-pick";
    pickBtn.textContent = "Picture…";
    const delImg = document.createElement("button");
    delImg.type = "button";
    delImg.className = "ghost rankimg-del";
    delImg.textContent = "Remove";
    delImg.hidden = true;
    cell.append(empty, file, pickBtn, delImg);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "ghost rankdel";
    del.title = "Remove this rank";
    del.textContent = "×";

    main.append(index, pick, at, min, pts, cell, del);
    const desc = document.createElement("textarea");
    desc.className = "rankdesc";
    desc.rows = 2;
    desc.maxLength = 400;
    desc.placeholder = "Optional — shown on the /rank card for this rank";
    desc.value = rank.description || "";
    row.append(main, desc);
    row.classList.toggle("mapped", String(rank.role_id || "0") !== "0");
    rankRows.appendChild(row);
    bindRolePickers(row, roles);
    renumber();
  };

  const addButton = document.getElementById("addrank");
  if (addButton) addButton.addEventListener("click", () => addRank(null));

  // Replace the whole ladder — used when a preset is loaded.
  window.setRanks = (ranks) => {
    rankRows.innerHTML = "";
    (ranks || []).forEach((rank) => addRank(rank));
    renumber();
  };

  page.addEventListener("rolechange", (e) => {
    const row = e.target.closest(".rankrow");
    if (row) row.classList.toggle("mapped", roleIdOf(row) !== "0");
  });

  // Read the ladder back out for save / preview / push.
  window.readRanks = () => Array.from(rankRows.querySelectorAll(".rankrow")).map((row) => {
    const roleId = roleIdOf(row);
    if (roleId === "0") return null;     // a row with no role picked yet
    return { role_id: roleId,
             min_points: Number(row.querySelector(".rankmin").value || 0),
             description: row.querySelector(".rankdesc").value.trim() };
  }).filter(Boolean);
}
if (!window.readRanks) window.readRanks = () => [];

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
      // Built with DOM calls, not markup: a role name is arbitrary text chosen
      // by whoever created the role, and .value as a property is never parsed
      // as HTML.
      const text = document.createElement("input");
      text.className = "rolepick-text";
      text.placeholder = "—";
      text.autocomplete = "off";
      text.spellcheck = false;
      text.value = chosen ? roleName(chosen) : "";
      const hiddenId = document.createElement("input");
      hiddenId.type = "hidden";
      hiddenId.className = "rolepick-id";
      hiddenId.value = chosen || 0;
      const clear = document.createElement("button");
      clear.type = "button";
      clear.className = "rolepick-clear";
      clear.title = "Clear";
      clear.textContent = "×";
      const list = document.createElement("div");
      list.className = "rolepick-list";
      list.hidden = true;
      pick.append(text, hiddenId, clear, list);
      const pts = document.createElement("input");
      pts.type = "number";
      pts.className = "rolepoints slotpoints";
      pts.placeholder = "pts";
      pts.dataset.role = chosen || "0";
      pts.hidden = !chosen;
      if (chosen && (trial.points || {})[chosen] !== undefined) {
        pts.value = trial.points[chosen];
      }
      cell.append(label, pick, pts);
      grid.appendChild(cell);
    });

    row.append(head, grid);
    _trialMap.appendChild(row);
    bindRolePickers(row, roles);   // the new pickers need wiring too
    return row;
  };

  document.getElementById("addtrial").addEventListener("click", () => addRow(null));

  // Replace the whole mapping — used when a preset is loaded.
  window.setTrialMap = (trials) => {
    _trialMap.innerHTML = "";
    (trials || []).forEach((trial) => addRow(trial));
  };

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

  // A slot's score belongs to the role in that slot, so the box has to follow
  // the picker — otherwise editing a mapping would silently reprice whatever
  // role used to be there.
  _trialMap.addEventListener("rolechange", (e) => {
    const cell = e.target.closest(".slotcell");
    if (!cell) return;
    const id = (cell.querySelector(".rolepick-id") || {}).value || "0";
    const pts = cell.querySelector(".slotpoints");
    if (!pts) return;
    pts.dataset.role = id;
    pts.hidden = id === "0";
    if (id === "0") pts.value = "";
  });

  // Type-to-find across trial names and every role they map.
  const search = document.getElementById("trialsearch");
  if (search) {
    search.addEventListener("input", () => {
      const q = search.value.trim().toLowerCase();
      _trialMap.querySelectorAll(".trialrow").forEach((row) => {
        row.style.display = !q || (row.dataset.search || "").includes(q) ? "" : "none";
      });
      document.querySelectorAll("#extrascores .extrarow").forEach((row) => {
        row.style.display = !q || (row.dataset.search || "").includes(q) ? "" : "none";
      });
    });
  }

  // --- standalone scoring roles (achievements that belong to no trial) ---
  const extras = document.getElementById("extrascores");
  if (extras) {
    extras.addEventListener("click", (e) => {
      if (e.target.classList.contains("extradel")) e.target.closest(".extrarow").remove();
    });
    extras.addEventListener("rolechange", (e) => {
      const row = e.target.closest(".extrarow");
      if (!row) return;
      const id = (row.querySelector(".rolepick-id") || {}).value || "0";
      row.querySelector(".rolepoints").dataset.role = id;
    });
    const buildExtraRow = (roleId, value) => {
      const row = document.createElement("div");
      row.className = "extrarow";
      const pick = document.createElement("div");
      pick.className = "rolepick";
      pick.dataset.key = "extra";
      const text = document.createElement("input");
      text.className = "rolepick-text";
      text.placeholder = "Type a role name…";
      text.autocomplete = "off";
      text.spellcheck = false;
      text.value = roleId ? (roles.find((r) => String(r.id) === String(roleId)) || {}).name || "" : "";
      const hid = document.createElement("input");
      hid.type = "hidden";
      hid.className = "rolepick-id";
      hid.value = roleId || "0";
      const clr = document.createElement("button");
      clr.type = "button";
      clr.className = "rolepick-clear";
      clr.textContent = "×";
      const lst = document.createElement("div");
      lst.className = "rolepick-list";
      lst.hidden = true;
      pick.append(text, hid, clr, lst);
      const pts = document.createElement("input");
      pts.type = "number";
      pts.className = "rolepoints";
      pts.placeholder = "pts";
      pts.dataset.role = roleId || "0";
      if (value !== undefined) pts.value = value;
      const del = document.createElement("button");
      del.type = "button";
      del.className = "ghost extradel";
      del.textContent = "×";
      row.append(pick, pts, del);
      extras.appendChild(row);
      bindRolePickers(row, roles);
      return { row, text };
    };

    const addExtra = document.getElementById("addextra");
    if (addExtra) {
      addExtra.addEventListener("click", () => buildExtraRow(null).text.focus());
    }

    // Rebuild the standalone list from a preset: everything it prices that
    // isn't mapped to one of its trials.
    window.setExtras = (points, trials) => {
      const mapped = new Set();
      (trials || []).forEach((t) => Object.values(t.slots || {}).forEach(
        (id) => mapped.add(String(id))));
      extras.innerHTML = "";
      Object.entries(points || {}).forEach(([roleId, value]) => {
        if (!mapped.has(String(roleId))) buildExtraRow(roleId, value);
      });
    };
  }

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

// --- Edited-value feedback --------------------------------------------------
// A points grid gives almost no sign that a number changed: same box, same
// place, new digits. Every scoring input remembers what it was loaded with and
// shows the difference until it's pushed, so an edit is visible without having
// to remember what you typed.
(function markEdits() {
  const page = document.querySelector(".trialspage");
  if (!page) return;

  const badge = (row, from, to) => {
    let tag = row.querySelector(".wasvalue");
    if (!tag) {
      tag = document.createElement("span");
      tag.className = "wasvalue";
      const anchor = row.querySelector(".rolename");
      if (anchor) anchor.insertAdjacentElement("afterend", tag);
      else row.appendChild(tag);
    }
    const arrow = Number(to) > Number(from) ? "↑" : "↓";
    tag.textContent = `was ${from === "" ? "—" : from} ${arrow} ${to === "" ? "—" : to}`;
    tag.classList.toggle("up", Number(to) > Number(from));
    tag.classList.toggle("down", Number(to) < Number(from));
  };

  const watch = (input, rowSelector) => {
    const row = input.closest(rowSelector);
    if (!row) return;
    // The value the page was rendered with — the thing "changed" is measured against.
    const original = input.dataset.original !== undefined ? input.dataset.original : input.value;
    input.dataset.original = original;
    const update = () => {
      const changed = String(input.value) !== String(original);
      row.classList.toggle("edited", changed);
      const tag = row.querySelector(".wasvalue");
      if (changed) badge(row, original, input.value);
      else if (tag) tag.remove();
    };
    input.addEventListener("input", update);
    input.addEventListener("change", update);
  };

  page.querySelectorAll(".rolepoints").forEach((i) => watch(i, ".scorerow"));
  page.querySelectorAll(".rankmin").forEach((i) => watch(i, ".rankrow"));

  // Once the weights are live, the current values become the new baseline.
  page.addEventListener("trialspushed", () => {
    page.querySelectorAll(".rolepoints, .rankmin").forEach((input) => {
      input.dataset.original = input.value;
    });
    page.querySelectorAll(".edited").forEach((row) => row.classList.remove("edited"));
    page.querySelectorAll(".wasvalue").forEach((tag) => tag.remove());
  });
})();


// --- Dashboard status board: a card on hover, like a real status page --------
// Everything shown is already on the bar as data-attributes, so this is pure
// presentation — no request, and no second source of truth to drift.
(function statusBars() {
  const strip = document.getElementById("hbars");
  const pop = document.getElementById("hpop");
  if (!strip || !pop) return;

  const LABEL = {
    ok: ["ok", "No downtime recorded on this day."],
    degraded: ["warn", "Degraded performance"],
    down: ["down", "Partial outage"],
    none: ["none", "No data recorded on this day."],
  };

  const show = (bar) => {
    const state = bar.dataset.state || "none";
    const [kind, headline] = LABEL[state] || LABEL.none;
    pop.innerHTML = "";

    const day = document.createElement("div");
    day.className = "hpop-day";
    day.textContent = bar.dataset.day;
    pop.appendChild(day);

    if (state === "ok" || state === "none") {
      const line = document.createElement("div");
      line.className = "hpop-none";
      line.textContent = headline;
      pop.appendChild(line);
    } else {
      const row = document.createElement("div");
      row.className = "hpop-row " + kind;
      const icon = document.createElement("span");
      icon.textContent = state === "down" ? "⚠" : "◐";
      const what = document.createElement("span");
      what.className = "hpop-what";
      what.textContent = headline;
      const dur = document.createElement("span");
      dur.className = "hpop-dur";
      dur.textContent = state === "down" ? bar.dataset.down : bar.dataset.degraded;
      row.append(icon, what, dur);
      pop.appendChild(row);
    }

    if (bar.dataset.samples && bar.dataset.samples !== "0") {
      const meta = document.createElement("div");
      meta.className = "hpop-meta";
      meta.textContent = `${bar.dataset.uptime}% uptime · ${bar.dataset.samples} checks`;
      pop.appendChild(meta);
    }

    // Positioned against the strip so it can't fall off either end.
    pop.hidden = false;
    const stripBox = strip.getBoundingClientRect();
    const barBox = bar.getBoundingClientRect();
    const width = pop.offsetWidth;
    let left = barBox.left - stripBox.left + barBox.width / 2 - width / 2;
    left = Math.max(0, Math.min(left, stripBox.width - width));
    pop.style.left = `${left}px`;
  };

  const hide = () => { pop.hidden = true; };

  strip.addEventListener("mouseover", (e) => {
    if (e.target.classList.contains("hbar")) show(e.target);
  });
  strip.addEventListener("focusin", (e) => {
    if (e.target.classList.contains("hbar")) show(e.target);
  });
  strip.addEventListener("mouseleave", hide);
  strip.addEventListener("focusout", hide);
})();


// --- Strings page: a cog at a time, one editor, search over the index --------
// 597 live textareas gave no way to *find* anything, only to scroll. The list is
// an index; editing happens in one drawer, so there is a single place a change
// can be made and a single place it can be validated.
(function langPage() {
  const page = document.querySelector(".langpage");
  const drawer = document.getElementById("langdrawer");
  if (!page || !drawer) return;

  const navItems = Array.from(page.querySelectorAll(".langnavitem"));
  const panels = Array.from(page.querySelectorAll(".langpanel"));
  const search = document.getElementById("langsearch");
  const editedOnly = document.getElementById("langedited");
  const counter = document.getElementById("langcount");
  const rows = Array.from(page.querySelectorAll(".langrow"));

  const show = (group) => {
    panels.forEach((p) => { p.hidden = p.dataset.group !== group; });
    navItems.forEach((a) => a.classList.toggle("active", a.dataset.group === group));
  };
  navItems.forEach((item) => item.addEventListener("click", (e) => {
    e.preventDefault();
    search.value = "";
    editedOnly.checked = false;
    filter();
    show(item.dataset.group);
  }));

  // Search spans every group at once: hunting for wording you only half
  // remember is the whole reason this page exists.
  function filter() {
    const q = (search.value || "").trim().toLowerCase();
    const onlyEdited = editedOnly.checked;
    let shown = 0;
    rows.forEach((row) => {
      const hit = (!q || (row.dataset.search || "").includes(q))
        && (!onlyEdited || row.dataset.edited === "1");
      row.hidden = !hit;
      if (hit) shown += 1;
    });
    if (q || onlyEdited) {
      panels.forEach((p) => {
        p.hidden = !Array.from(p.querySelectorAll(".langrow")).some((r) => !r.hidden);
      });
      navItems.forEach((a) => a.classList.remove("active"));
      counter.textContent = shown + (shown === 1 ? " match" : " matches");
    } else {
      counter.textContent = "";
      if (navItems.length) show(navItems[0].dataset.group);
    }
  }
  search.addEventListener("input", filter);
  editedOnly.addEventListener("change", filter);

  // --- the editor ---
  const kEl = document.getElementById("drawerkey");
  const vEl = document.getElementById("drawervalue");
  const dEl = document.getElementById("drawerdefault");
  const phEl = document.getElementById("drawerph");
  const warnEl = document.getElementById("drawerwarn");
  const lenEl = document.getElementById("drawerlen");
  let current = null;

  const close = () => { drawer.hidden = true; current = null; };
  document.getElementById("drawerclose").addEventListener("click", close);

  const measure = () => {
    const n = vEl.value.length;
    lenEl.textContent = n + (n === 1 ? " character" : " characters");
    lenEl.className = "muted small" + (n > 2000 ? " overlimit" : "");
  };
  vEl.addEventListener("input", measure);

  const open = (row) => {
    current = row;
    kEl.textContent = row.dataset.key;
    vEl.value = row.querySelector(".langvalue").value;
    dEl.textContent = row.querySelector(".langdefault").textContent;
    phEl.innerHTML = "";
    // Placeholders are click-to-insert: retyping {mention} by hand is how a
    // brace gets dropped and a command starts throwing.
    row.querySelectorAll(".ph").forEach((chip) => {
      const c = document.createElement("code");
      c.className = "ph";
      c.textContent = chip.textContent;
      c.title = "Click to insert";
      c.addEventListener("click", () => {
        const at = vEl.selectionStart || vEl.value.length;
        vEl.value = vEl.value.slice(0, at) + chip.textContent + vEl.value.slice(at);
        vEl.focus();
        measure();
      });
      phEl.appendChild(c);
    });
    warnEl.hidden = true;
    drawer.hidden = false;
    measure();
    vEl.focus();
  };

  page.addEventListener("click", (e) => {
    const row = e.target.closest(".langrow");
    if (row) open(row);
  });

  // "/" focuses search, Escape closes the drawer.
  document.addEventListener("keydown", (e) => {
    const tag = (document.activeElement || {}).tagName;
    if (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA") {
      e.preventDefault();
      search.focus();
    }
    if (e.key === "Escape" && !drawer.hidden) close();
  });

  const showWarnings = (list) => {
    warnEl.innerHTML = "";
    if (!list || !list.length) { warnEl.hidden = true; return; }
    list.forEach((w) => {
      const line = document.createElement("div");
      line.textContent = "⚠ " + w;
      warnEl.appendChild(line);
    });
    warnEl.hidden = false;
  };

  document.getElementById("drawersave").addEventListener("click", async () => {
    if (!current) return;
    const res = await post("/api/lang", {
      key: current.dataset.key,
      value: vEl.value,
      is_list: current.dataset.list === "1",
    });
    if (!res.ok) { flash(res.error || "Failed", false); showWarnings([]); return; }
    current.querySelector(".langvalue").value = vEl.value;
    current.querySelector(".langpreview").textContent =
      vEl.value.length > 110 ? vEl.value.slice(0, 110) + "…" : vEl.value;
    current.dataset.edited = "1";
    current.dataset.search = (current.dataset.key + " " + vEl.value).toLowerCase();
    if (!current.querySelector(".langtag.edited")) {
      const tag = document.createElement("span");
      tag.className = "langtag edited";
      tag.textContent = "edited";
      current.querySelector(".langmarks").appendChild(tag);
    }
    showWarnings(res.warnings);
    flash(res.warnings && res.warnings.length
      ? "saved, " + res.warnings.length + " warning(s)" : "saved ✓", true);
  });

  document.getElementById("drawerreset").addEventListener("click", async () => {
    if (!current) return;
    if (!confirm("Reset " + current.dataset.key + " to its default?")) return;
    const res = await post("/api/lang", { key: current.dataset.key, action: "reset" });
    if (!res.ok) { flash(res.error || "Failed", false); return; }
    flash("reset ✓", true);
    setTimeout(() => location.reload(), 600);
  });
})();


// --- Trial ranks: world-record holders ---------------------------------------
// A record belongs to a person, not a role, so it is edited here rather than on
// the points board. Edit fills the add row instead of opening a second form:
// one place to type, whether the person is already listed or not.
(function worldRecords() {
  const page = document.querySelector(".trialspage");
  const rows = document.getElementById("wrrows");
  if (!page || !rows) return;

  const guildId = page.dataset.guild;
  const tag = document.getElementById("wrtag");
  const current = document.getElementById("wrcurrent");
  const former = document.getElementById("wrformer");
  const saveBtn = document.getElementById("wrsave");
  let editingId = null;

  rows.addEventListener("click", (e) => {
    if (!e.target.classList.contains("wredit")) return;
    const row = e.target.closest("tr");
    editingId = e.target.dataset.user;
    tag.value = e.target.dataset.name;
    tag.disabled = true;
    current.value = row.dataset.current;
    former.value = row.dataset.former;
    saveBtn.textContent = "Update";
    current.focus();
  });

  const reset = () => {
    editingId = null;
    tag.value = "";
    tag.disabled = false;
    current.value = "";
    former.value = "";
    saveBtn.textContent = "Save";
  };

  tag.addEventListener("input", () => { if (!tag.disabled) editingId = null; });

  saveBtn.addEventListener("click", async () => {
    const body = {
      action: "wr_set",
      tag: tag.value.trim(),
      user_id: editingId || "",
      current: Number(current.value || 0),
      former: Number(former.value || 0),
    };
    if (!body.user_id && !body.tag) { flash("Type a user tag first", false); return; }
    saveBtn.disabled = true;
    const res = await post(`/api/guild/${guildId}/trials`, body);
    saveBtn.disabled = false;
    if (!res.ok) { flash(res.error || "Failed", false); return; }
    flash(`${res.name}: +${res.bonus} points`, true);
    reset();
    // The table, the counters and the menu badge all move together, so the
    // page is redrawn rather than one row patched and the rest left stale.
    setTimeout(() => location.reload(), 700);
  });

  [current, former].forEach((el) => el.addEventListener("keydown", (e) => {
    if (e.key === "Enter") saveBtn.click();
    if (e.key === "Escape") reset();
  }));
})();
