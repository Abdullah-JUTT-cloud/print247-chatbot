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
<style>body{font-family:system-ui,sans-serif;max-width:640px;margin:40px auto;padding:0 16px}
#log{border:1px solid #ccc;border-radius:8px;padding:12px;min-height:300px}
.msg{margin:8px 0}.me{text-align:right}.src{font-size:12px;color:#666}
input{width:75%;padding:10px}button{padding:10px 16px}</style></head>
<body><h1>Print247 Chat</h1><p>Ask about products, shipping, refunds, sizes and more.</p>
<div id="log"></div><p><input id="q" placeholder="Type your message…">
<button onclick="send()">Send</button></p>
<script>async function send(){const q=document.getElementById('q');const t=q.value;if(!t)return;
const log=document.getElementById('log');log.innerHTML+=`<div class="msg me"><b>You:</b> ${t}</div>`;q.value='';
const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({message:t,session_id:'web-ui'})});const d=await r.json();
log.innerHTML+=`<div class="msg"><b>Bot:</b> ${d.reply}</div><div class="src">Sources: ${(d.sources||[]).join(', ')||'none'}${d.handoff?' • handoff: '+d.handoff:''}</div>`;}
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter')send();});</script>
</body></html>"""

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
