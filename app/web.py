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
html,body{height:100%}body{height:100vh;overflow:hidden}
.wrap{max-width:680px;margin:0 auto;padding:20px 14px 12px;height:100vh;display:flex;flex-direction:column}
header{background:#111827;color:#fff;border-radius:16px;padding:18px 20px;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center;gap:12px}
header h1{margin:0 0 4px;font-size:22px}header p{margin:0;color:#d1d5db;font-size:14px}
header .dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#22c55e;margin-right:6px}
header button{background:#374151;color:#fff;border:1px solid #4b5563;border-radius:999px;padding:8px 14px;cursor:pointer;white-space:nowrap}
#log{background:#fff;border-radius:16px;padding:16px;flex:1;overflow-y:auto;min-height:0;box-shadow:0 2px 12px rgba(0,0,0,.08)}
header,form,.note{flex-shrink:0}
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
<title>Print247 Admin</title>
<style>body{font-family:system-ui,sans-serif;max-width:960px;margin:30px auto;padding:0 16px;color:#1f2937}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:8px;text-align:left;vertical-align:top}
button{padding:7px 14px;margin:2px;cursor:pointer}input,textarea,select{width:100%;padding:8px;margin:4px 0}
pre{background:#f4f4f4;padding:12px;white-space:pre-wrap}.card{border:1px solid #d1d5db;border-radius:12px;padding:16px;margin:16px 0}
.help{color:#4b5563;font-size:14px}.warn{color:#b45309}h2{margin-top:32px}</style></head>
<body><h1>Print247 Admin</h1>
<p class="help"><b>Sirf 3 kaam hain:</b> 1) Neeche wali chat mein se <b>Draft KB</b> dabao — poori chat ki ek file ban jaye gi. 2) Us file ko parho, sahi fact likho, <b>Approve</b> karo. 3) <b>Re-ingest</b> dabao — tab bot seekhe ga. Bas.</p>

<h2>1. Chats — har session ek hi chat hai</h2>
<p class="help">Har row poori baat-cheet hai, har message alag row nahi. <b>Chat dekho</b> par poori conversation khulti hai, <b>Draft KB</b> par us poori chat ki ek file ban jati hai.</p>
<button onclick="autoDraftAll()">Sab chats se auto-draft banao</button>
<div id="sessions">Loading…</div>
<div class="card" id="sessionDetail" style="display:none"><h3>Poori chat</h3><pre id="stranscript"></pre>
<button onclick="draftCurrentSession()">Is chat se Draft KB banao</button><button onclick="closeSession()">Band karo</button></div>

<div class="card" id="detail" style="display:none"><h3>Step 2 — File parho, sahi fact likho, phir Approve karo</h3><h3 id="dtitle"></h3><p id="dmeta"></p><p id="dwarn" class="warn"></p>
<textarea id="dbody" rows="12"></textarea><br>
<button onclick="saveDetail()">Save edits</button><button onclick="approveDetail()">Approve this file</button>
<button onclick="closeDetail()">Close</button><span id="dmsg"></span></div>

<h2>2. Approve karo — drafts sab se upar hain</h2>
<p class="help">Draft wali files upar hain. <b>View</b> par file khulti hai, wahan fact likho, <b>Save</b> karo, <b>Approve</b> karo. Verified files neeche hain, un ko kuch karne ki zaroorat nahi.</p>
<div id="kb">Loading…</div>

<h2>3. Deploy — bot ko sikhana</h2>
<button onclick="ingest()">Re-ingest KB into Qdrant</button>
<button onclick="runtests()">Run golden + chat tests</button>
<p class="help"><b>Re-ingest</b> = asli training. Is ke baad hi bot nayi approved files se jawab de ga. <b>Tests</b> = 16 golden sawal + 11 chat rules; koi fail ho to deploy theek nahi.</p>
<pre id="out"></pre>

<h2>Nayi file khud likhni ho to (optional)</h2>
<form onsubmit="return createOkf(event)">
<input id="fid" placeholder="id, e.g. fact-samples-custom" required>
<select id="fcat"><option>facts</option><option>products</option><option>materials</option><option>policies</option></select>
<input id="ftitle" placeholder="Title" required>
<input id="fsource" placeholder="Source, e.g. print247.us/faq" required>
<textarea id="fbody" rows="6" placeholder="Facts, one concept only. Source + context on every fact." required></textarea>
<button>Create as draft</button></form>
<p class="help">Ye sirf draft banata hai. Bot tabhi seekhe ga jab Approve + Re-ingest ho.</p>
<script>
let curId=null,curSession=null;
async function loadKb(){const r=await fetch('/api/admin/kb');const d=await r.json();
document.getElementById('kb').innerHTML='<table><tr><th>File</th><th>Status</th><th>Action</th></tr>'+d.map(f=>
`<tr><td>${f.path}</td><td>${f.status}</td><td><button onclick="viewKb('${f.id}')">View</button>${f.status==='draft'?`<button onclick="approve('${f.id}')">Approve</button>`:''}</td></tr>`).join('')+'</table>';}
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
async function loadSessions(){const r=await fetch('/api/admin/logs');const d=await r.json();window._sessions=d;
document.getElementById('sessions').innerHTML=d.length?'<table><tr><th>Chat (pehla message)</th><th>Messages</th><th>Action</th></tr>'+d.map((s,i)=>
`<tr><td>${s.first_message}<br><small>${s.session_id} • ${s.started_at||''}</small></td><td>${s.count}</td><td><button onclick="viewSession(${i})">Chat dekho</button><button onclick="draftSession('${s.session_id}')">Draft KB</button></td></tr>`).join('')+'</table>':'No chats yet — send a chat from the chat page first.';}
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
loadKb();loadSessions();</script></body></html>"""
