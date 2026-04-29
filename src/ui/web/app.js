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
  const panel = document.getElementById('aiPanelContainer');
  panel.classList.add('open');
  addLog('AI Asistan açıldı', 'log-info');
  
  // Input'a focus
  setTimeout(() => {
    document.getElementById('assistantInput').focus();
  }, 400);
}

// AI Asistan'ı kapat
function closeAIAssistant() {
  const panel = document.getElementById('aiPanelContainer');
  panel.classList.remove('open');
  
  // Detail panel'i de kapat
  closeDetailPanel();
}

// Detail panel aç
function openDetailPanel(title, content) {
  const detailPanel = document.getElementById('aiPanelDetail');
  const detailTitle = document.getElementById('detailTitle');
  const detailContent = document.getElementById('detailContent');
  
  detailTitle.textContent = title;
  detailContent.innerHTML = content;
  detailPanel.classList.add('active');
}

// Detail panel kapat
function closeDetailPanel() {
  const detailPanel = document.getElementById('aiPanelDetail');
  detailPanel.classList.remove('active');
}

// Hızlı aksiyon butonu
async function quickAction(agentType) {
  // Hangi makine?
  const machineChoice = prompt(
    'Hangi makine için?\n\n' +
    '• HPR001, HPR002, HPR003, HPR004, HPR005, HPR006\n' +
    '• Veya "hepsi" yazın\n\n' +
    '(Örnek: HPR001)'
  );
  
  if (!machineChoice) return;
  
  let machineId = machineChoice.toUpperCase();
  
  // Kullanıcı mesajı ekle
  addAssistantMessage('user', `${agentType} için analiz istiyorum`);
  
  // Loading göster
  addAssistantMessage('ai', '⏳ Analiz yapılıyor... (15-20 saniye sürebilir)');
  
  try {
    if (machineId === 'HEPSI' || machineId === 'TÜMÜ' || machineId === 'TUMU') {
      // Filo analizi
      const response = await fetch('/api/fleet');
      const data = await response.json();
      
      removeLastAssistantMessage();
      addAssistantMessage('ai', data.analysis || 'Filo analizi tamamlandı.');
      
    } else {
      // Tek makine analizi
      const response = await fetch(`/api/multi-agent/analyze/${machineId}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({})
      });
      
      const data = await response.json();
      removeLastAssistantMessage();
      
      if (data.success) {
        // Ajana özel sonuç göster
        displayAgentResult(agentType, data, machineId);
      } else {
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
  let message = '';
  
  switch(agentType) {
    case 'diagnosis':
      const diagnosis = data.diagnosis?.primary_diagnosis?.description_tr || 'Teşhis bilgisi yok';
      message = `🔍 TEŞHİS - ${machineId}\n\n${diagnosis}`;
      break;
      
    case 'action':
      const actions = data.action?.immediate_actions || [];
      if (actions.length === 0) {
        message = `🛠️ AKSİYON - ${machineId}\n\nÖnerilen aksiyon yok.`;
      } else {
        message = `🛠️ AKSİYON - ${machineId}\\n\n` + 
                  actions.map(a => `• ${a.description_tr} (${a.priority})`).join('\n');
      }
      break;
      
    case 'prediction':
      const prediction = data.prediction?.short_term_forecast || 'Tahmin bilgisi yok';
      message = `📈 TAHMİN - ${machineId}\n\n${prediction}`;
      break;
      
    case 'root_cause':
      const causes = data.root_cause?.likely_causes || [];
      if (causes.length === 0) {
        message = `🎯 KÖK NEDEN - ${machineId}\n\nKök neden analizi yok.`;
      } else {
        message = `🎯 KÖK NEDEN - ${machineId}\n\n` + 
                  causes.map(c => `• ${c.description_tr}`).join('\n');
      }
      break;
  }
  
  addAssistantMessage('ai', message);
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
  contentDiv.textContent = text;
  contentDiv.style.whiteSpace = 'pre-wrap'; // Yeni satırları koru
  
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
