const state = {
  board: null,
  history: null,
  currentTab: 'dashboard',
  calendarDate: new Date(),
  krCalendarDate: new Date(),
};

function fmtNumber(v){
  return Number(v || 0).toLocaleString('ko-KR');
}

function fmtPercent(v){
  const n = Number(v || 0);
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
}

function clsByChange(v){
  const n = Number(v || 0);
  if(n > 0) return 'up';
  if(n < 0) return 'down';
  return 'neutral';
}

function ymd(dateObj){
  const y = dateObj.getFullYear();
  const m = String(dateObj.getMonth() + 1).padStart(2, '0');
  const d = String(dateObj.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function updateKRClock(){
  const now = new Date();
  const kr = new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).formatToParts(now);
  const pick = type => kr.find(p => p.type === type)?.value || '--';
  document.getElementById('krClock').textContent = `KR ${pick('month')}-${pick('day')} ${pick('hour')}:${pick('minute')}:${pick('second')}`;
}

async function loadJson(url){
  const res = await fetch(`${url}?v=${Date.now()}`, { cache: 'no-store' });
  if(!res.ok) throw new Error(`${url} load failed: ${res.status}`);
  return await res.json();
}

async function loadAll(){
  state.board = await loadJson('../data/leader_board.json');
  state.history = await loadJson('../data/sector_calendar_history.json');
}

function setHero(){
  const board = state.board || {};
  const hist = state.history || {};
  document.getElementById('heroTradeDate').textContent = board?.meta?.trade_date || '-';
  document.getElementById('heroSession').textContent = board?.meta?.session_state || '-';
  document.getElementById('heroSectorCount').textContent = fmtNumber((board?.top_sectors || []).length);
  document.getElementById('heroMarketBias').textContent = board?.summary?.market_bias || '-';
  document.getElementById('heroLeaderCount').textContent = fmtNumber((board?.leaders || []).length);
  document.getElementById('heroFilteredEtf').textContent = `ETF 필터 ${fmtNumber(board?.summary?.filtered_etf_stock_count || 0)}개`;
  document.getElementById('heroHistoryCount').textContent = fmtNumber(hist?.meta?.history_count || 0);
  document.getElementById('heroUpdatedAt').textContent = hist?.meta?.updated_at || '-';
}

function renderLeaders(){
  const box = document.getElementById('leadersList');
  const rows = state.board?.leaders || [];
  if(!rows.length){
    box.innerHTML = '<div class="empty">주도주 데이터가 없습니다.</div>';
    return;
  }
  box.innerHTML = rows.map((row, idx) => `
    <div class="item-card">
      <div class="item-top">
        <div>
          <div class="item-name">${idx + 1}. ${row.name}</div>
          <div class="item-meta">
            <span class="pill">${row.sector1 || '-'}</span>
            <span class="pill">${row.market || '-'}</span>
            <span class="pill">${row.code || '-'}</span>
          </div>
        </div>
        <div style="text-align:right">
          <div class="score">${(Number(row.stock_score || row.score || 0)).toFixed(1)}</div>
          <div class="change ${clsByChange(row.change_pct)}">${fmtPercent(row.change_pct)}</div>
        </div>
      </div>
      <div class="item-meta">
        <span>거래대금 ${fmtNumber(row.trading_value_okrw)}억</span>
        <span>거래량 ${fmtNumber(row.volume || 0)}</span>
        <span>가격 ${fmtNumber(row.price || 0)}</span>
      </div>
    </div>
  `).join('');
}

function renderSectors(){
  const box = document.getElementById('sectorCards');
  const rows = state.board?.top_sectors || [];
  if(!rows.length){
    box.innerHTML = '<div class="empty">섹터 데이터가 없습니다.</div>';
    return;
  }
  box.innerHTML = rows.map((row, idx) => `
    <div class="sector-card">
      <div class="sector-top">
        <div>
          <div class="sector-name">${idx + 1}. ${row.sector1}</div>
          <div class="sector-meta">
            <span>종목수 ${fmtNumber(row.stock_count || 0)}</span>
            <span>평균등락 ${fmtPercent(row.sector_avg_change_pct || 0)}</span>
          </div>
        </div>
        <div style="text-align:right">
          <div class="score">${Number(row.sector_score || 0).toFixed(1)}</div>
          <div class="item-meta">거래대금 ${fmtNumber(row.sector_total_trading_value || 0)}억</div>
        </div>
      </div>
    </div>
  `).join('');
}

function historyRows(){
  return Array.isArray(state.history?.history) ? state.history.history.slice().sort((a,b) => String(a.date).localeCompare(String(b.date))) : [];
}

function buildWeekdayGrid(targetId){
  document.getElementById(targetId).innerHTML = ['월','화','수','목','금'].map(d => `<div class="weekday">${d}</div>`).join('');
}

function renderMonthCalendar(targetMonthDate, monthLabelId, gridId, sourceRows){
  const monthLabel = document.getElementById(monthLabelId);
  const calendarGrid = document.getElementById(gridId);

  const current = targetMonthDate;
  const year = current.getFullYear();
  const month = current.getMonth();

  monthLabel.textContent = `${year}년 ${month + 1}월`;

  const firstDay = new Date(year, month, 1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstWeekdayMon0 = (firstDay.getDay() + 6) % 7;
  const rowsMap = new Map((sourceRows || []).map(row => [row.date, row]));
  const todayStr = ymd(new Date());

  const cells = [];
  const leadingBlanks = Math.min(firstWeekdayMon0, 5);
  for(let i = 0; i < leadingBlanks; i++) cells.push({ blank: true });

  for(let d = 1; d <= daysInMonth; d++){
    const dateObj = new Date(year, month, d);
    const day = dateObj.getDay();
    if(day >= 1 && day <= 5){
      cells.push({ dateObj });
    }
  }
  while(cells.length % 5 !== 0) cells.push({ blank: true });

  calendarGrid.innerHTML = cells.map(cell => {
    if(cell.blank) return '<div class="day-cell blank"></div>';
    const key = ymd(cell.dateObj);
    const row = rowsMap.get(key);
    const sectors = Array.isArray(row?.top_sectors) ? row.top_sectors.slice(0, 3) : [];
    return `
      <div class="day-cell ${key === todayStr ? 'today' : ''}">
        <div class="day-num">
          <span>${cell.dateObj.getDate()}</span>
          ${key === todayStr ? '<span class="day-badge">TODAY</span>' : ''}
        </div>
        ${sectors.length ? sectors.map(sec => `<div class="day-chip">${sec.sector1}</div>`).join('') : '<div class="sub">기록 없음</div>'}
      </div>
    `;
  }).join('');
}

function renderCalendar(){
  buildWeekdayGrid('weekdayGrid');
  renderMonthCalendar(state.calendarDate, 'calendarMonthLabel', 'calendarGrid', historyRows());
}

function renderKrCalendar(){
  buildWeekdayGrid('krWeekdayGrid');
  renderMonthCalendar(state.krCalendarDate, 'krCalendarMonthLabel', 'krCalendarGrid', []);
}

function recent10DayCounts(){
  const rows = historyRows().slice(-10);
  const counts = new Map();
  rows.forEach(day => {
    (day.top_sectors || []).forEach(sec => {
      const score = Number(sec.sector_score || 0);
      if(score < 80) return;
      const name = sec.sector1 || '기타';
      counts.set(name, (counts.get(name) || 0) + 1);
    });
  });
  return Array.from(counts.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((a,b) => b.count - a.count || a.name.localeCompare(b.name, 'ko'));
}

function renderRecentCounts(){
  const box = document.getElementById('recentCounts');
  const rows = recent10DayCounts();
  if(!rows.length){
    box.innerHTML = '<div class="empty">카운트 데이터가 없습니다.</div>';
    return;
  }
  box.innerHTML = rows.slice(0, 10).map((row, idx) => `
    <div class="count-card">
      <div class="count-top">
        <strong>${idx + 1}. ${row.name}</strong>
        <strong>${row.count}회</strong>
      </div>
    </div>
  `).join('');
}

function renderTodaySectorSummary(){
  const box = document.getElementById('todaySectorSummary');
  const latest = historyRows().slice(-1)[0];
  const rows = latest?.top_sectors || [];
  if(!rows.length){
    box.innerHTML = '<div class="empty">오늘 섹터 데이터가 없습니다.</div>';
    return;
  }
  box.innerHTML = rows.slice(0, 8).map((row, idx) => `
    <div class="count-card">
      <div class="count-top">
        <strong>${idx + 1}. ${row.sector1}</strong>
        <strong>${Number(row.sector_score || 0).toFixed(1)}</strong>
      </div>
    </div>
  `).join('');
}

function bindTabs(){
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      state.currentTab = tab;
      document.querySelectorAll('.tab-btn').forEach(x => x.classList.toggle('active', x.dataset.tab === tab));
      document.querySelectorAll('.screen').forEach(x => x.classList.toggle('active', x.id === `screen-${tab}`));
    });
  });
}

function bindCalendarNav(){
  document.getElementById('prevMonthBtn').addEventListener('click', () => {
    state.calendarDate = new Date(state.calendarDate.getFullYear(), state.calendarDate.getMonth() - 1, 1);
    renderCalendar();
  });
  document.getElementById('todayMonthBtn').addEventListener('click', () => {
    state.calendarDate = new Date();
    renderCalendar();
  });
  document.getElementById('nextMonthBtn').addEventListener('click', () => {
    state.calendarDate = new Date(state.calendarDate.getFullYear(), state.calendarDate.getMonth() + 1, 1);
    renderCalendar();
  });

  document.getElementById('krPrevMonthBtn').addEventListener('click', () => {
    state.krCalendarDate = new Date(state.krCalendarDate.getFullYear(), state.krCalendarDate.getMonth() - 1, 1);
    renderKrCalendar();
  });
  document.getElementById('krTodayMonthBtn').addEventListener('click', () => {
    state.krCalendarDate = new Date();
    renderKrCalendar();
  });
  document.getElementById('krNextMonthBtn').addEventListener('click', () => {
    state.krCalendarDate = new Date(state.krCalendarDate.getFullYear(), state.krCalendarDate.getMonth() + 1, 1);
    renderKrCalendar();
  });
}

async function refreshAll(){
  try{
    await loadAll();
    setHero();
    renderLeaders();
    renderSectors();
    renderCalendar();
    renderRecentCounts();
    renderTodaySectorSummary();
    renderKrCalendar();
  }catch(err){
    console.error(err);
    alert('데이터 로딩 실패: leader_board.json / sector_calendar_history.json 확인 필요');
  }
}

async function init(){
  bindTabs();
  bindCalendarNav();
  document.getElementById('refreshBtn').addEventListener('click', refreshAll);
  updateKRClock();
  setInterval(updateKRClock, 1000);
  await refreshAll();
}

init();
