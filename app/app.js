const DEFAULT_LEADER_BOARD = {
  meta: {
    trade_date: "",
    generated_at_kst: "",
    mode: "",
    session_state: "",
    leader_count: 0,
    sector_count: 0,
    market_bias: "데이터 로딩 대기",
    filtered_etf: ""
  },
  top_sectors: [],
  leaders: []
};

const DEFAULT_CALENDAR = {
  meta: {
    generated_at_kst: "",
    days: 0
  },
  history: []
};

const state = {
  leaderBoard: DEFAULT_LEADER_BOARD,
  calendarHistory: DEFAULT_CALENDAR,
  calendarDate: new Date()
};

const SECTOR_COLOR_MAP = {
  "반도체": "sector-color-yellow",
  "우주": "sector-color-cyan",
  "방산": "sector-color-orange",
  "전력설비": "sector-color-red",
  "전력": "sector-color-red",
  "조선": "sector-color-blue",
  "에너지": "sector-color-green",
  "2차전지": "sector-color-violet",
  "AI": "sector-color-pink",
  "원전": "sector-color-lime",
  "화학": "sector-color-gold",
  "철강": "sector-color-silver",
  "자동차": "sector-color-white",
  "금융": "sector-color-mint",
  "건설": "sector-color-sand",
  "유리기판": "sector-color-cyan",
  "로봇": "sector-color-violet",
  "바이오": "sector-color-pink",
  "미디어": "sector-color-gold",
  "게임": "sector-color-mint"
};

document.addEventListener("DOMContentLoaded", async () => {
  startClock();
  bindTabs();
  bindButtons();
  await loadData();
  syncCalendarDateToTradeDate();
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
      syncCalendarDateToTradeDate();
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
      state.calendarDate = new Date(
        state.calendarDate.getFullYear(),
        state.calendarDate.getMonth() - 1,
        1
      );
      renderCalendar();
    });
  }

  if (today) {
    today.addEventListener("click", () => {
      syncCalendarDateToTradeDate(true);
      renderCalendar();
    });
  }

  if (next) {
    next.addEventListener("click", () => {
      state.calendarDate = new Date(
        state.calendarDate.getFullYear(),
        state.calendarDate.getMonth() + 1,
        1
      );
      renderCalendar();
    });
  }
}

async function loadData(force = false) {
  state.leaderBoard = await safeFetchJson(`../data/leader_board.json`, DEFAULT_LEADER_BOARD, force);
  state.calendarHistory = await safeFetchJson(`../data/sector_calendar_history.json`, DEFAULT_CALENDAR, force);
}

async function safeFetchJson(url, fallback, force = false) {
  try {
    const requestUrl = `${url}?t=${Date.now()}`;
    const response = await fetch(requestUrl, {
      cache: "no-store",
      headers: {
        "Cache-Control": "no-cache"
      }
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    console.warn(`safeFetchJson fallback: ${url}`, error);
    return fallback;
  }
}

function syncCalendarDateToTradeDate(force = false) {
  const tradeDate = state.leaderBoard?.meta?.trade_date;
  const parsed = parseYmdLocal(tradeDate);
  if (!parsed) {
    if (force) {
      const now = new Date();
      state.calendarDate = new Date(now.getFullYear(), now.getMonth(), 1);
    }
    return;
  }

  if (
    force ||
    !state.calendarDate ||
    state.calendarDate.getFullYear() !== parsed.getFullYear() ||
    state.calendarDate.getMonth() !== parsed.getMonth()
  ) {
    state.calendarDate = new Date(parsed.getFullYear(), parsed.getMonth(), 1);
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
  setText("heroSession", buildHeroSessionText(meta));
  setText("heroSectorCount", `${meta.sector_count ?? "-"}`);
  setText("heroMarketBias", meta.market_bias || "-");
  setText("heroLeaderCount", `${meta.leader_count ?? "-"}`);
  setText("heroFilteredEtf", meta.filtered_etf || "ETF 제외 적용");
  setText("heroHistoryCount", `${state.calendarHistory.meta?.days ?? "-"}`);
  setText(
    "heroUpdatedAt",
    meta.generated_at_kst || state.calendarHistory.meta?.generated_at_kst || "-"
  );
}

function buildHeroSessionText(meta) {
  const parts = [];
  if (meta.mode) parts.push(meta.mode);
  if (meta.session_state) parts.push(meta.session_state);
  return parts.length ? parts.join(" / ") : "-";
}

function renderLeaders() {
  const wrap = document.getElementById("leadersList");
  if (!wrap) return;

  const leaders = Array.isArray(state.leaderBoard.leaders) ? state.leaderBoard.leaders : [];
  if (!leaders.length) {
    wrap.innerHTML = `<div class="empty-state">표시할 주도주 데이터가 없습니다.</div>`;
    return;
  }

  wrap.innerHTML = leaders.map((item) => {
    const highlightClass = getHighlightClass(item);
    const changeClass = Number(item.change_pct) >= 0 ? "up" : "down";
    const code = item.code || item.ticker || "-";
    const sectorName = getFinalSectorName(item);
    const tradingValue = item.trading_value_okrw ?? item.trading_value_eok ?? 0;

    return `
      <div class="leader-card">
        <div class="rank-badge">#${item.rank ?? "-"}</div>
        <div class="leader-main">
          <div class="leader-name ${highlightClass}">${escapeHtml(item.name || "-")}</div>
          <div class="leader-meta">${escapeHtml(code)} · 점수 ${num(item.score, 0)} · 거래량 ${formatNumber(item.volume)}</div>
        </div>
        <div class="leader-sector ${highlightClass} ${getSectorColorClass(sectorName)}">${escapeHtml(sectorName)}</div>
        <div class="metric-box">
          <div class="metric-label">등락률</div>
          <div class="metric-value ${changeClass}">${signedPercent(item.change_pct)}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">거래대금</div>
          <div class="metric-value">${formatEok(tradingValue)}</div>
        </div>
      </div>
    `;
  }).join("");
}

function renderSectors() {
  const wrap = document.getElementById("sectorCards");
  if (!wrap) return;

  const sectors = Array.isArray(state.leaderBoard.top_sectors) ? state.leaderBoard.top_sectors : [];
  if (!sectors.length) {
    wrap.innerHTML = `<div class="empty-state">표시할 주도섹터 데이터가 없습니다.</div>`;
    return;
  }

  wrap.innerHTML = sectors.map((item, index) => {
    const score = Number(item.score) || 0;
    const width = Math.max(10, Math.min(score, 100));
    const bandClass =
      score >= 90 ? "band-90" :
      score >= 80 ? "band-80" :
      score >= 70 ? "band-70" : "band-low";

    const sectorName = item.sector || "-";
    const textColorClass = index <= 2 ? "sector-color-yellow" : "sector-color-white";
    const leaders = getSectorLeaderItems(sectorName).slice(0, 3);

    const leadersHtml = leaders.length
      ? `
        <div class="sector-leader-list">
          ${leaders.map((leader, leaderIndex) => `
            <div class="sector-leader-item">
              <div class="sector-leader-left">
                <div class="sector-leader-rank">${leaderIndex + 1}</div>
                <div class="sector-leader-main">
                  <div class="sector-leader-name ${textColorClass}">${escapeHtml(leader.name || "-")}</div>
                  <div class="sector-leader-meta">${escapeHtml(leader.code || leader.ticker || "-")} · ${formatEok(leader.trading_value_okrw ?? leader.trading_value_eok ?? 0)}</div>
                </div>
              </div>
              <div class="sector-leader-change ${Number(leader.change_pct) >= 0 ? "up" : "down"}">${signedPercent(leader.change_pct)}</div>
            </div>
          `).join("")}
        </div>
      `
      : "";

    return `
      <div class="sector-card">
        <div class="sector-top">
          <div class="sector-name ${textColorClass}">${escapeHtml(sectorName)}</div>
          <div class="sector-score">${num(score, 0)}</div>
        </div>
        <div class="score-bar">
          <div class="score-bar-fill ${bandClass}" style="width:${width}%">${num(score, 0)}</div>
        </div>
        <div class="sector-sub">
          <span>주도주 ${num(item.leaders, 0)}개</span>
          <span>평균 ${signedPercent(item.avg_change_pct)}</span>
        </div>
        ${leadersHtml}
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
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0).getDate();

  const historyMap = new Map((history || []).map((item) => [item.date, item]));

  const cells = [];
  const firstWeekday = firstDay.getDay();
  const mondayOffset = firstWeekday === 0 ? 6 : firstWeekday - 1;

  for (let i = 0; i < mondayOffset; i += 1) {
    cells.push({ empty: true, day: "", sectors: [] });
  }

  for (let day = 1; day <= lastDay; day += 1) {
    const d = new Date(year, month, day);
    const weekday = d.getDay();

    if (weekday === 0 || weekday === 6) continue;

    const dateStr = formatDate(d);
    const found = historyMap.get(dateStr);

    cells.push({
      empty: false,
      date: dateStr,
      day,
      sectors: Array.isArray(found?.sectors) ? found.sectors : []
    });
  }

  return cells;
}

function renderCalendarCell(item) {
  if (item.empty) {
    return `<div class="calendar-cell" style="visibility:hidden;"></div>`;
  }

  const sectors = (item.sectors || []).slice(0, 3);
  const body = sectors.length
    ? sectors
        .map((sector) => {
          const name = sector.name || "-";
          const colorClass = getSectorColorClass(name);
          return `<div class="calendar-sector-item ${colorClass}">${escapeHtml(name)} (${num(sector.score, 0)})</div>`;
        })
        .join("")
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

  const history = Array.isArray(state.calendarHistory.history) ? state.calendarHistory.history : [];
  const recent = history.slice(-20);
  const counts = {};
  const lastSeen = {};

  recent.forEach((day, dayIndex) => {
    (day.sectors || []).forEach((sector) => {
      if ((Number(sector.score) || 0) >= 80) {
        const name = sector.name;
        counts[name] = (counts[name] || 0) + 1;
        lastSeen[name] = dayIndex;
      }
    });
  });

  const rows = Object.entries(counts)
    .map(([name, count]) => {
      const unseenDays = lastSeen[name] === undefined ? 999 : (recent.length - 1 - lastSeen[name]);
      const adjusted = Math.max(0, count - (unseenDays >= 3 ? 1 : 0));
      return { name, count: adjusted };
    })
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, "ko"))
    .slice(0, 8);

  if (!rows.length) {
    wrap.innerHTML = `<div class="empty-state">최근 20거래일 카운트 데이터가 없습니다.</div>`;
    return;
  }

  const summaryHtml = `
    <div class="count-summary-grid">
      <div class="count-summary-card">
        <div class="count-summary-label">집계 기간</div>
        <div class="count-summary-value">최근 20거래일</div>
        <div class="count-summary-sub">3거래일 미등장 시 -1 감산</div>
      </div>
      <div class="count-summary-card">
        <div class="count-summary-label">히스토리 일수</div>
        <div class="count-summary-value">${history.length}일</div>
        <div class="count-summary-sub">최대 7개 섹터 표시</div>
      </div>
    </div>
  `;

  const rowsHtml = rows.map((row, idx) => {
    const colorClass = getSectorColorClass(row.name);
    const activeCount = Math.max(0, Math.min(20, row.count));
    const cells = Array.from({ length: 20 }, (_, i) =>
      `<span class="count-dot ${i < activeCount ? "active" : ""} ${colorClass}"></span>`
    ).join("");

    return `
      <div class="count-graph-row">
        <div class="count-graph-rank">${idx + 1}.</div>
        <div class="count-graph-name ${colorClass}">${escapeHtml(row.name)}</div>
        <div class="count-graph-track">${cells}</div>
        <div class="count-graph-value">${row.count}회</div>
      </div>
    `;
  }).join("");

  wrap.innerHTML = `
    ${summaryHtml}
    <div class="count-graph-panel">
      <div class="count-graph-caption">최근 20거래일 상위 섹터(80점 이상) 출현 횟수 · 최근성 감산 반영</div>
      <div class="count-graph-list">${rowsHtml}</div>
    </div>
  `;
}

function renderTodaySectorSummary() {
  const wrap = document.getElementById("todaySectorSummary");
  if (!wrap) return;

  const sectors = (state.leaderBoard.top_sectors || []).slice(0, 3);
  if (!sectors.length) {
    wrap.innerHTML = `<div class="empty-state">오늘의 주도섹터 요약이 없습니다.</div>`;
    return;
  }

  wrap.innerHTML = sectors.map((item, idx) => {
    const sectorName = item.sector || "-";
    const colorClass = getSectorColorClass(sectorName);
    const leaderNames = getSectorLeaderItems(sectorName).slice(0, 3).map((x) => x.name).filter(Boolean);
    const namesText = leaderNames.length ? ` (${leaderNames.map(escapeHtml).join(", ")})` : "";

    return `
      <div class="count-item">
        <div class="count-title ${colorClass}">${idx + 1}. ${escapeHtml(sectorName)}${namesText}</div>
        <div class="count-body">점수 ${num(item.score, 0)} / 주도주 ${num(item.leaders, 0)}개 / 평균 ${signedPercent(item.avg_change_pct)}</div>
      </div>
    `;
  }).join("");
}

function getFinalSectorName(item) {
  return item.sector || item.sector1 || item.sector2 || "-";
}

function getSectorLeaderItems(sectorName) {
  const leaders = Array.isArray(state.leaderBoard.leaders) ? state.leaderBoard.leaders : [];
  return leaders
    .filter((item) => getFinalSectorName(item) === sectorName)
    .sort((a, b) => (Number(b.score) || 0) - (Number(a.score) || 0))
    .slice(0, 3);
}

function getSectorColorClass(sectorName) {
  return SECTOR_COLOR_MAP[sectorName] || "sector-color-default";
}

function getHighlightClass(item) {
  const trading = Number(item.trading_value_okrw ?? item.trading_value_eok) || 0;
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

function parseYmdLocal(text) {
  if (!text || typeof text !== "string") return null;
  const m = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
