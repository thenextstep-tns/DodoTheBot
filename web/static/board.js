"use strict";

// The public leaderboard. Everything it needs is embedded in the page, so
// filtering, expanding and comparing cost no requests and the token in the URL
// is never sent anywhere again.
(function board() {
  const raw = document.getElementById("board-data");
  const body = document.getElementById("brows");
  if (!raw || !body) return;

  const data = JSON.parse(raw.textContent || "{}");
  const players = data.players || [];
  const roles = data.roles || [];
  const search = document.getElementById("bsearch");
  const rankSel = document.getElementById("brank");
  const achSel = document.getElementById("bach");
  const wrOnly = document.getElementById("bwr");
  const counter = document.getElementById("bcount");
  const compareBtn = document.getElementById("bcompare");
  const compareUI = document.getElementById("bcompareui");

  // Podium is the first three *overall*, not of whatever the filter shows: a
  // search must not be able to invent a winner.
  players.forEach((p, i) => { p.place = i; });

  const fill = (select, values) => {
    values.forEach((v) => {
      const o = document.createElement("option");
      o.value = v;
      o.textContent = v;
      select.appendChild(o);
    });
  };
  fill(rankSel, [...new Set(players.map((p) => p.rank).filter((r) => r && r !== "—"))].sort());
  fill(achSel, roles.map((r) => r.name));

  const breakdownRow = (player, span) => {
    const tr = document.createElement("tr");
    tr.className = "bdetail";
    const td = document.createElement("td");
    td.colSpan = span;
    if (!player.held.length && !player.bonus) {
      td.className = "none";
      td.textContent = "No scoring clears yet.";
    } else {
      const wrap = document.createElement("div");
      wrap.className = "bchips";
      player.held.forEach((name) => {
        const chip = document.createElement("span");
        const counted = player.has.indexOf(name) >= 0;
        chip.className = "bchip" + (counted ? "" : " superseded");
        chip.textContent = counted ? name : name + " (superseded)";
        wrap.appendChild(chip);
      });
      if (player.bonus) {
        const chip = document.createElement("span");
        chip.className = "bchip record";
        chip.textContent = "World records · " + player.bonus;
        wrap.appendChild(chip);
      }
      td.appendChild(wrap);
    }
    tr.appendChild(td);
    return tr;
  };

  const render = () => {
    const q = (search.value || "").trim().toLowerCase();
    const rank = rankSel.value;
    const ach = achSel.value;
    const shown = players.filter((p) =>
      (!q || p.name.toLowerCase().includes(q))
      && (!rank || p.rank === rank)
      && (!ach || p.held.indexOf(ach) >= 0)
      && (!wrOnly.checked || p.wr));
    body.innerHTML = "";
    const filtered = q || rank || ach || wrOnly.checked;
    counter.textContent = filtered ? shown.length + " of " + players.length : "";
    if (!shown.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 5;
      td.className = "none";
      td.textContent = "Nobody matches.";
      tr.appendChild(td);
      body.appendChild(tr);
      return;
    }
    shown.forEach((player) => {
      const tr = document.createElement("tr");
      tr.className = "brow" + (player.place < 3
        ? " " + ["gold", "silver", "bronze"][player.place] : "");

      const pos = document.createElement("td");
      pos.className = "pos";
      pos.textContent = player.place < 3
        ? ["\u{1F947}", "\u{1F948}", "\u{1F949}"][player.place] : String(player.place + 1);

      const who = document.createElement("td");
      who.className = "who";
      who.textContent = player.name;
      if (player.medals) {
        const med = document.createElement("span");
        med.className = "med";
        med.textContent = " " + player.medals;
        who.appendChild(med);
      }

      const pts = document.createElement("td");
      pts.className = "pts";
      pts.textContent = String(player.score);

      const rankCell = document.createElement("td");
      rankCell.className = "rk";
      const pill = document.createElement("span");
      pill.className = "rankpill";
      pill.textContent = player.rank;
      // The role's own colour, softened into a sweep so it reads as a badge
      // rather than as a block of raw hex.
      if (player.colour) {
        pill.style.color = player.colour;
        pill.style.borderColor = player.colour + "66";
        pill.style.backgroundImage =
          "linear-gradient(100deg, " + player.colour + "1f, " + player.colour + "05 60%)";
      }
      rankCell.appendChild(pill);

      const chev = document.createElement("td");
      chev.className = "bchev";
      chev.textContent = "▸";

      tr.append(pos, who, pts, rankCell, chev);
      body.appendChild(tr);

      tr.addEventListener("click", () => {
        const after = tr.nextElementSibling;
        if (after && after.classList.contains("bdetail")) {
          after.remove();
          chev.textContent = "▸";
          return;
        }
        tr.after(breakdownRow(player, 5));
        chev.textContent = "▾";
      });
    });
  };

  [search, rankSel, achSel, wrOnly].forEach((el) => {
    el.addEventListener("input", render);
    el.addEventListener("change", render);
  });
  render();

  // --- compare -------------------------------------------------------------
  // Type-to-find rather than a scroll list, and grouped by trial, because a
  // flat sixty-row wall answers "who has more" without ever saying where the
  // difference actually is.
  const picker = (id, initial) => {
    const wrap = document.createElement("span");
    wrap.className = "bpickone";
    const input = document.createElement("input");
    input.setAttribute("list", id);
    input.autocomplete = "off";
    input.placeholder = "Type a name";
    input.value = (players[initial] || {}).name || "";
    const list = document.createElement("datalist");
    list.id = id;
    players.forEach((p) => {
      const o = document.createElement("option");
      o.value = p.name;
      list.appendChild(o);
    });
    wrap.append(input, list);
    wrap.input = input;
    return wrap;
  };

  const findPlayer = (name) =>
    players.find((p) => p.name.toLowerCase() === (name || "").trim().toLowerCase());

  let open = false;
  compareBtn.addEventListener("click", () => {
    open = !open;
    compareUI.hidden = !open;
    compareBtn.textContent = open ? "Close comparison" : "Compare two players";
    if (!open) return;
    compareUI.innerHTML = "";
    if (players.length < 2) {
      compareUI.textContent = "Two players are needed to compare.";
      return;
    }
    const pickers = document.createElement("div");
    pickers.className = "bpick";
    const left = picker("cmp-left", 0);
    const right = picker("cmp-right", 1);
    pickers.append(left, Object.assign(document.createElement("span"),
                                       { className: "vs", textContent: "vs" }), right);
    const out = document.createElement("div");
    const note = document.createElement("p");
    note.className = "bnote";
    note.textContent =
      "Comparison is the thief of joy! Don't get too obsessed with someone else's results ❤️";
    compareUI.append(pickers, out, note);

    const draw = () => {
      const a = findPlayer(left.input.value);
      const b = findPlayer(right.input.value);
      out.innerHTML = "";
      if (!a || !b) {
        out.innerHTML = "";
        const hint = document.createElement("p");
        hint.className = "muted";
        hint.textContent = "Pick two players.";
        out.appendChild(hint);
        return;
      }

      const head = document.createElement("div");
      head.className = "bcmphead";
      [a, b].forEach((p) => {
        const cell = document.createElement("div");
        const n = document.createElement("b");
        n.textContent = p.name;
        const s = document.createElement("span");
        s.className = "muted small";
        s.textContent = " " + p.score + " pts · " + p.rank;
        cell.append(n, s);
        head.appendChild(cell);
      });
      out.appendChild(head);

      // Group in the order the roles arrive (points descending), so the
      // heaviest raids lead.
      const groups = [];
      const byName = {};
      roles.forEach((role) => {
        if (!byName[role.group]) {
          byName[role.group] = { name: role.group, rows: [] };
          groups.push(byName[role.group]);
        }
        byName[role.group].rows.push(role);
      });

      groups.forEach((group) => {
        let deltaA = 0;
        let deltaB = 0;
        const rows = document.createElement("div");
        rows.className = "bcmp";
        group.rows.forEach((role) => {
          const hasA = a.held.indexOf(role.name) >= 0;
          const hasB = b.held.indexOf(role.name) >= 0;
          // Counting only what scores: a superseded clear is held but paid for
          // by the stronger one above it.
          if (a.has.indexOf(role.name) >= 0) deltaA += role.points;
          if (b.has.indexOf(role.name) >= 0) deltaB += role.points;
          const row = document.createElement("div");
          row.className = "bcmprow" + (hasA === hasB ? " same" : "");
          const mark = (has) => {
            const el = document.createElement("span");
            // Matching states read as "no difference here" rather than as two
            // separate verdicts, so the eye lands on the rows that differ.
            el.className = "cmpcell " + (hasA === hasB ? "eq" : (has ? "yes" : "no"));
            el.textContent = hasA === hasB ? "=" : (has ? "✓" : "✕");
            return el;
          };
          const mid = document.createElement("span");
          mid.className = "cmpname";
          mid.textContent = role.name;
          const val = document.createElement("span");
          val.className = "cmppts";
          val.textContent = String(role.points);
          row.append(mark(hasA), mid, val, mark(hasB));
          rows.appendChild(row);
        });

        const head = document.createElement("div");
        head.className = "bcmpgroup";
        const title = document.createElement("b");
        title.textContent = group.name;
        const diff = document.createElement("span");
        const gap = deltaA - deltaB;
        diff.className = "gdiff " + (gap > 0 ? "up" : (gap < 0 ? "down" : "flat"));
        diff.textContent = deltaA + " vs " + deltaB
          + (gap ? "  (" + (gap > 0 ? "+" : "") + gap + ")" : "  (level)");
        head.append(title, diff);
        out.append(head, rows);
      });
    };
    left.input.addEventListener("input", draw);
    right.input.addEventListener("input", draw);
    draw();
  });
})();
