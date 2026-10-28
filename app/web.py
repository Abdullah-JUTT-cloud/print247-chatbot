"""Chat UI + Admin dashboard pages — plain HTML, no build step.

Why no framework: the user asked for speed and a working admin
now, not a React build pipeline. These two pages are served by
FastAPI itself, talk to the same /chat and /api/admin endpoints,
and are enough to demo, test and approve KB files.

SECURITY NOTE (read before production): /admin has NO login in
this dev version. It is for local/staging use only. Before any
public deployment, put it behind a login (see README) — otherwise
anyone could edit the knowledge base.
"""

CHAT_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Print247 Chat</title>
<style>
*{box-sizing:border-box}body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#eef1f5;color:#1f2937}
.wrap{max-width:680px;margin:0 auto;padding:20px 14px 28px}
header{background:#111827;color:#fff;border-radius:16px;padding:18px 20px;margin-bottom:14px}
header h1{margin:0 0 4px;font-size:22px}header p{margin:0;color:#d1d5db;font-size:14px}
header .dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#22c55e;margin-right:6px}
#log{background:#fff;border-radius:16px;padding:16px;min-height:420px;box-shadow:0 2px 12px rgba(0,0,0,.08)}
.row{display:flex;margin:10px 0}.row.me{justify-content:flex-end}
.bubble{max-width:82%;padding:11px 14px;border-radius:16px;line-height:1.5;font-size:15px;white-space:pre-wrap;word-wrap:break-word}
.bot .bubble{background:#f3f4f6;border-bottom-left-radius:4px}
.me .bubble{background:#2563eb;color:#fff;border-bottom-right-radius:4px}
.avatar{width:32px;height:32px;border-radius:50%;background:#111827;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;margin-right:8px;flex-shrink:0}
.src{font-size:12px;color:#6b7280;margin:2px 0 2px 40px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 6px 40px}
.chip{border:1px solid #2563eb;color:#2563eb;background:#fff;border-radius:999px;padding:7px 13px;cursor:pointer;font-size:13px}
.chip:hover{background:#2563eb;color:#fff}
.typing{display:flex;gap:4px;align-items:center}.typing span{width:8px;height:8px;border-radius:50%;background:#9ca3af;animation:b 1s infinite}
.typing span:nth-child(2){animation-delay:.15s}.typing span:nth-child(3){animation-delay:.3s}
@keyframes b{0%,100%{transform:translateY(0);opacity:.5}50%{transform:translateY(-4px);opacity:1}}
form{display:flex;gap:10px;margin-top:14px}
input{flex:1;padding:13px 16px;border-radius:999px;border:1px solid #d1d5db;font-size:15px;outline:none}
input:focus{border-color:#2563eb}
button.send{background:#2563eb;color:#fff;border:none;border-radius:999px;padding:13px 22px;font-size:15px;cursor:pointer}
button.send:disabled{opacity:.5;cursor:default}
.note{text-align:center;color:#6b7280;font-size:12px;margin-top:10px}
</style></head>
<body><div class="wrap">
<header><h1>Print247</h1><p><span class="dot"></span>Online — replies from our packaging assistant</p></header>
<div id="log"></div>
<form onsubmit="return send(event)"><input id="q" placeholder="Type your message…" autocomplete="off">
<button class="send" id="sendBtn" type="submit">Send</button></form>
<p class="note">Prices depend on your exact spec — the bot collects it and gives you the quote path.</p>
</div>
<script>
const log=document.getElementById('log'),q=document.getElementById('q'),btn=document.getElementById('sendBtn');
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function chipsHTML(sugs){if(!sugs||!sugs.length)return '';
return '<div class="chips">'+sugs.map(s=>`<button class="chip" onclick="quick(${JSON.stringify(s).replace(/"/g,'&quot;')})">${esc(s)}</button>`).join('')+'</div>';}
function addBot(text,sugs,sources){log.innerHTML+=`<div class="row bot"><div class="avatar">P</div><div><div class="bubble">${esc(text)}</div></div></div>`
+chipsHTML(sugs)+(sources&&sources.length?`<div class="src">Sources: ${esc(sources.join(', '))}</div>`:'');log.scrollTop=log.scrollHeight;}
function addMe(t){log.innerHTML+=`<div class="row me"><div class="bubble">${esc(t)}</div></div>`;log.scrollTop=log.scrollHeight;}
function typingRow(){const d=document.createElement('div');d.className='row bot';d.id='typing';
d.innerHTML='<div class="avatar">P</div><div class="bubble typing"><span></span><span></span><span></span></div>';log.appendChild(d);log.scrollTop=log.scrollHeight;}
function quick(t){q.value=t;send(new Event('submit'));}
async function send(e){e.preventDefault();const t=q.value.trim();if(!t||btn.disabled)return;
addMe(t);q.value='';btn.disabled=true;typingRow();
try{const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({message:t,session_id:'web-ui'})});const d=await r.json();
document.getElementById('typing').remove();addBot(d.reply,d.suggestions||[],d.sources||[]);}
catch(err){document.getElementById('typing').remove();addBot('Sorry, something went wrong. Please try again.',[]);}
btn.disabled=false;q.focus();return false;}
// Predefined greeting, already in the chat on load — no empty screen.
addBot("Hi! I'm the Print247 assistant. I can help with products, sizes, quantities, shipping and refunds. What are you looking to have made?",
["I need mylar bags","I need custom boxes","I need labels","Is shipping free?"],[]);
</script></body></html>"""

ADMIN_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Print247 Admin — KB Approval</title>
<style>body{font-family:system-ui,sans-serif;max-width:900px;margin:30px auto;padding:0 16px}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:6px;text-align:left}
button{padding:6px 12px;margin:2px}input,textarea,select{width:100%;padding:8px;margin:4px 0}
pre{background:#f4f4f4;padding:12px;white-space:pre-wrap}</style></head>
<body><h1>Print247 Admin (dev only — no login yet)</h1>
<p>Workflow: new question appears in Unanswered → write an OKF file → Approve it → Re-ingest → Run golden tests. Nothing reaches the bot until it is approved AND re-ingested.</p>
<h2>Knowledge base files</h2><div id="kb">Loading…</div>
<h2>Create a new OKF file</h2>
<form onsubmit="return createOkf(event)">
<input id="fid" placeholder="id, e.g. fact-samples-custom" required>
<select id="fcat"><option>facts</option><option>products</option><option>materials</option><option>policies</option></select>
<input id="ftitle" placeholder="Title" required>
<input id="fsource" placeholder="Source, e.g. print247.us/faq" required>
<textarea id="fbody" rows="6" placeholder="Facts, one concept only. Source + context on every fact." required></textarea>
<button>Create as draft</button></form>
<h2>Unanswered / handed-off chats (latest first)</h2><div id="logs">Loading…</div>
<h2>Deploy: re-ingest + golden tests</h2>
<button onclick="ingest()">Re-ingest KB into Qdrant</button>
<button onclick="runtests()">Run golden + chat tests</button>
<pre id="out"></pre>
<script>
async function loadKb(){const r=await fetch('/api/admin/kb');const d=await r.json();
document.getElementById('kb').innerHTML='<table><tr><th>File</th><th>Status</th><th>Action</th></tr>'+d.map(f=>
`<tr><td>${f.path}</td><td>${f.status}</td><td>${f.status==='draft'?`<button onclick="approve('${f.id}')">Approve</button>`:''}</td></tr>`).join('')+'</table>';}
async function approve(id){await fetch('/api/admin/okf/'+encodeURIComponent(id)+'/approve',{method:'POST'});
document.getElementById('out').textContent='Approved '+id+' — now press Re-ingest.';loadKb();}
async function createOkf(e){e.preventDefault();const b={id:fid.value,title:ftitle.value,category:fcat.value,source:fsource.value,body:fbody.value};
const r=await fetch('/api/admin/okf',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
const d=await r.json();document.getElementById('out').textContent=JSON.stringify(d,null,2);loadKb();return false;}
async function loadLogs(){const r=await fetch('/api/admin/logs');const d=await r.json();
document.getElementById('logs').innerHTML=d.length?'<table><tr><th>Message</th><th>Sources</th><th>Handoff</th></tr>'+d.map(l=>
`<tr><td>${l.message}</td><td>${(l.sources||[]).join(', ')}</td><td>${l.handoff||''}</td></tr>`).join('')+'</table>':'No logged chats yet — send a chat from the chat page first.';}
async function ingest(){const r=await fetch('/api/admin/ingest',{method:'POST'});document.getElementById('out').textContent=await r.text();}
async function runtests(){const r=await fetch('/api/admin/test',{method:'POST'});document.getElementById('out').textContent=await r.text();}
loadKb();loadLogs();</script></body></html>"""
