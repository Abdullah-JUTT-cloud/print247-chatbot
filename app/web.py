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

from .chat_ui import CHAT_HTML

ADMIN_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Print247 Admin</title>
<style>body{font-family:system-ui,sans-serif;max-width:960px;margin:30px auto;padding:0 16px;background:#0a0a0a;color:#e5e7eb}
h1,h2{color:#f9fafb}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #374151;padding:8px;text-align:left;vertical-align:top}
th{background:#1f2937}
button{padding:7px 14px;margin:2px;cursor:pointer;background:#f97316;color:#111827;border:none;border-radius:8px;font-weight:700}input,textarea,select{width:100%;padding:8px;margin:4px 0;background:#1f2937;border:1px solid #374151;color:#e5e7eb;border-radius:8px}
pre{background:#1f2937;color:#e5e7eb;padding:12px;white-space:pre-wrap}.card{border:1px solid #374151;background:#111111;border-radius:12px;padding:16px;margin:16px 0}
.help{color:#9ca3af;font-size:14px}.warn{color:#fbbf24}h2{margin-top:32px}</style></head>
<body><h1>Print247 Admin</h1><p id="serverstatus" class="help">Server check ho raha hai…</p><noscript><p class="warn">JavaScript band hai is browser mein — neeche wali lists server se aayi hain, buttons ke liye JavaScript chahiye.</p></noscript><p class="help"><a href="/admin?view=pending">Sirf pending dikhao (baki kaam chhupao)</a> | <a href="/admin">Sab kuch dikhao</a></p>
<p class="help"><b>Sirf 3 kaam hain:</b> 1) Neeche wali chat mein se <b>Draft KB</b> dabao — poori chat ki ek file ban jaye gi. 2) Us file ko parho, sahi fact likho, <b>Approve</b> karo. 3) <b>Re-ingest</b> dabao — tab bot seekhe ga. Bas.</p>

<h2>1. Chats — har session ek hi chat hai</h2>
<p class="help">Har row poori baat-cheet hai, har message alag row nahi. <b>Chat dekho</b> par poori conversation khulti hai, <b>Draft KB</b> par us poori chat ki ek file ban jati hai.</p>
<form method="post" action="/admin/auto-draft-all" style="display:inline"><button>Sab chats se auto-draft banao</button></form>
<div id="sessions">{{SESSION_ROWS}}</div>
<div class="card" id="sessionDetail" style="display:none"><h3>Poori chat</h3><pre id="stranscript"></pre>
<button onclick="draftCurrentSession()">Is chat se Draft KB banao</button><button onclick="closeSession()">Band karo</button></div>

<div class="card" id="detail" style="display:none"><h3>Step 2 — File parho, sahi fact likho, phir Approve karo</h3><h3 id="dtitle"></h3><p id="dmeta"></p><p id="dwarn" class="warn"></p>
<textarea id="dbody" rows="12"></textarea><br>
<button onclick="saveDetail()">Save edits</button><button onclick="approveDetail()">Approve this file</button>
<button onclick="closeDetail()">Close</button><span id="dmsg"></span></div>

<h2>2. Approve karo — drafts sab se upar hain</h2>
<p class="help">Draft wali files upar hain. <b>View</b> par file khulti hai, wahan fact likho, <b>Save</b> karo, <b>Approve</b> karo. Verified files neeche hain, un ko kuch karne ki zaroorat nahi.</p>
<div id="kb">{{KB_ROWS}}</div>

<h2>3. Deploy — bot ko sikhana</h2>
<form method="post" action="/admin/ingest" style="display:inline"><button>Re-ingest KB into Qdrant</button></form>
<form method="post" action="/admin/test" style="display:inline"><button>Run golden + chat tests</button></form>
<p class="help"><b>Re-ingest</b> = asli training. Is ke baad hi bot nayi approved files se jawab de ga. <b>Tests</b> = 16 golden sawal + 11 chat rules; koi fail ho to deploy theek nahi.</p>
<pre id="out"></pre>

<h2>Nayi file khud likhni ho to (optional)</h2>
<form method="post" action="/admin/kb/create">
<input name="id" placeholder="id, e.g. fact-samples-custom" required>
<select name="category"><option>facts</option><option>products</option><option>materials</option><option>policies</option></select>
<input name="title" placeholder="Title" required>
<input name="source" placeholder="Source, e.g. print247.us/faq" required>
<textarea name="body" rows="6" placeholder="Facts, one concept only. Source + context on every fact." required></textarea>
<button>Create as draft</button></form>
<p class="help">Ye sirf draft banata hai. Bot tabhi seekhe ga jab Approve + Re-ingest ho.</p>
<script>
let curId=null,curSession=null;
async function loadKb(){try{const c=new AbortController();setTimeout(()=>c.abort(),8000);
const r=await fetch('/api/admin/kb',{signal:c.signal});const d=await r.json();
if(!Array.isArray(d))throw new Error('Server ne list nahi bheji (status '+r.status+')');
document.getElementById('kb').innerHTML='<table><tr><th>File</th><th>Status</th><th>Action</th></tr>'+d.map(f=>
`<tr><td>${f.path}</td><td>${f.status}</td><td><button onclick="viewKb('${f.id}')">View</button>${f.status==='draft'?`<button onclick="approve('${f.id}')">Approve</button>`:''}</td></tr>`).join('')+'</table>';}
catch(e){document.getElementById('kb').innerHTML='<p class="warn">KB list load nahi hui ('+e.message+'). Server down ho sakta hai ya purana code chal raha hai — pehle pull + rebuild karo, phir <button onclick="loadKb()">Retry</button> dabao.</p>';}}
async function viewKb(id){const r=await fetch('/api/admin/kb/'+encodeURIComponent(id));const d=await r.json();
if(!d.ok){document.getElementById('out').textContent=JSON.stringify(d);return;}
curId=id;document.getElementById('detail').style.display='block';
document.getElementById('dtitle').textContent=d.title+' ('+d.path+')';
document.getElementById('dmeta').textContent='Status: '+d.status+' • Source: '+d.source;
document.getElementById('dbody').value=d.body;document.getElementById('dmsg').textContent='';
document.getElementById('dwarn').textContent=d.body.includes('VERIFIED FACT — admin must write')?'⚠ Placeholder abhi maujood hai — pehle sahi fact likho, warna Approve nahi hoga.':'';}
function closeDetail(){document.getElementById('detail').style.display='none';curId=null;}
async function saveDetail(){const v=document.getElementById('dbody').value;
await fetch('/api/admin/okf/'+encodeURIComponent(curId)+'/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({body:v})});
document.getElementById('dmsg').textContent=v.includes('VERIFIED FACT — admin must write')?'Saved, lekin placeholder abhi bhi hai — pehle fact likho, phir Approve karo.':'Saved. Now Approve, then Re-ingest.';
document.getElementById('dwarn').textContent=v.includes('VERIFIED FACT — admin must write')?'⚠ Placeholder abhi maujood hai — pehle sahi fact likho, warna Approve nahi hoga.':'';}
async function approveDetail(){const r=await fetch('/api/admin/okf/'+encodeURIComponent(curId)+'/approve',{method:'POST'});const d=await r.json();
if(!d.ok){document.getElementById('dmsg').textContent='Approve nahi hua: '+d.error;return;}
document.getElementById('out').textContent='Approved '+curId+' — now press Re-ingest.';loadKb();viewKb(curId);}
async function approve(id){const r=await fetch('/api/admin/okf/'+encodeURIComponent(id)+'/approve',{method:'POST'});const d=await r.json();
document.getElementById('out').textContent=d.ok?('Approved '+id+' — now press Re-ingest.'):('Approve nahi hua: '+d.error);loadKb();}
async function createOkf(e){e.preventDefault();const b={id:fid.value,title:ftitle.value,category:fcat.value,source:fsource.value,body:fbody.value};
const r=await fetch('/api/admin/okf',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
const d=await r.json();document.getElementById('out').textContent=JSON.stringify(d,null,2);loadKb();return false;}
async function loadSessions(){try{const c=new AbortController();setTimeout(()=>c.abort(),8000);
const r=await fetch('/api/admin/logs',{signal:c.signal});const d=await r.json();
if(!Array.isArray(d))throw new Error('Server ne chats nahi bheji (status '+r.status+')');
window._sessions=d;
document.getElementById('sessions').innerHTML=d.length?'<table><tr><th>Chat (pehla message)</th><th>Messages</th><th>Action</th></tr>'+d.map((s,i)=>
`<tr><td>${s.first_message}<br><small>${s.session_id} • ${s.started_at||''}</small></td><td>${s.count}</td><td><button onclick="viewSession(${i})">Chat dekho</button><button onclick="draftSession('${s.session_id}')">Draft KB</button></td></tr>`).join('')+'</table>':'No chats yet — send a chat from the chat page first.';}
catch(e){document.getElementById('sessions').innerHTML='<p class="warn">Chats load nahi hui ('+e.message+'). Server down ho sakta hai ya purana code chal raha hai — pehle pull + rebuild karo, phir <button onclick="loadSessions()">Retry</button> dabao.</p>';}}
function viewSession(i){const s=window._sessions[i];curSession=s.session_id;
document.getElementById('sessionDetail').style.display='block';
document.getElementById('stranscript').textContent=s.messages.map(m=>'Visitor: '+m.message+'\nBot: '+m.reply).join('\n\n');}
function closeSession(){document.getElementById('sessionDetail').style.display='none';curSession=null;}
async function draftSession(sid){const r=await fetch('/api/admin/draft-from-session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sid})});
const d=await r.json();document.getElementById('out').textContent=JSON.stringify(d,null,2);loadKb();if(d.id)viewKb(d.id);}
async function draftCurrentSession(){if(curSession)draftSession(curSession);}
async function autoDraftAll(){const r=await fetch('/api/admin/auto-draft-all',{method:'POST'});const d=await r.json();
document.getElementById('out').textContent=JSON.stringify(d,null,2);loadKb();}
async function ingest(){const r=await fetch('/api/admin/ingest',{method:'POST'});document.getElementById('out').textContent=await r.text();}
async function runtests(){const r=await fetch('/api/admin/test',{method:'POST'});document.getElementById('out').textContent=await r.text();}
loadKb();loadSessions();(async()=>{try{const r=await fetch('/health');const h=await r.json();document.getElementById('serverstatus').textContent='Server: OK (api='+h.api+', mongo='+h.mongo+', qdrant='+h.qdrant+') — agar upar Loading hi rahe to page ko hard refresh karo (Ctrl+Shift+R).';}catch(e){document.getElementById('serverstatus').textContent='Server: NAHI MIL RAHA — API container down hai. docker compose ps aur docker compose logs api check karo.';}})();</script></body></html>"""
