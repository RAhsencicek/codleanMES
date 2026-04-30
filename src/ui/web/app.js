/**
 * Codlean MES — Web Dashboard
 * SSE ile gerçek zamanlı güncelleme · 2 saniyede bir
 * v2: Usta Başı soru-cevap entegrasyonu, warn_level desteği
 */

// ─── Makine Tipi Eşleştirmesi ───────────────────────────────────────────────
const MACHINE_TYPES = {
  HPR001: { type: 'Dikey Pres', icon: '🔵' },
  HPR002: { type: 'Yatay Pres', icon: '🟠' },
  HPR003: { type: 'Dikey Pres', icon: '🔵' },
  HPR004: { type: 'Dikey Pres', icon: '🔵' },
  HPR005: { type: 'Dikey Pres', icon: '🔵' },
  HPR006: { type: 'Yatay Pres', icon: '🟠' },
  HPR011: { type: 'Dikey Pres', icon: '🔵' },
  HPR012: { type: 'Dikey Pres', icon: '🔵' },
  HPR013: { type: 'Dikey Pres', icon: '🔵' },
};

// ─── Durum ─────────────────────────────────────────────────────────────────
const state = {
  machines:     {},
  startTime:    Date.now(),
  alertCount:   0,
  prevSeverities: {},
  currentMachine: null,  // Modal için aktif makine
};

// ─── Yardımcılar ────────────────────────────────────────────────────────────
function riskClass(score) {
  if (score >= 70) return 'critical';
  if (score >= 50) return 'high';
  if (score >= 30) return 'warning';
  return 'normal';
}
function riskColor(cls) {
  return {normal:'var(--green)', warning:'var(--yellow)', high:'var(--orange)', critical:'var(--red)'}[cls] || 'var(--text-2)';
}
// Teşhis kuralı Türkçe isimleri
const DIAGNOSIS_NAMES = {
  termal_stres_ve_sizinti_riski: {icon: '🌡️', label: 'Termal Stres'},
  pompa_kavitasyon_ve_hava_emme: {icon: '💨', label: 'Kavitasyon'},
  ic_kacak_belirtisi_dusuk_basinc_yuksek_isi: {icon: '💧', label: 'İç Kaçak'},
  filtre_tikanikligi_ve_yuksek_direnc: {icon: '🔧', label: 'Filtre Tıkanık'},
  yatay_pres_hareket_duzensizligi: {icon: '↔️', label: 'Hareket Bozuk'},
  sogutma_sistemi_verimsizligi: {icon: '❄️', label: 'Soğutma Yetersiz'},
  dikey_pres_asiri_yuklenme: {icon: '⚠️', label: 'Aşırı Yük'},
  soguk_baslangic_asiri_basinc: {icon: '🧊', label: 'Soğuk Başlangıç'},
  alt_ejektor_sikismasi: {icon: '🔩', label: 'Ejektör Sıkışması'},
  yatay_pres_hidrolik_kayma_drift: {icon: '📐', label: 'Hidrolik Kayma'},
};
function execBadge(execution, machineId) {
  // Execution bilgisi yoksa makine tipini göster
  if (!execution || execution === '—') {
    const mt = MACHINE_TYPES[machineId];
    if (mt) return ['exec-type', mt.icon, mt.type];
    return ['exec-unknown', '⬜', 'HPR'];
  }
  const e = execution.toUpperCase();
  if (e === 'RUNNING')  return ['exec-running', '🟢', 'Çalışıyor'];
  if (e === 'IDLE')     return ['exec-idle',    '🟡', 'Bekleniyor'];
  if (e === 'STOPPED')  return ['exec-stopped', '🔴', 'Durdu'];
  return ['exec-unknown', '⬜', execution];
}
function severityToLogClass(sev) {
  return {KRİTİK:'log-critical', YÜKSEK:'log-high', ORTA:'log-warning', NORMAL:'log-normal'}[sev] || 'log-info';
}
function now() {
  return new Date().toLocaleTimeString('tr-TR', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
}

// ─── Kart HTML üretici ──────────────────────────────────────────────────────
function buildCardHTML(machine) {
  const { id, execution, severity, risk_score, sensors } = machine;
  const cls   = riskClass(risk_score);
  const color = riskColor(cls);
  const [execClass, execIcon, execLabel] = execBadge(execution, id);
  const mt = MACHINE_TYPES[id] || { type: 'HPR', icon: '⚙️' };

  // Sensörler — max 5, kritik üste
  const sorted = [...(sensors||[])].sort((a,b)=>(b.pct||0)-(a.pct||0)).slice(0,5);
  const sensorsHTML = sorted.map(s => {
    const pct  = Math.min(s.pct ?? 0, 110);
    const sCls = s.status === 'critical'  ? 'color-critical'
               : s.status === 'warn'      ? 'color-warning'
               : s.status === 'pre_fault' ? 'color-prefault'
               :                            'color-normal';
    const pfBadge = s.pre_fault ? '<span class="pf-badge">PRE⚡</span>' : '';
    return `<div class="sensor-row">
      <span class="sensor-name">${s.label} ${pfBadge}</span>
      <span class="sensor-value">${s.value.toFixed(1)}<span style="color:var(--text-3);font-size:9px"> ${s.unit||''}</span></span>
      <div class="sensor-bar-wrap" title="${pct.toFixed(0)}%">
        <div class="sensor-bar-fill ${sCls}" style="width:${Math.min(pct,100)}%"></div>
      </div>
    </div>`;
  }).join('');

  // Causal Teşhis Badge'leri
  const diagHTML = (machine.diagnoses || []).map(d => {
    // Yeni sistemde rule doğrudan okunaklı isim olarak geliyor (örn: "Testere Bicak Korelmesi")
    let icon = '🔍';
    if(d.rule.toLowerCase().includes('isi') || d.rule.toLowerCase().includes('sicak')) icon = '🌡️';
    if(d.rule.toLowerCase().includes('testere') || d.rule.toLowerCase().includes('korelme')) icon = '⚡';
    if(d.rule.toLowerCase().includes('basinc')) icon = '💨';
    
    return `<span class="diag-badge" title="${d.explanation_tr}">${icon} ${d.rule}</span>`;
  }).join('');
  const diagSection = diagHTML
    ? `<div class="diag-section"><span class="diag-title">🩺 Aktif Teşhis</span>${diagHTML}</div>`
    : '';

  const sevLabel = {KRİTİK:'🚨 KRİTİK', YÜKSEK:'⚠️ YÜKSEK', ORTA:'⚡ ORTA', NORMAL:'✅ NORMAL'}[severity] || severity;
  const sevStyle = {KRİTİK:'risk-critical', YÜKSEK:'risk-high', ORTA:'risk-warning', NORMAL:'risk-normal'}[severity] || 'risk-normal';

  return `
    <div class="card-header">
      <span class="card-id">⚙️ ${id}</span>
      <span class="card-exec-badge ${execClass}">${execIcon} ${execLabel}</span>
    </div>
    <div class="risk-section">
      <div class="risk-top">
        <span class="risk-label">Risk Skoru</span>
        <span class="risk-score-big ${sevStyle}">${Math.round(risk_score)}</span>
      </div>
      <div class="risk-track">
        <div class="risk-fill" style="width:${risk_score}%;background:${color}"></div>
      </div>
      <span class="risk-severity ${sevStyle}">${sevLabel}</span>
    </div>
    ${diagSection}
    <div class="sensors-list">${sensorsHTML || '<span style="color:var(--text-3);font-size:11px">⏳ Veri bekleniyor...</span>'}</div>
    <button class="usta-card-btn" onclick="openUsta('${id}', event)">🤖 Usta Başı'na Sor</button>`;
}

// ─── Grid güncelleme ────────────────────────────────────────────────────────
function updateGrid(machines) {
  const grid = document.getElementById('machines-grid');
  document.getElementById('loading')?.classList.add('hidden');

  machines.forEach(machine => {
    const cls = riskClass(machine.risk_score);
    let card = document.getElementById(`card-${machine.id}`);
    if (!card) {
      card = document.createElement('div');
      card.id        = `card-${machine.id}`;
      card.className = `machine-card ${cls}`;
      grid.appendChild(card);
    } else {
      card.className = `machine-card ${cls}`;
    }
    card.innerHTML = buildCardHTML(machine);

    // Severity değişti mi?
    const prev = state.prevSeverities[machine.id];
    if (prev && prev !== machine.severity && machine.severity !== 'NORMAL') {
      addLog(`${machine.id} → ${machine.severity}`, severityToLogClass(machine.severity));
      if (machine.severity === 'KRİTİK' || machine.severity === 'YÜKSEK') {
        showToast(`🚨 ${machine.id} — ${machine.severity} alarm!`, machine.severity);
        state.alertCount++;
      }
    }
    state.prevSeverities[machine.id] = machine.severity;
    // Makine verisini state'e kaydet (modal için)
    state.machines[machine.id] = machine;
  });

  const alerts = machines.filter(m => m.severity !== 'NORMAL').length;
  document.getElementById('total-machines').textContent = machines.length;
  document.getElementById('alert-count').textContent    = alerts;
}

// ─── Kafka Lag Banner ──────────────────────────────────────────────────────
function updateLagBanner(lag) {
  let el = document.getElementById('lag-banner');
  if (!el) {
    el = document.createElement('div');
    el.id = 'lag-banner';
    const header = document.querySelector('.header');
    if (header) header.parentNode.insertBefore(el, header.nextSibling);
  }
  if (!lag || lag.level === 'CANLI') {
    el.className = 'lag-banner lag-ok';
    el.innerHTML = `📡 Veri: <strong>CANLI</strong> — Son güncelleme: ${lag?.last_update || '—'}`;
  } else if (lag.level === 'NORMAL') {
    el.className = 'lag-banner lag-normal';
    el.innerHTML = `📡 Veri: Normal — Gecikme: ${lag.lag_seconds}sn — Son: ${lag.last_update}`;
  } else if (lag.level === 'GECİKMELİ') {
    el.className = 'lag-banner lag-delayed';
    el.innerHTML = `⚠️ Veri Gecikmesi: <strong>${Math.round(lag.lag_seconds/60)} dk</strong> — Son: ${lag.last_update}`;
  } else {
    el.className = 'lag-banner lag-critical';
    const hours = (lag.lag_seconds / 3600).toFixed(1);
    el.innerHTML = `🚨 Veri Gecikmesi: <strong>KRİTİK (${hours} saat)</strong> — Son: ${lag.last_update} — Kafka bağlantısını kontrol edin!`;
  }
}

// ─── Log ────────────────────────────────────────────────────────────────────
const logLines = [];
function addLog(msg, cls = 'log-info') {
  logLines.unshift({t: now(), msg, cls});
  if (logLines.length > 30) logLines.pop();
  const el = document.getElementById('log-list');
  if (el) renderLog();
}
function renderLog() {
  const el = document.getElementById('log-list');
  el.innerHTML = logLines.map(l =>
    `<div class="log-item ${l.cls}"><span style="color:var(--text-3)">${l.t}</span>  ${l.msg}</div>`
  ).join('');
}

// ─── Toast ──────────────────────────────────────────────────────────────────
const toastContainer = document.createElement('div');
toastContainer.className = 'toast-container';
document.body.appendChild(toastContainer);
function showToast(msg, severity) {
  const cls = severity === 'KRİTİK' ? 'toast-critical' : severity === 'YÜKSEK' ? 'toast-warning' : 'toast-info';
  const el = document.createElement('div');
  el.className   = `toast ${cls}`;
  el.textContent = msg;
  toastContainer.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ─── Saat & Uptime ──────────────────────────────────────────────────────────
function updateClock() {
  document.getElementById('clock').textContent = now();
  const elapsed = Math.floor((Date.now() - state.startTime) / 1000);
  const m = Math.floor(elapsed / 60).toString().padStart(2,'0');
  const s = (elapsed % 60).toString().padStart(2,'0');
  document.getElementById('uptime').textContent = `${m}:${s}`;
}
setInterval(updateClock, 1000);
updateClock();

// ─── SSE ────────────────────────────────────────────────────────────────────
let evtSource = null;
let reconnectTimer = null;
function connect() {
  if (evtSource) { evtSource.close(); evtSource = null; }
  evtSource = new EventSource('/stream');
  const dot   = document.getElementById('conn-dot');
  const label = document.getElementById('conn-label');

  evtSource.onopen = () => {
    dot.className   = 'conn-dot live';
    label.textContent = 'Canlı';
    addLog('Veri akışına bağlandı', 'log-normal');
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  };
  evtSource.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      if (data.error) { addLog('Sunucu hatası: ' + data.error, 'log-critical'); return; }
      updateGrid(data.machines || []);
      const ua = document.getElementById('updated-at');
      if (ua) ua.textContent = 'Son güncelleme: ' + (data.updated_at || now());
      if (data.context_faults !== undefined)
        document.getElementById('fault-count').textContent = data.context_faults;
      // Kafka Lag Banner güncelle
      if (data.kafka_lag) updateLagBanner(data.kafka_lag);
    } catch (e) {
      addLog('JSON parse hatası: ' + e.message, 'log-warning');
    }
  };
  evtSource.onerror = () => {
    dot.className     = 'conn-dot error';
    label.textContent = 'Bağlantı kesildi';
    addLog('Sunucuya bağlanılamıyor — 5sn sonra yeniden denenecek', 'log-warning');
    evtSource.close(); evtSource = null;
    reconnectTimer = setTimeout(connect, 5000);
  };
}

// ─── AI Usta Başı Modal ─────────────────────────────────────────────────────
function openUsta(machineId, event) {
  if (event) event.stopPropagation();
  state.currentMachine = machineId;

  // Modal başlık
  document.getElementById('modal-machine-id').textContent = machineId;

  // Sensör özet
  const m = state.machines[machineId];
  const summaryEl = document.getElementById('modal-sensor-summary');
  if (m && m.sensors) {
    summaryEl.innerHTML = m.sensors.slice(0,4).map(s => `
      <div class="modal-sensor-chip ${s.status==='critical'?'chip-critical':s.status==='warn'?'chip-warn':'chip-normal'}">
        <span>${s.label}</span>
        <strong>${s.value.toFixed(1)} ${s.unit||''}</strong>
      </div>`).join('');
  } else {
    summaryEl.innerHTML = '';
  }

  // Chat sıfırla
  const chat = document.getElementById('modal-chat');
  const sev  = m?.severity || '?';
  const score = m?.risk_score ? Math.round(m.risk_score) : '?';
  chat.innerHTML = `<div class="chat-bubble chat-system">
    <strong>${machineId}</strong> · Risk Skoru: ${score} · Durum: ${sev}<br>
    Sorunuzu yazın veya "⚡ Anlık Analiz" butonuna basın.
  </div>`;

  document.getElementById('usta-input').value = '';
  document.getElementById('usta-modal').classList.add('open');
  document.getElementById('usta-input').focus();
}

function closeUstaModal(event) {
  if (event && event.target !== document.getElementById('usta-modal')) return;
  document.getElementById('usta-modal').classList.remove('open');
}

function addChatBubble(text, role) {
  const chat = document.getElementById('modal-chat');
  const div  = document.createElement('div');
  div.className = `chat-bubble chat-${role}`;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

async function sendUstaQuestion() {
  const input = document.getElementById('usta-input');
  const question = input.value.trim();
  if (!question || !state.currentMachine) return;
  input.value = '';

  addChatBubble(question, 'user');
  addChatBubble('⏳ Usta Başı düşünüyor...', 'loading');
  document.getElementById('btn-ask').disabled     = true;
  document.getElementById('btn-analyze').disabled = true;

  try {
    const res  = await fetch('/api/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({machine_id: state.currentMachine, question}),
    });
    const data = await res.json();

    // Loading bubble'ı kaldır
    const chat = document.getElementById('modal-chat');
    const loading = chat.querySelector('.chat-loading');
    if (loading) loading.remove();
    const bubbles = chat.querySelectorAll('.chat-bubble');
    bubbles[bubbles.length-1]?.classList.contains('chat-loading') && bubbles[bubbles.length-1].remove();

    addChatBubble(data.answer || 'Yanıt alınamadı.', 'usta');
    addLog(`${state.currentMachine}: Usta Başı yanıtladı`, 'log-info');
  } catch(e) {
    addChatBubble('Bağlantı hatası: ' + e.message, 'usta');
  } finally {
    document.getElementById('btn-ask').disabled     = false;
    document.getElementById('btn-analyze').disabled = false;
  }
}

async function sendAutoAnalyze() {
  if (!state.currentMachine) return;
  const m     = state.machines[state.currentMachine];
  const score = m?.risk_score ? Math.round(m.risk_score) : '?';
  const question = `${state.currentMachine} mevcut durumunu analiz et. Risk skoru ${score}. Ne oluyor, neden, ne yapmalı?`;

  document.getElementById('usta-input').value = question;
  await sendUstaQuestion();
}

// ─── Filo Analizi ────────────────────────────────────────────────────────────
async function openFleet() {
  document.getElementById('fleet-modal').classList.add('open');
  const chat = document.getElementById('fleet-chat');
  chat.innerHTML = '<div class="chat-bubble chat-system">⏳ Tüm HPR makineleri analiz ediliyor...</div>';
  
  try {
    const res  = await fetch('/api/fleet');
    const data = await res.json();
    chat.innerHTML = `<div class="chat-bubble chat-usta">${data.analysis || 'Analiz üretilemedi.'}</div>
      <div class="chat-bubble chat-system" style="font-size:11px;opacity:0.6">${data.timestamp || ''}</div>`;
  } catch(e) {
    chat.innerHTML = `<div class="chat-bubble chat-usta">Bağlantı hatası: ${e.message}</div>`;
  }
}

function closeFleetModal(event) {
  if (event && event.target !== document.getElementById('fleet-modal')) return;
  document.getElementById('fleet-modal').classList.remove('open');
}

// ─── API Key Status ─────────────────────────────────────────────────────
async function openApiStatus() {
  document.getElementById('api-modal').style.display = 'flex';
  await fetchApiStatus();
}

function closeApiModal(event) {
  if (event && event.target !== event.currentTarget) return;
  document.getElementById('api-modal').style.display = 'none';
}

async function fetchApiStatus() {
  try {
    const response = await fetch('/api/status/keys');
    const data = await response.json();
    
    if (!data.success) return;
    
    // Gemini
    const gemini = data.gemini;
    document.getElementById('gemini-used').textContent = gemini.used;
    document.getElementById('gemini-remaining').textContent = gemini.remaining;
    document.getElementById('gemini-total').textContent = gemini.total;
    document.getElementById('gemini-keys').textContent = gemini.keys_count;
    document.getElementById('gemini-bar').style.width = `${gemini.usage_pct}%`;
    
    // Groq
    const groq = data.groq;
    document.getElementById('groq-used').textContent = groq.used;
    document.getElementById('groq-remaining').textContent = groq.remaining;
    document.getElementById('groq-total').textContent = groq.total;
    document.getElementById('groq-keys').textContent = groq.keys_count;
    document.getElementById('groq-bar').style.width = `${groq.usage_pct}%`;
    
    // Combined
    const combined = data.combined;
    document.getElementById('combined-used').textContent = combined.used;
    document.getElementById('combined-remaining').textContent = combined.remaining;
    document.getElementById('combined-total').textContent = combined.total;
    document.getElementById('combined-pct').textContent = `${combined.usage_pct}%`;
    document.getElementById('combined-bar').style.width = `${combined.usage_pct}%`;
    
    // Header pill
    document.getElementById('api-usage').textContent = `${combined.used}/${combined.total}`;
    
  } catch (error) {
    console.error('[API Status] Hata:', error);
  }
}

// API status'ü her 30 saniyede bir güncelle
setInterval(fetchApiStatus, 30000);

// Sayfa yüklenince API status'ü çek
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    fetchApiStatus();
  });
} else {
  fetchApiStatus();
}

// ─── Klavye kısayolları ───────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.getElementById('usta-modal').classList.remove('open');
    document.getElementById('fleet-modal').classList.remove('open');
    document.getElementById('aiModalBackdrop').classList.remove('open');
  }
});

// ─── Başlat ─────────────────────────────────────────────────────────────────
addLog('Dashboard başlatılıyor...', 'log-info');
connect();

// ═══════════════════════════════════════════════════════
// AI ASİSTAN FONKSİYONLARI
// ═══════════════════════════════════════════════════════

// AI Asistan'ı aç
function openAIAssistant() {
  const backdrop = document.getElementById('aiModalBackdrop');
  backdrop.classList.add('open');
  addLog('AI Asistan açıldı', 'log-info');
  
  // Input'a focus
  setTimeout(() => {
    document.getElementById('assistantInput').focus();
  }, 300);
}

// AI Asistan'ı kapat
function closeAIAssistant(event) {
  // Eğer modal içinde tıklandıysa kapatma
  if (event && event.target.id !== 'aiModalBackdrop') {
    return;
  }
  
  const backdrop = document.getElementById('aiModalBackdrop');
  backdrop.classList.remove('open');
  
  // Detay panel'i de kapat
  closeDetailPanel();
}

// Detay panel aç (modal'ın sağında)
function openDetailPanel(title, content) {
  const detailPanel = document.getElementById('aiDetailPanel');
  const detailTitle = document.getElementById('detailTitle');
  const detailContent = document.getElementById('detailContent');
  
  detailTitle.textContent = title;
  detailContent.innerHTML = content;
  detailPanel.classList.add('active');
}

// Detay panel kapat
function closeDetailPanel() {
  const detailPanel = document.getElementById('aiDetailPanel');
  detailPanel.classList.remove('active');
}

// Hızlı aksiyon butonu - Makine seçimi göster
function quickAction(agentType) {
  const agentNames = {
    diagnosis: '🔍 Teşhis',
    action: '🛠️ Aksiyon',
    prediction: '📈 Tahmin',
    root_cause: '🎯 Kök Neden'
  };
  
  const agentEmojis = {
    diagnosis: '🔍',
    action: '🛠️',
    prediction: '📈',
    root_cause: '🎯'
  };
  
  // Kullanıcı seçimini göster
  addAssistantMessage('user', `${agentNames[agentType]} analizi yapmak istiyorum`);
  
  // Makine seçim kartları göster
  const machinesHTML = `
    <div style="margin-top:12px;">
      <p style="margin-bottom:12px;color:var(--text-2);font-size:13px;">Hangi makine için?</p>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">
        ${['HPR001', 'HPR002', 'HPR003', 'HPR004', 'HPR005', 'HPR006'].map(id => `
          <button onclick="selectMachine('${id}', '${agentType}')" 
                  style="padding:10px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;color:var(--text-1);cursor:pointer;font-size:12px;font-weight:600;transition:all 0.2s;"
                  onmouseover="this.style.background='rgba(102,126,234,0.2)';this.style.borderColor='#667eea'"
                  onmouseout="this.style.background='var(--bg-card)';this.style.borderColor='var(--border)'">
            ${id}
          </button>
        `).join('')}
      </div>
      <button onclick="selectMachine('HEPSI', '${agentType}')" 
              style="margin-top:8px;width:100%;padding:10px;background:linear-gradient(135deg,#667eea,#764ba2);border:none;border-radius:8px;color:white;cursor:pointer;font-size:13px;font-weight:600;">
        🏭 Tüm Makineler (Filo Analizi)
      </button>
    </div>
  `;
  
  addAssistantMessage('ai', `${agentEmojis[agentType]} <strong>${agentNames[agentType]}</strong> için makine seçin:${machinesHTML}`);
}

// Makine seçildiğinde
async function selectMachine(machineId, agentType) {
  const agentNames = {
    diagnosis: '🔍 Teşhis',
    action: '🛠️ Aksiyon',
    prediction: '📈 Tahmin',
    root_cause: '🎯 Kök Neden'
  };
  
  // Seçimi göster
  addAssistantMessage('user', machineId === 'HEPSI' ? '🏭 Tüm makineler' : `✓ ${machineId}`);
  
  // Loading göster
  const loadingMsg = addAssistantMessage('ai', '⏳ Analiz yapılıyor... (15-20 saniye sürebilir)');
  
  // Sağ paneli aç - Loading
  openDetailPanel(
    `${agentNames[agentType]} Analizi`,
    '<div style="text-align:center;padding:40px;color:var(--text-2);">⏳ Analiz yapılıyor...</div>'
  );
  
  try {
    if (machineId === 'HEPSI') {
      // Filo analizi
      const response = await fetch('/api/fleet');
      const data = await response.json();
      
      // Sağ paneli güncelle
      openDetailPanel(
        `${agentNames[agentType]} - Filo Analizi`,
        `<div style="padding:16px;line-height:1.8;">${data.analysis || 'Analiz tamamlandı.'}</div>`
      );
      
      // Sol panele de mesaj ekle
      addAssistantMessage('ai', `📊 Filo analizi tamamlandı. Detaylar sağ panelde.`);
      
    } else {
      // Tek makine analizi
      const response = await fetch(`/api/multi-agent/analyze/${machineId}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({})
      });
      
      const data = await response.json();
      
      if (data.success) {
        // Sağ panelde göster
        displayAgentResult(agentType, data, machineId);
        
        // Sol panele mesaj
        addAssistantMessage('ai', `✅ ${machineId} için analiz tamamlandı. Detaylar sağ panelde.`);
      } else {
        openDetailPanel(
          'Hata',
          `<div style="padding:20px;color:var(--red);">❌ ${data.error || 'Bilinmeyen hata'}</div>`
        );
        addAssistantMessage('ai', `❌ Analiz yapılamadı: ${data.error || 'Bilinmeyen hata'}`);
      }
    }
  } catch (error) {
    removeLastAssistantMessage();
    addAssistantMessage('ai', '❌ Bağlantı hatası. Lütfen tekrar deneyin.');
  }
}

// Ajan sonucunu göster
function displayAgentResult(agentType, data, machineId) {
  const agentNames = {
    diagnosis: '🔍 Teşhis',
    action: '🛠️ Aksiyon',
    prediction: '📈 Tahmin',
    root_cause: '🎯 Kök Neden'
  };
  
  let html = `<div style="padding:16px;line-height:1.8;">`;
  html += `<h4 style="color:var(--cyan);margin-bottom:16px;">${agentNames[agentType]} - ${machineId}</h4>`;
  
  switch(agentType) {
    case 'diagnosis':
      const diagnosis = data.diagnosis?.primary_diagnosis?.description_tr || 'Teşhis bilgisi yok';
      html += `<p>${diagnosis}</p>`;
      break;
      
    case 'action':
      const actions = data.action?.immediate_actions || [];
      if (actions.length === 0) {
        html += `<p style="color:var(--text-2);">Önerilen aksiyon yok.</p>`;
      } else {
        html += `<ul style="list-style:none;padding:0;">`;
        actions.forEach(a => {
          const priorityColor = a.priority === 'KRİTİK' ? 'var(--red)' : a.priority === 'YÜKSEK' ? 'var(--orange)' : 'var(--yellow)';
          html += `<li style="margin-bottom:12px;padding:12px;background:var(--bg-card);border-radius:8px;border-left:3px solid ${priorityColor};">
            <strong style="color:${priorityColor};">${a.priority}</strong><br>
            ${a.description_tr}
          </li>`;
        });
        html += `</ul>`;
      }
      break;
      
    case 'prediction':
      const prediction = data.prediction?.short_term_forecast || 'Tahmin bilgisi yok';
      html += `<p>${prediction}</p>`;
      break;
      
    case 'root_cause':
      const causes = data.root_cause?.likely_causes || [];
      if (causes.length === 0) {
        html += `<p style="color:var(--text-2);">Kök neden analizi yok.</p>`;
      } else {
        html += `<ul style="list-style:none;padding:0;">`;
        causes.forEach(c => {
          html += `<li style="margin-bottom:10px;padding:10px;background:var(--bg-card);border-radius:6px;">
            • ${c.description_tr}
          </li>`;
        });
        html += `</ul>`;
      }
      break;
  }
  
  html += `</div>`;
  
  // Sağ panelde göster
  openDetailPanel(agentNames[agentType], html);
}

// Serbest mesaj gönder
async function sendAssistantMessage() {
  const input = document.getElementById('assistantInput');
  const message = input.value.trim();
  
  if (!message) return;
  
  // Kullanıcı mesajı ekle
  addAssistantMessage('user', message);
  input.value = '';
  
  // Loading göster
  addAssistantMessage('ai', '⏳ Düşünüyorum...');
  
  try {
    const response = await fetch('/api/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        message: message
      })
    });
    
    const data = await response.json();
    removeLastAssistantMessage();
    
    addAssistantMessage('ai', data.answer || data.response || 'Üzgünüm, yanıt veremedim.');
  } catch (error) {
    removeLastAssistantMessage();
    addAssistantMessage('ai', '❌ Bağlantı hatası. Lütfen tekrar deneyin.');
  }
}

// Yardımcı: Mesaj ekle
function addAssistantMessage(sender, text) {
  const messagesDiv = document.getElementById('assistantMessages');
  const messageDiv = document.createElement('div');
  messageDiv.className = `message ${sender}-message`;
  
  const contentDiv = document.createElement('div');
  contentDiv.className = 'message-content';
  
  // HTML içerik varsa innerHTML, yoksa textContent kullan
  if (text.includes('<')) {
    contentDiv.innerHTML = text;
  } else {
    contentDiv.textContent = text;
    contentDiv.style.whiteSpace = 'pre-wrap';
  }
  
  messageDiv.appendChild(contentDiv);
  messagesDiv.appendChild(messageDiv);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// Yardımcı: Son mesajı kaldır
function removeLastAssistantMessage() {
  const messagesDiv = document.getElementById('assistantMessages');
  if (messagesDiv.lastChild) {
    messagesDiv.removeChild(messagesDiv.lastChild);
  }
}

// ─── Sayfa Yüklendiğinde Başlat ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  connect();
  addLog('Dashboard başlatıldı', 'log-normal');
});
