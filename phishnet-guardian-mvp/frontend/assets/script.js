// frontend/assets/script.js

// ---------------- CONFIG ----------------
const API = "https://phishnet-guardian-mvp.onrender.com"; 
const $ = (s) => document.querySelector(s);

// ---------------- THEME TOGGLE (persist) ----------------
(function initTheme() {
  const root = document.documentElement;
  const saved = localStorage.getItem('theme') || 'dark';
  root.setAttribute('data-theme', saved);

  const btn = $('#themeToggle');
  if (btn) {
    btn.addEventListener('click', () => {
      const next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
      root.setAttribute('data-theme', next);
      localStorage.setItem('theme', next);
    });
  }
})();

// ---------------- HELPERS ----------------
function formatSize(bytes){
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024*1024) return `${(bytes/1024).toFixed(1)} KB`;
  return `${(bytes/1024/1024).toFixed(1)} MB`;
}

function showErrorBox(container, err){
  const msg = (typeof err === 'string') ? err : (err && err.message) || 'Unknown error';
  container.classList.remove('hidden');
  container.innerHTML = `
    <div class="error-box">⚠️ Error: ${msg}</div>
  `;
}

async function parseResponse(res){
  const text = await res.text();
  try {
    const json = JSON.parse(text);
    if (!res.ok) {
      const detail = json.detail || text || `HTTP ${res.status}`;
      throw new Error(detail);
    }
    return json;
  } catch {
    if (!res.ok) {
      throw new Error(text || `HTTP ${res.status}`);
    }
    // Not JSON but OK (unlikely)
    return {};
  }
}

// ---------------- IMAGE PREVIEW ----------------
function showImagePreview(file){
  const wrap = $('#imgPreviewWrap');
  const img = $('#imgPreview');
  const name = $('#imgName');
  const size = $('#imgSize');
  if (!file || !wrap || !img) return;

  const url = URL.createObjectURL(file);
  img.src = url;
  if (name) name.textContent = file.name || 'image';
  if (size) size.textContent = formatSize(file.size || 0);
  wrap.classList.remove('hidden');
  img.onload = () => URL.revokeObjectURL(url);
}

(function bindImageInput(){
  const input = $('#imgFile');
  if (!input) return;

  const dz = $('#dropzone');
  if (dz) {
    dz.addEventListener('click', () => input.click());
    dz.addEventListener('dragover', (e)=>{ e.preventDefault(); dz.classList.add('drag'); });
    dz.addEventListener('dragleave', ()=> dz.classList.remove('drag'));
    dz.addEventListener('drop', (e)=>{
      e.preventDefault();
      dz.classList.remove('drag');
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
        input.files = e.dataTransfer.files;
        showImagePreview(input.files[0]);
      }
    });
  }

  input.addEventListener('change', (e)=>{
    const f = e.target.files && e.target.files[0];
    if (f) showImagePreview(f);
  });
})();

// ---------------- QUIZ (interactive) ----------------
function renderQuiz(container, quiz) {
  const q = quiz || {};
  const options = Array.isArray(q.options) ? q.options : [];
  const correct = (q.answer || "").trim();

  if (!q.question || options.length === 0) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = `
    <div class="quiz-wrap">
      <div class="quiz-title">Quiz</div>
      <div class="quiz-q">${q.question}</div>
      <div class="quiz-opts">
        ${options.map((o)=>`<button class="quiz-opt outline" data-val="${o}">${o}</button>`).join('')}
      </div>
      <div id="quizFeedback" class="quiz-feedback"></div>
    </div>
  `;

  const opts = container.querySelectorAll('.quiz-opt');
  const feedback = container.querySelector('#quizFeedback');
  let answered = false;

  opts.forEach(btn=>{
    btn.addEventListener('click', ()=>{
      if (answered) return;
      answered = true;

      const val = btn.getAttribute('data-val') || '';
      const ok = val.trim() === correct;

      btn.classList.remove('outline');
      btn.style.background = ok ? 'linear-gradient(135deg,#20c997,#12b886)' : 'linear-gradient(135deg,#ff4757,#ff6b6b)';
      btn.style.color = '#fff';

      // disable others & highlight the correct one
      opts.forEach(b=>{
        b.disabled = true;
        if (b !== btn && b.getAttribute('data-val') === correct) {
          b.classList.remove('outline');
          b.style.background = 'linear-gradient(135deg,#20c997,#12b886)';
          b.style.color = '#fff';
        }
      });

      const expl = (q.explanation || '').trim();
      feedback.innerHTML = ok ? `✅ ${expl || 'Correct.'}` : `❌ ${expl || 'Not quite.'}`;
    });
  });
}

// ---------------- RENDER RESULT ----------------
function renderResult(r) {
  const resultBox = $('#result');
  resultBox.classList.remove('hidden');

  const flags = Array.isArray(r.red_flags) ? r.red_flags : [];
  const actions = Array.isArray(r.recommended_actions) ? r.recommended_actions : [];
  const notToDo = Array.isArray(r.not_to_do) ? r.not_to_do : [];
  const plan = Array.isArray(r.plan) ? r.plan : [];
  const quiz = r.quiz || {};
  const summary = r.summary || r.micro_lesson || '';

  const redFlagsHtml = flags.length ? flags.map(f => `<span class="flag">${f}</span>`).join(' ') : '—';
  const list = arr => arr.map(a => `<li>${a}</li>`).join('');

  // Optional badges if present in the page
  const riskBadge = $('#riskBadge');
  const confBadge = $('#confBadge');
  if (riskBadge) riskBadge.textContent = `${r.classification || '-'} / ${r.risk_level || '-'}`;
  if (confBadge) confBadge.textContent = `${Math.round(((r.confidence || 0) * 100))}%`;

  // Build base sections
  resultBox.innerHTML = `
    <section class="result-summary">
      <h3>Summary</h3>
      <p>${summary}</p>
    </section>

    <section class="result-flags">
      <h3>Red Flags</h3>
      <div>${redFlagsHtml}</div>
    </section>

    <section class="result-actions">
      <h3>What To Do</h3>
      <ul>${list(actions)}</ul>
    </section>

    <section class="result-notto">
      <h3>What NOT To Do</h3>
      <ul>${list(notToDo)}</ul>
    </section>

    <section class="result-plan">
      <h3>Plan</h3>
      <ul>${plan.map(p => `<li>${p}</li>`).join('')}</ul>
    </section>

    <section class="result-lesson">
      <h3>Micro‑Lesson</h3>
      <div>${r.micro_lesson || ''}</div>
    </section>
  `;

  // Render quiz block after base sections
  const quizHtml = document.createElement('div');
  renderQuiz(quizHtml, quiz);
  resultBox.appendChild(quizHtml);
}

// ---------------- API HELPERS ----------------
async function scanText({ text, lang = "en" }) {
  console.log("Calling:", `${API}/api/scan`);
  const res = await fetch(`${API}/api/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, lang })
  });
  return parseResponse(res);
}

async function scanImage(file, lang = "en") {
  const form = new FormData();
  form.append("file", file); // MUST be "file" to match FastAPI UploadFile param
  form.append("lang", lang);

  console.log("Calling:", `${API}/api/scan-image`);
  const res = await fetch(`${API}/api/scan-image`, { method: "POST", body: form });
  return parseResponse(res);
}

async function getHistory(limit = 50) {
  console.log("Calling:", `${API}/api/history?limit=${limit}`);
  const res = await fetch(`${API}/api/history?limit=${limit}`);
  return parseResponse(res);
}

async function getStats(){
  console.log("Calling:", `${API}/api/stats`);
  const res = await fetch(`${API}/api/stats`);
  return parseResponse(res);
}

// ---------------- ANALYZE (TEXT) ----------------
async function onAnalyze(ev) {
  ev.preventDefault();
  const resultBox = $('#result');
  const textEl = $('#text');
  const langEl = $('#language');
  const btn = $('#analyzeBtn') || $('#runBtn');

  const text = (textEl?.value || '').trim();
  const lang = (langEl?.value) || 'en';

  if (text.length < 5) {
    alert('Please enter a longer message to analyze.');
    return;
  }

  const old = btn ? btn.textContent : null;
  if (btn) { btn.disabled = true; btn.textContent = 'Analyzing…'; }

  try {
    const data = await scanText({ text, lang });
    renderResult(data);
    await loadHistory();
    await loadStats();
  } catch (e) {
    showErrorBox(resultBox, e);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = old; }
  }
}

// ---------------- ANALYZE (IMAGE) ----------------
async function onAnalyzeImage(ev) {
  ev.preventDefault();
  const imgBox = $('#imgResult') || $('#result');
  const fileEl = $('#imgFile');
  const langEl = $('#imgLanguage');
  const btn = $('#imgBtn');

  const file = fileEl?.files?.[0];
  if (!file) { alert('Select an image first.'); return; }
  const lang = (langEl?.value) || 'en';

  const old = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = 'Analyzing…'; }

  try {
    const data = await scanImage(file, lang);
    renderResult(data);
    await loadHistory();
    await loadStats();
  } catch (e) {
    showErrorBox(imgBox, e);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = old; }
  }
}

// ---------------- HISTORY ----------------
async function loadHistory() {
  const hist = $('#history');
  if (!hist) return;
  try {
    const data = await getHistory(50);
    hist.innerHTML = (data.items || []).map(it => `
      <div class="hist-item">
        <div class="hist-time">${new Date(it.created_at).toLocaleString()}</div>
        <div class="hist-text">${(it.input_text || '').slice(0, 120)}</div>
        <div class="hist-meta">${it.classification || '-'} ${Math.round(((it.confidence || 0) * 100))}%</div>
      </div>
    `).join('');
  } catch (e) {
    hist.innerHTML = 'History unavailable';
  }
}

// ---------------- STATS (KPI COUNTERS) ----------------
async function loadStats(){
  const total = $('#totalScans');
  const scam = $('#scamCount');
  const susp = $('#suspCount');
  const safe = $('#safeCount');
  if (!total && !scam && !susp && !safe) return; // page may not have KPIs

  try {
    const data = await getStats();
    const dist = data.distribution || {};
    const t = data.total || 0;
    if (total) total.textContent = t;
    if (scam) scam.textContent = dist.Scam || 0;
    if (susp) susp.textContent = dist.Suspicious || 0;
    if (safe) safe.textContent = dist.Safe || 0;
  } catch {
    // Silently ignore; KPIs just won't update this tick
  }
}

// ---------------- WIRE-UP ----------------
(function init() {
  const y = document.getElementById('year');
  if (y) y.textContent = new Date().getFullYear();

  const scanForm = $('#scanForm') || $('#runForm');
  if (scanForm) scanForm.addEventListener('submit', onAnalyze);

  const imgForm = $('#imgForm');
  if (imgForm) imgForm.addEventListener('submit', onAnalyzeImage);

  loadHistory();
  loadStats();
})();
