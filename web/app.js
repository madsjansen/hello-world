const RATING_COLOR = {
  "Korrekt": "var(--korrekt)",
  "Delvist korrekt": "var(--delvist)",
  "Misvisende": "var(--misvisende)",
  "Forkert": "var(--forkert)",
  "Ikke verificerbar": "var(--ukendt)",
};

let DATA = null;

function scoreColor(score) {
  if (score === null || score === undefined) return "var(--ukendt)";
  if (score >= 75) return "var(--korrekt)";
  if (score >= 50) return "var(--delvist)";
  if (score >= 25) return "var(--misvisende)";
  return "var(--forkert)";
}

function breakdownBar(breakdown) {
  const order = ["Korrekt", "Delvist korrekt", "Misvisende", "Forkert", "Ikke verificerbar"];
  const total = order.reduce((s, r) => s + (breakdown[r] || 0), 0) || 1;
  const segs = order
    .filter((r) => breakdown[r])
    .map((r) => `<span style="width:${(100 * breakdown[r]) / total}%;background:${RATING_COLOR[r]}" title="${r}: ${breakdown[r]}"></span>`)
    .join("");
  return `<div class="bar">${segs}</div>`;
}

function renderRanking(list) {
  if (!list.length) return `<p class="empty">Ingen data endnu. Kør pipelinen eller <code>seed-demo</code>.</p>`;
  return list.map((item, i) => {
    const score = item.score === null ? "–" : item.score;
    const suffix = item.score === null ? "" : "%";
    return `
      <div class="row">
        <div class="rank">${i + 1}</div>
        <div class="who">
          <div class="name">${item.name}</div>
          ${item.party && item.party !== item.name ? `<div class="party">${item.party}</div>` : ""}
        </div>
        <div class="score">
          <div class="val" style="color:${scoreColor(item.score)}">${score}${suffix}</div>
          <div class="count">${item.verifiable} verificerbare / ${item.total} i alt</div>
        </div>
        ${breakdownBar(item.breakdown)}
      </div>`;
  }).join("");
}

function renderClaims(claims) {
  if (!claims.length) return `<p class="empty">Ingen påstande endnu.</p>`;
  return claims.map((c) => {
    const color = RATING_COLOR[c.rating] || "var(--ukendt)";
    const sources = (c.sources || [])
      .map((s) => `<a href="${s.url}" target="_blank" rel="noopener">${s.title || s.url}</a>`)
      .join("");
    return `
      <div class="claim" style="border-left-color:${color}">
        <div class="head">
          <span class="meta">${c.politician} (${c.party}) · ${c.meeting?.date || ""}</span>
          <span class="badge" style="background:${color};color:#0f1419">${c.rating}</span>
        </div>
        <div class="text">${c.claim}</div>
        <div class="expl">${c.explanation || ""}</div>
        <div class="sources">${sources}</div>
      </div>`;
  }).join("");
}

function show(view) {
  const board = document.getElementById("board");
  if (!DATA) { board.innerHTML = `<p class="empty">Indlæser …</p>`; return; }
  if (view === "claims") board.innerHTML = renderClaims(DATA.claims);
  else board.innerHTML = renderRanking(DATA[view]);
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === view));
}

document.querySelectorAll(".tab").forEach((tab) =>
  tab.addEventListener("click", () => show(tab.dataset.view))
);

fetch("leaderboard.json")
  .then((r) => r.json())
  .then((data) => { DATA = data; show("politicians"); })
  .catch(() => {
    document.getElementById("board").innerHTML =
      `<p class="empty">Kunne ikke indlæse <code>leaderboard.json</code>. Kør <code>build-site</code> først.</p>`;
  });
