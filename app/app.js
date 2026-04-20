const DEFAULT_LEADER_BOARD = {
  meta: {
    trade_date: "2026-04-20",
    generated_at_kst: "2026-04-20 15:30:00",
    mode: "sample_scoring",
    session_state: "kr_open",
    leader_count: 0,
    sector_count: 0,
    market_bias: "데이터 로딩 대기",
    filtered_etf: "ETF 제외 기준 준비중"
  },
  top_sectors: [],
  leaders: []
};

const DEFAULT_CALENDAR = {
  meta: {
    generated_at_kst: "2026-04-20 15:30:00",
    days: 0
  },
  history: []
};

const state = {
  leaderBoard: DEFAULT_LEADER_BOARD,
  calendarHistory: DEFAULT_CALENDAR,
  calendarDate: new Date()
};

document.addEventListener("DOMContentLoaded", async () => {
  startClock();
  bindTabs();
  bindButtons();
  await loadData();
  renderAll();
});

function startClock() {
  const el = document.getElementById("krClock");
  if (!el) return;

  const tick = () => {
    const now = new Date();
    const value = now.toLocaleString("sv-SE", {
      timeZone: "Asia/Seoul",
      hour12: false
    });
    el.textContent = `KR ${value}`;
  };

  tick();
  setInterval(tick, 1000);
}

function bindTabs() {
  const buttons = document.querySelectorAll(".tab-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      const tab = btn.dataset.tab;
      document.querySelectorAll(".screen").forEach((screen) => {
        screen.classList.remove("active");
      });

      const target = document.getElementById(`screen-${tab}`);
      if (target) target.classList.add("active");
    });
  });
}

function bindButtons() {
  const refreshBtn = document.getElementById("refreshBtn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", async () => {
      await loadData(true);
      renderAll();
    });
  }

  bindCalendarNav("prevMonthBtn", "todayMonthBtn", "nextMonthBtn");
}

function bindCalendarNav(prevId, todayId, nextId) {
  const prev = document.getElementById(prevId);
  const today = document.getElementById(todayId);
  const next = document.getElementById(nextId);

  if (prev) {
    prev.addEventListener("click", () => {
      state.calendarDate.setMonth(state.calendarDate.getMonth() - 1);
      renderCalendar();
    });
  }

  if (today) {
    today.addEventListener("click", () => {
      state.calendarDate = new Date();
      renderCalendar();
    });
  }

  if (next) {
    next.addEventListener("click", () => {
      state.calendarDate.setMonth(state.calendarDate.getMonth() + 1);
      renderCalendar();
    });
  }
}

async function loadData(force = false) {
  state.leaderBoard = await safeFetchJson("../data/leader_board.json", DEFAULT_LEADER_BOARD, force);
  state.calendarHistory = await safeFetchJson("../data/sector_calendar_history.json", DEFAULT_CALENDAR, force);
}

async function safeFetchJson(url, fallback, force = false) {
  try {
    const requestUrl = force ? `${url}?t=${Date.now()}` : url;
    const response = await fetch(requestUrl, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    return fallback;
  }
}

function renderAll() {
  renderHero();
  renderLeaders();
  renderSectors();
  renderCalendar();
  renderRecentCounts();
  renderTodaySectorSummary();
}

function renderHero() {
  const meta = state.leaderBoard.meta || {};
  setText("heroTradeDate", meta.trade_date || "-");
  setText("heroSession", `${meta.mode || "-"} / ${meta.session_state || "-"}`);
  setText("heroSectorCount", `${meta.sector_count ?? "-"}`);
  setText("heroMarketBias", meta.market_bias || "-");
  setText("heroLeaderCount", `${meta.leader_count ?? "-"}`);
  setText("heroFilteredEtf", meta.filtered_etf || "-");
  setText("heroHistoryCount", `${state.calendarHistory.meta?.days ?? "-"}`);
  setText("heroUpdatedAt", meta.generated_at_kst || state.calendarHistory.meta?.generated_at_kst || "-");
}

function renderLeaders() {
  const wrap = document.getElementById("leadersList");
  if (!wrap) return;

  const leaders = state.leaderBoard.leaders || [];
  if (!leaders.length) {
    wrap.innerHTML = `<div class="empty-state">표시할 주도주 데이터가 없습니다.</div>`;
    return;
  }

  wrap.innerHTML = leaders.map((item) => {
    const highlightClass = getHighlightClass(item);
    const changeClass = Number(item.change_pct) >= 0 ? "up" : "down";

    return `
      <div class="leader-card">
        <div class="rank-badge">#${item.rank ?? "-"}</div>
        <div class="leader-main">
          <div class="leader-name ${highlightClass}">${escapeHtml(item.name || "-")}</div>
          <div class="leader-meta">${escapeHtml(item.ticker || "-")} · 점수 ${num(item.score, 0)} · 거래량 ${formatNumber(item.volume)}</div>
        </div>
        <div class="leader-sector ${highlightClass}">${escapeHtml(item.sector || "-")}</div>
        <div class="metric-box">
          <div class="metric-label">등락률</div>
          <div class="metric-value ${changeClass}">${signedPercent(item.change_pct)}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">거래대금</div>
          <div class="metric-value">${formatEok(item.trading_value_eok)}</div>
        </div>
      </div>
    `;
  }).join("");
}

function renderSectors() {
  const wrap = document.getElementById("sectorCards");
  if (!wrap) return;

  const sectors = state.leaderBoard.top_sectors || [];
  if (!sectors.length) {
    wrap.innerHTML = `<div class="empty-state">표시할 주도섹터 데이터가 없습니다.</div>`;
    return;
  }

  wrap.innerHTML = sectors.map((item) => {
    const score = Number(item.score) || 0;
    const width = Math.max(10, Math.min(score, 100));
    const bandClass = score >= 90 ? "band-90" : score >= 80 ? "band-80" : score >= 70 ? "band-70" : "band-low";

    return `
      <div class="sector-card">
        <div class="sector-top">
          <div class="sector-name">${escapeHtml(item.sector || "-")}</div>
          <div class="sector-score">${num(score, 0)}</div>
        </div>
        <div class="score-bar">
          <div class="score-bar-fill ${bandClass}" style="width:${width}%">${num(score, 0)}</div>
        </div>
        <div class="sector-sub">
          <span>주도주 ${num(item.leaders, 0)}개</span>
          <span>평균 ${signedPercent(item.avg_change_pct)}</span>
        </div>
      </div>
    `;
  }).join("");
}

function renderCalendar() {
  setWeekdays("weekdayGrid");
  const label = document.getElementById("calendarMonthLabel");
  const grid = document.getElementById("calendarGrid");
  if (!label || !grid) return;

  const current = state.calendarDate;
  label.textContent = `${current.getFullYear()}년 ${current.getMonth() + 1}월`;

  const cells = buildWeekdayMonthCells(current, state.calendarHistory.history || []);
  grid.innerHTML = cells.map(renderCalendarCell).join("");
}

function setWeekdays(targetId) {
  const el = document.getElementById(targetId);
  if (!el) return;
  el.innerHTML = ["월", "화", "수", "목", "금"]
    .map((d) => `<div class="weekday-cell">${d}</div>`)
    .join("");
}

function buildWeekdayMonthCells(dateObj, history) {
  const year = dateObj.getFullYear();
  const month = dateObj.getMonth();
  const lastDay = new Date(year, month + 1, 0).getDate();
  const map = new Map((history || []).map((item) => [item.date, item]));
  const cells = [];

  for (let day = 1; day <= lastDay; day += 1) {
    const d = new Date(year, month, day);
    const weekday = d.getDay();
    if (weekday === 0 || weekday === 6) continue;

    const dateStr = formatDate(d);
    const found = map.get(dateStr);

    cells.push({
      date: dateStr,
      day,
      sectors: found?.sectors || []
    });
  }

  return cells;
}

function renderCalendarCell(item) {
  const sectors = (item.sectors || []).slice(0, 3);
  const body = sectors.length
    ? sectors.map((sector) => `<div class="calendar-sector-item">${escapeHtml(sector.name)} (${num(sector.score, 0)})</div>`).join("")
    : `<div class="calendar-sector-item" style="color:#8fa0bf;">기록 없음</div>`;

  return `
    <div class="calendar-cell">
      <div class="calendar-day">${item.day}</div>
      <div class="calendar-sector-list">${body}</div>
    </div>
  `;
}

function renderRecentCounts() {
  const wrap = document.getElementById("recentCounts");
  if (!wrap) return;

  const history = state.calendarHistory.history || [];
  const recent = history.slice(-10);
  const counts = {};

  recent.forEach((day) => {
    (day.sectors || []).forEach((sector) => {
      if ((Number(sector.score) || 0) >= 80) {
        counts[sector.name] = (counts[sector.name] || 0) + 1;
      }
    });
  });

  const rows = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);

  if (!rows.length) {
    wrap.innerHTML = `<div class="empty-state">최근 10일 카운트 데이터가 없습니다.</div>`;
    return;
  }

  wrap.innerHTML = rows.map(([name, count]) => `
    <div class="count-item">
      <div class="count-title">${escapeHtml(name)}</div>
      <div class="count-body">최근 10일 중 ${count}회 상위 기록</div>
    </div>
  `).join("");
}

function renderTodaySectorSummary() {
  const wrap = document.getElementById("todaySectorSummary");
  if (!wrap) return;

  const sectors = (state.leaderBoard.top_sectors || []).slice(0, 3);
  if (!sectors.length) {
    wrap.innerHTML = `<div class="empty-state">오늘의 주도섹터 요약이 없습니다.</div>`;
    return;
  }

  wrap.innerHTML = sectors.map((item, idx) => `
    <div class="count-item">
      <div class="count-title">${idx + 1}. ${escapeHtml(item.sector)}</div>
      <div class="count-body">점수 ${num(item.score, 0)} / 주도주 ${num(item.leaders, 0)}개 / 평균 ${signedPercent(item.avg_change_pct)}</div>
    </div>
  `).join("");
}

function getHighlightClass(item) {
  const trading = Number(item.trading_value_eok) || 0;
  const change = Number(item.change_pct) || 0;
  if (trading >= 3000 && change >= 5) return "highlight-strong";
  if (trading >= 1000 && change >= 5) return "highlight-mid";
  return "";
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function num(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toFixed(digits);
}

function signedPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const n = Number(value);
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function formatEok(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${Math.round(Number(value)).toLocaleString("ko-KR")}억`;
}

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString("ko-KR");
}

function formatDate(date) {
  const y = date.getFullYear();
  const m = `${date.getMonth() + 1}`.padStart(2, "0");
  const d = `${date.getDate()}`.padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
