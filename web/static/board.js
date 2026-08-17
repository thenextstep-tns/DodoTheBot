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
  const counter = document.getElementById("bcount");
  const compareBtn = document.getElementById("bcompare");
  const compareUI = document.getElementById("bcompareui");

  // Podium colours are the first three *overall*, not the first three of
  // whatever the filter happens to show: a search must not invent a winner.
  const podium = ["gold", "silver", "bronze"];
  players.forEach((p, i) => { p.place = i; });

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
    const shown = players.filter((p) => !q || p.name.toLowerCase().includes(q));
    body.innerHTML = "";
    counter.textContent = q ? shown.length + " of " + players.length : "";
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
      tr.className = "brow" + (player.place < 3 ? " " + podium[player.place] : "");

      const pos = document.createElement("td");
      pos.className = "pos";
      pos.textContent = player.place < 3 ? ["\u{1F947}", "\u{1F948}", "\u{1F949}"][player.place]
                                         : String(player.place + 1);

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

      const rank = document.createElement("td");
      rank.className = "rk";
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
      rank.appendChild(pill);

      const chev = document.createElement("td");
      chev.className = "bchev";
      chev.textContent = "▸";

      tr.append(pos, who, pts, rank, chev);
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

  search.addEventListener("input", render);
  render();

  // --- compare -------------------------------------------------------------
  // Every earnable clear, marked per player. Showing only what they hold would
  // answer "who has more" but not "what is one of them missing", which is the
  // question a comparison is actually for.
  const option = (selected) => {
    const sel = document.createElement("select");
    players.forEach((p, i) => {
      const o = document.createElement("option");
      o.value = String(i);
      o.textContent = p.name;
      sel.appendChild(o);
    });
    sel.selectedIndex = Math.min(selected, players.length - 1);
    return sel;
  };

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
    const left = option(0);
    const right = option(1);
    pickers.append(left, document.createTextNode("vs"), right);
    const out = document.createElement("div");
    compareUI.append(pickers, out);

    const draw = () => {
      const a = players[Number(left.value)];
      const b = players[Number(right.value)];
      out.innerHTML = "";
      const head = document.createElement("div");
      head.className = "bcmphead";
      head.innerHTML = "";
      [a, b].forEach((p) => {
        const cell = document.createElement("div");
        cell.innerHTML = "";
        const n = document.createElement("b");
        n.textContent = p.name;
        const s = document.createElement("span");
        s.className = "muted small";
        s.textContent = " " + p.score + " pts · " + p.rank;
        cell.append(n, s);
        head.appendChild(cell);
      });
      out.appendChild(head);

      const list = document.createElement("div");
      list.className = "bcmp";
      let differing = 0;
      roles.forEach((role) => {
        const hasA = a.held.indexOf(role.name) >= 0;
        const hasB = b.held.indexOf(role.name) >= 0;
        if (hasA && hasB) return;     // shared ground is not the interesting part
        differing += 1;
        const row = document.createElement("div");
        row.className = "bcmprow";
        const l = document.createElement("span");
        l.className = "cmpcell " + (hasA ? "yes" : "no");
        l.textContent = hasA ? "✓" : "✕";
        const mid = document.createElement("span");
        mid.className = "cmpname";
        mid.textContent = role.name;
        const val = document.createElement("span");
        val.className = "cmppts";
        val.textContent = role.points;
        const r = document.createElement("span");
        r.className = "cmpcell " + (hasB ? "yes" : "no");
        r.textContent = hasB ? "✓" : "✕";
        row.append(l, mid, val, r);
        list.appendChild(row);
      });
      if (!differing) {
        const same = document.createElement("p");
        same.className = "muted";
        same.textContent = "These two hold exactly the same clears.";
        list.appendChild(same);
      }
      out.appendChild(list);
    };
    left.addEventListener("change", draw);
    right.addEventListener("change", draw);
    draw();
  });
})();
