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
header{background:#111827;color:#fff;border-radius:16px;padding:18px 20px;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center;gap:12px}
header h1{margin:0 0 4px;font-size:22px}header p{margin:0;color:#d1d5db;font-size:14px}
header .dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#22c55e;margin-right:6px}
header button{background:#374151;color:#fff;border:1px solid #4b5563;border-radius:999px;padding:8px 14px;cursor:pointer;white-space:nowrap}
#log{background:#fff;border-radius:16px;padding:16px;min-height:420px;box-shadow:0 2px 12px rgba(0,0,0,.08)}
.row{display:flex;margin:10px 0}.row.me{justify-content:flex-end}
.bubble{max-width:82%;padding:11px 14px;border-radius:16px;line-height:1.5;font-size:15px;white-space:pre-wrap;word-wrap:break-word}
.bot .bubble{background:#f3f4f6;border-bottom-left-radius:4px}
.me .bubble{background:#2563eb;color:#fff;border-bottom-right-radius:4px}
.avatar{width:32px;height:32px;border-radius:50%;background:#111827;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;margin-right:8px;flex-shrink:0}
.src{font-size:12px;color:#6b7280;margin:2px 0 2px 40px}
.replybtn{font-size:12px;color:#2563eb;background:none;border:none;cursor:pointer;padding:2px 0 0 40px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 6px 40px}
.chip{border:1px solid #2563eb;color:#2563eb;background:#fff;border-radius:999px;padding:7px 13px;cursor:pointer;font-size:13px}
.chip:hover{background:#2563eb;color:#fff}
.quote{background:#e5e7eb;border-left:3px solid #9ca3af;padding:6px 10px;margin-bottom:6px;font-size:13px;color:#374151;white-space:pre-wrap}
.me .quote{background:rgba(255,255,255,.2);border-color:#bfdbfe;color:#dbeafe}
#replybar{display:none;background:#fef3c7;border-radius:12px;padding:10px 14px;margin-top:14px;font-size:13px}
#replybar button{float:right;background:none;border:none;cursor:pointer;font-size:15px}
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
<header><div><h1>Print247</h1><p><span class="dot"></span>Online — replies from our packaging assistant</p></div>
<button onclick="newChat()">+ New chat</button></header>
<div id="log"></div>
<div id="replybar"><button onclick="cancelReply()">✕</button>Replying to: <span id="replytext"></span></div>
<form onsubmit="return send(event)"><input id="q" placeholder="Type your message…" autocomplete="off">
<button class="send" id="sendBtn" type="submit">Send</button></form>
<p class="note">Prices depend on your exact spec — the bot collects it and gives you the quote path.</p>
</div>
<script>
const log=document.getElementById('log'),q=document.getElementById('q'),btn=document.getElementById('sendBtn');
let sessionId=localStorage.getItem('p247_session')||'web-ui';
localStorage.setItem('p247_session',sessionId);
let pendingReply=null;
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function chipsHTML(sugs){if(!sugs||!sugs.length)return '';
return '<div class="chips">'+sugs.map(s=>`<button class="chip" onclick="quick(${JSON.stringify(s).replace(/"/g,'&quot;')})">${esc(s)}</button>`).join('')+'</div>';}
function addBot(text,sugs,sources){const safe=esc(text);
log.innerHTML+=`<div class="row bot"><div class="avatar">P</div><div><div class="bubble">${safe}</div>
<button class="replybtn" onclick="setReply(${JSON.stringify(text).replace(/"/g,'&quot;')})">↩ Reply</button></div></div>`
+chipsHTML(sugs)+(sources&&sources.length?`<div class="src">Sources: ${esc(sources.join(', '))}</div>`:'');log.scrollTop=log.scrollHeight;saveLocal();}
function addMe(t,quote){log.innerHTML+=`<div class="row me"><div class="bubble">${quote?`<div class="quote">${esc(quote)}</div>`:''}${esc(t)}</div></div>`;log.scrollTop=log.scrollHeight;saveLocal();}
function setReply(t){pendingReply=t;document.getElementById('replytext').textContent=t.slice(0,120);
document.getElementById('replybar').style.display='block';q.focus();}
function cancelReply(){pendingReply=null;document.getElementById('replybar').style.display='none';}
function typingRow(){const d=document.createElement('div');d.className='row bot';d.id='typing';
d.innerHTML='<div class="avatar">P</div><div class="bubble typing"><span></span><span></span><span></span></div>';log.appendChild(d);log.scrollTop=log.scrollHeight;}
function quick(t){q.value=t;send(new Event('submit'));}
function saveLocal(){try{localStorage.setItem('p247_chat_'+sessionId,log.innerHTML);}catch(e){}}
function restoreLocal(){const h=localStorage.getItem('p247_chat_'+sessionId);if(h){log.innerHTML=h;log.scrollTop=log.scrollHeight;return true;}return false;}
async function send(e){e.preventDefault();const t=q.value.trim();if(!t||btn.disabled)return;
const quote=pendingReply;addMe(t,quote);q.value='';cancelReply();btn.disabled=true;typingRow();
try{const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({message:t,session_id:sessionId,reply_to:quote})});const d=await r.json();
document.getElementById('typing').remove();addBot(d.reply,d.suggestions||[],d.sources||[]);}
catch(err){document.getElementById('typing').remove();addBot('Sorry, something went wrong. Please try again.',[]);}
btn.disabled=false;q.focus();return false;}
function newChat(){sessionId=(crypto.randomUUID?crypto.randomUUID():String(Date.now()));
localStorage.setItem('p247_session',sessionId);log.innerHTML='';greet();}
function greet(){addBot("Hi! I'm the Print247 assistant. I can help with products, sizes, quantities, shipping and refunds. What are you looking to have made?",
["I need mylar bags","I need custom boxes","I need labels","Is shipping free?"],[]);}
// Restore the saved session first (server history, with local backup).
// A refresh keeps the chat; New chat starts a fresh session on purpose.
(async function(){try{const r=await fetch('/api/chat/history?session_id='+encodeURIComponent(sessionId));const h=await r.json();
if(h&&h.length){h.forEach(m=>{if(m.reply_to)addMe(m.message,m.reply_to);else addMe(m.message);addBot(m.reply,m.suggestions||[],m.sources||[]);});return;}}catch(e){}
if(!restoreLocal())greet();})();
</script></body></html>"""

ADMIN_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Print247 Admin — KB Approval</title>
<style>body{font-family:system-ui,sans-serif;max-width:960px;margin:30px auto;padding:0 16px;color:#1f2937}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:6px;text-align:left;vertical-align:top}
button{padding:6px 12px;margin:2px;cursor:pointer}input,textarea,select{width:100%;padding:8px;margin:4px 0}
pre{background:#f4f4f4;padding:12px;white-space:pre-wrap}.card{border:1px solid #d1d5db;border-radius:12px;padding:16px;margin:16px 0}
.help{color:#4b5563;font-size:14px}.ok{color:#15803d}.warn{color:#b45309}</style></head>
<body><h1>Print247 Admin (dev only — no login yet)</h1>
<p class="help">How it works: a new question appears in Unanswered chats → press <b>Draft KB</b> → a draft file is ready → <b>View</b> it, read it, write the verified fact → <b>Approve</b> → <b>Re-ingest</b>. Only after Re-ingest does the bot learn it. A draft alone trains nothing.</p>
<h2>Knowledge base files</h2><div id="kb">Loading…</div>
<div class="card" id="detail" style="display:none"><h3 id="dtitle"></h3><p id="dmeta"></p>
<textarea id="dbody" rows="12"></textarea><br>
<button onclick="saveDetail()">Save edits</button><button onclick="approveDetail()">Approve this file</button>
<button onclick="closeDetail()">Close</button><span id="dmsg"></span></div>
<h2>Create a new OKF file</h2>
<form onsubmit="return createOkf(event)">
<input id="fid" placeholder="id, e.g. fact-samples-custom" required>
<select id="fcat"><option>facts</option><option>products</option><option>materials</option><option>policies</option></select>
<input id="ftitle" placeholder="Title" required>
<input id="fsource" placeholder="Source, e.g. print247.us/faq" required>
<textarea id="fbody" rows="6" placeholder="Facts, one concept only. Source + context on every fact." required></textarea>
<button>Create as draft</button></form>
<p class="help"><b>Create as draft</b> only writes a draft file. It does not train the bot. You must Approve it, then Re-ingest.</p>
<h2>Previous chats — turn one into a KB file</h2><div id="logs">Loading…</div>
<p class="help"><b>Draft KB</b> on a chat row creates a ready draft file from that chat: visitor question, bot reply and sources are pre-filled, and the verified fact is left as a placeholder for you to write. View it, verify it, approve it — only then does it count.</p>
<h2>Deploy: re-ingest + golden tests</h2>
<button onclick="ingest()">Re-ingest KB into Qdrant</button>
<button onclick="runtests()">Run golden + chat tests</button>
<p class="help"><b>Re-ingest KB into Qdrant</b> runs the ingest script: every OKF file gets a new embedding and is saved in Qdrant. This is the actual "training" step — after this, the bot answers from the new file. <b>Run golden + chat tests</b> runs the 15 golden questions and 11 chat rules; if any fail, do not treat the deploy as good — fix first.</p>
<pre id="out"></pre>
<script>
let curId=null;
async function loadKb(){const r=await fetch('/api/admin/kb');const d=await r.json();
document.getElementById('kb').innerHTML='<table><tr><th>File</th><th>Status</th><th>Action</th></tr>'+d.map(f=>
`<tr><td>${f.path}</td><td>${f.status}</td><td><button onclick="viewKb('${f.id}')">View</button>${f.status==='draft'?`<button onclick="approve('${f.id}')">Approve</button>`:''}</td></tr>`).join('')+'</table>';}
async function viewKb(id){const r=await fetch('/api/admin/kb/'+encodeURIComponent(id));const d=await r.json();
if(!d.ok){document.getElementById('out').textContent=JSON.stringify(d);return;}
curId=id;document.getElementById('detail').style.display='block';
document.getElementById('dtitle').textContent=d.title+' ('+d.path+')';
document.getElementById('dmeta').textContent='Status: '+d.status+' • Source: '+d.source;
document.getElementById('dbody').value=d.body;document.getElementById('dmsg').textContent='';}
function closeDetail(){document.getElementById('detail').style.display='none';curId=null;}
async function saveDetail(){const r=await fetch('/api/admin/okf/'+encodeURIComponent(curId)+'/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({body:document.getElementById('dbody').value})});
document.getElementById('dmsg').textContent='Saved. Now Approve, then Re-ingest.';}
async function approveDetail(){await approve(curId);viewKb(curId);}
async function approve(id){await fetch('/api/admin/okf/'+encodeURIComponent(id)+'/approve',{method:'POST'});
document.getElementById('out').textContent='Approved '+id+' — now press Re-ingest.';loadKb();}
async function createOkf(e){e.preventDefault();const b={id:fid.value,title:ftitle.value,category:fcat.value,source:fsource.value,body:fbody.value};
const r=await fetch('/api/admin/okf',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
const d=await r.json();document.getElementById('out').textContent=JSON.stringify(d,null,2);loadKb();return false;}
async function loadLogs(){const r=await fetch('/api/admin/logs');const d=await r.json();
document.getElementById('logs').innerHTML=d.length?'<table><tr><th>Message</th><th>Sources</th><th>Handoff</th><th>Action</th></tr>'+d.map((l,i)=>
`<tr><td>${l.message}</td><td>${(l.sources||[]).join(', ')}</td><td>${l.handoff||''}</td><td><button onclick="draftLog(${i})">Draft KB</button></td></tr>`).join('')+'</table>':'No logged chats yet — send a chat from the chat page first.';
window._logs=d;}
async function draftLog(i){const l=window._logs[i];
const r=await fetch('/api/admin/draft-from-log',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:l.message,reply:l.reply||'',sources:l.sources||[]})});
const d=await r.json();document.getElementById('out').textContent=JSON.stringify(d,null,2);loadKb();if(d.id)viewKb(d.id);}
async function ingest(){const r=await fetch('/api/admin/ingest',{method:'POST'});document.getElementById('out').textContent=await r.text();}
async function runtests(){const r=await fetch('/api/admin/test',{method:'POST'});document.getElementById('out').textContent=await r.text();}
loadKb();loadLogs();</script></body></html>"""
