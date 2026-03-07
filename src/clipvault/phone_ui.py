PHONE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no"/>
<title>ClipVault</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#1a1a2e;color:#eee;min-height:100vh;display:flex;flex-direction:column}

  header{background:#16213e;padding:14px 16px;display:flex;align-items:center;gap:10px;box-shadow:0 2px 8px #0005;position:sticky;top:0;z-index:10}
  header h1{font-size:1.2rem;font-weight:700;color:#7c83fd}
  #status{margin-left:auto;font-size:.72rem;padding:4px 10px;border-radius:999px;background:#333;color:#aaa;white-space:nowrap}
  #status.on{background:#1a472a;color:#6fcf97}
  #status.off{background:#4a1a1a;color:#eb5757}

  /* Send box — type or paste here */
  #sendBox{padding:12px 16px;background:#16213e;border-bottom:1px solid #2a2a4a;display:flex;gap:8px;align-items:flex-end}
  #sendBox textarea{
    flex:1;background:#0f3460;border:1.5px solid #3a3a6a;border-radius:10px;
    color:#fff;padding:10px 12px;font-size:.95rem;resize:none;height:70px;
    outline:none;font-family:inherit;line-height:1.4
  }
  #sendBox textarea:focus{border-color:#7c83fd}
  #sendBox textarea::placeholder{color:#556}
  #sendBtn{
    background:#7c83fd;color:#fff;border:none;border-radius:10px;
    padding:0 16px;height:70px;font-size:.9rem;font-weight:700;
    cursor:pointer;white-space:nowrap;min-width:64px;transition:background .15s
  }
  #sendBtn:active{background:#5c63dd}

  .search-bar{padding:10px 16px;background:#1a1a2e}
  .search-bar input{width:100%;background:#16213e;border:1px solid #3a3a6a;border-radius:10px;color:#fff;padding:9px 14px;font-size:.95rem;outline:none}
  .search-bar input:focus{border-color:#7c83fd}

  #clipList{flex:1;overflow-y:auto;padding:8px 16px 32px;display:flex;flex-direction:column;gap:8px}

  .card{background:#16213e;border-radius:12px;padding:12px 14px;display:flex;align-items:flex-start;gap:10px;border:1px solid #2a2a4a}
  .card.new{border-color:#6fcf97;animation:flash 1.5s ease-out forwards}
  @keyframes flash{0%{background:#1a472a}100%{background:#16213e}}
  .ctext{flex:1;font-size:.88rem;line-height:1.5;word-break:break-word;color:#ddd;overflow:hidden;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical}
  .cmeta{font-size:.7rem;color:#556;margin-top:3px}
  .cbtns{display:flex;flex-direction:column;gap:5px;flex-shrink:0}
  .ibtn{background:#0f3460;border:none;border-radius:8px;color:#aaa;padding:7px 9px;cursor:pointer;font-size:.85rem}
  .ibtn:active{background:#7c83fd;color:#fff}

  .toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#7c83fd;color:#fff;padding:10px 22px;border-radius:999px;font-size:.88rem;opacity:0;transition:opacity .3s;pointer-events:none;z-index:100;white-space:nowrap}
  .toast.show{opacity:1}
  .empty{text-align:center;padding:48px 24px;color:#555}
</style>
</head>
<body>

<header>
  <h1>📋 ClipVault</h1>
  <div id="status" class="off">Connecting…</div>
</header>

<!-- FIX Issue 1: Simple type/paste box — no auto-sync magic, user is in control -->
<div id="sendBox">
  <textarea id="input" placeholder="Type here, or paste (long-press → Paste) to send to PC…"></textarea>
  <button id="sendBtn" onclick="sendInput()">Send</button>
</div>

<div class="search-bar">
  <input type="search" id="srch" placeholder="Search history…" oninput="filter()"/>
</div>

<div id="clipList"><div class="empty"><p>Connecting…</p></div></div>
<div class="toast" id="toast"></div>

<script>
const WS_PORT = {{WS_PORT}};
let ws, clips = [];

// ── WebSocket ─────────────────────────────────────────────────────────────────
function connect(){
  ws = new WebSocket(`ws://${location.hostname}:${WS_PORT}`);
  ws.onopen  = () => setStatus('🟢 Connected','on');
  ws.onclose = () => { setStatus('🔴 Disconnected','off'); setTimeout(connect, 3000); };
  ws.onerror = () => ws.close();
  ws.onmessage = ({data}) => {
    const msg = JSON.parse(data);
    if(msg.action === 'history'){
      // FIX Issue 2: Replace entire list from server — don't locally add again
      clips = msg.clips || [];
      render(clips);
    } else if(msg.action === 'clip'){
      // FIX Issue 2: This is a clip from PC or another phone — add once
      clips.unshift({content: msg.content, preview: msg.preview, timestamp: new Date().toLocaleTimeString()});
      render(clips, true);
    }
  };
}

function setStatus(t, c){
  const el = document.getElementById('status');
  el.textContent = t; el.className = c;
}

// ── Send ──────────────────────────────────────────────────────────────────────
function sendInput(){
  const ta = document.getElementById('input');
  const text = ta.value.trim();
  if(!text){ toast('Nothing to send'); return; }
  if(!ws || ws.readyState !== WebSocket.OPEN){ toast('Not connected'); return; }

  // FIX Issue 2: Send to server only — do NOT add to clips[] locally here.
  // Server will NOT echo back to sender, so we add it once manually:
  ws.send(JSON.stringify({action: 'clip', content: text}));
  clips.unshift({content: text, preview: text.slice(0,80), timestamp: new Date().toLocaleTimeString()});
  render(clips, true);

  ta.value = '';
  ta.style.height = '70px';
  toast('✅ Sent to PC!');
}

// Ctrl+Enter or Enter (if no shift) to send
document.getElementById('input').addEventListener('keydown', e => {
  if(e.key === 'Enter' && !e.shiftKey){
    e.preventDefault();
    sendInput();
  }
});

// ── Render ────────────────────────────────────────────────────────────────────
function filter(){
  const q = document.getElementById('srch').value.toLowerCase();
  render(q ? clips.filter(c => c.content?.toLowerCase().includes(q)) : clips);
}

function render(list, hi = false){
  const el = document.getElementById('clipList');
  if(!list.length){
    el.innerHTML = '<div class="empty"><p>No clips yet</p></div>';
    return;
  }
  el.innerHTML = list.map((c, i) => `
    <div class="card ${hi && i===0 ? 'new' : ''}">
      <div style="flex:1;min-width:0">
        <div class="ctext">${esc(c.content || c.preview || '')}</div>
        <div class="cmeta">${c.timestamp || ''}</div>
      </div>
      <div class="cbtns">
        <button class="ibtn" onclick="copyItem(${i})" title="Copy on phone">📋</button>
        <button class="ibtn" onclick="sendItem(${i})" title="Send to PC">💻</button>
      </div>
    </div>`).join('');
}

function copyItem(i){
  const t = clips[i]?.content;
  if(!t) return;
  navigator.clipboard.writeText(t)
    .then(() => toast('Copied!'))
    .catch(() => {
      const a = document.createElement('textarea');
      a.value = t; document.body.appendChild(a);
      a.select(); document.execCommand('copy');
      document.body.removeChild(a); toast('Copied!');
    });
}

function sendItem(i){
  const t = clips[i]?.content;
  if(!t || !ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({action: 'clip', content: t}));
  // Move to top visually
  clips.splice(i, 1);
  clips.unshift({content: t, preview: t.slice(0,80), timestamp: new Date().toLocaleTimeString()});
  render(clips, true);
  toast('✅ Sent to PC!');
}

function toast(msg){
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  clearTimeout(t._t);
  t._t = setTimeout(() => t.classList.remove('show'), 2500);
}

function esc(t){
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

connect();
</script>
</body>
</html>
"""
