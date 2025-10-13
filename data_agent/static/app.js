const clientId = Math.random().toString(36).slice(2,9);
const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/${clientId}`);

ws.addEventListener('open', ()=>{
  console.log('ws open')
  // fetch root filesystem listing on connect
  fetch('/api/list_dir?path=.').then(r=>r.json()).then(d=>{
    if(d.items) renderFsRoot(d.items);
  }).catch(e=>console.error('fs load err',e));
});

ws.addEventListener('message', ev => {
  try{
    const data = JSON.parse(ev.data);
    handleWs(data);
  }catch(e){console.log('bad',e)}
});

function handleWs(msg){
  const t = msg.type;
  if(t === 'list_result'){
    const payload = msg.payload;
    if(payload.error){alert(payload.error);return}
    renderList(payload.items || []);
  } else if(t === 'visualize_result'){
    renderVisualCards(msg.payload || []);
  } else if(t === 'agent_stream'){
    // append partial content to a streaming message
    const incoming = msg.payload.content || '';
    // detect if this chunk encodes a tool-calls array (JSON or python-like repr)
    const toolCalls = parseToolCallsFromString(incoming);
    if(toolCalls){
      // remove any existing streaming partial (we'll render tools instead)
      const existing = document.getElementById('streaming-partial');
      if(existing) existing.remove();
      renderToolCalls(toolCalls);
      return;
    }

    let partial = document.getElementById('streaming-partial');
    if(!partial){
      partial = document.createElement('div');
      partial.id = 'streaming-partial';
      partial.className = 'msg';
      partial.innerHTML = `<div class='meta'>agent (streaming)</div><div class='stream-content'></div>`;
      document.getElementById('messages').appendChild(partial);
    }
    const c = partial.querySelector('.stream-content');
    c.innerHTML = (c.innerHTML || '') + escapeHtml(incoming).replace(/\n/g, '<br>');
  } else if(t === 'agent_stream_end'){
    // finalize streaming message
    const partial = document.getElementById('streaming-partial');
    if(partial){
      partial.removeAttribute('id');
      partial.querySelector('.meta').textContent = 'agent';
    }
  } else if(t === 'echo'){
    appendMessage('agent', JSON.stringify(msg.payload));
  } else if(t === 'tool_calls'){
    // New message type: an array of tool call descriptions
    renderToolCalls(msg.payload || []);
  } else if(t === 'agent_result'){
    // payload is an array of result pieces: [{content: '...'}, ...]
    const pieces = msg.payload || [];
    for(const p of pieces){
      let content = p && p.content != null ? p.content : '';
      // try parsing content as JSON array of tool calls
      // try robustly parse toolcalls (JSON or python-style repr)
      const parsedToolCalls = parseToolCallsFromString(content);
      if(parsedToolCalls){ renderToolCalls(parsedToolCalls); continue; }

      // otherwise treat as agent text
      appendMessage('agent', content);
    }
  }
}

// Try to parse an incoming string as a tool-call array. Handles JSON and a
// heuristic conversion from Python-style reprs (single quotes, None/True/False).
function parseToolCallsFromString(s){
  if(!s || typeof s !== 'string') return null;
  s = s.trim();
  // quick JSON parse
  try{ const parsed = JSON.parse(s); if(Array.isArray(parsed) && parsed.length && parsed[0].name) return parsed; }catch(e){}

  // heuristic: convert common Python literal patterns to JSON
  // Replace None/True/False with JSON equivalents
  let t = s.replace(/\bNone\b/g,'null').replace(/\bTrue\b/g,'true').replace(/\bFalse\b/g,'false');
  // If it looks like a Python list/dict (starts with "[{" or "['"), replace single quotes with double quotes
  if(/^\[\s*\{/.test(t) || /^\[\s*'/.test(t) || /\{\s*'/.test(t)){
    t = t.replace(/'/g,'"');
  }
  try{ const parsed2 = JSON.parse(t); if(Array.isArray(parsed2) && parsed2.length && parsed2[0].name) return parsed2; }catch(e){}
  return null;
}

function appendMessage(role, text){
  const el = document.createElement('div');
  el.className = 'msg';
  el.innerHTML = `<div class='meta'>${role}</div><div>${escapeHtml(text).replace(/\n/g,'<br>')}</div>`;
  document.getElementById('messages').appendChild(el);
  window.scrollTo(0, document.body.scrollHeight);
}

function escapeHtml(unsafe) {
  if (unsafe === null || unsafe === undefined) return '';
  return String(unsafe)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
function renderList(items){
  const tree = document.getElementById('fs-tree');
  tree.innerHTML = '';
  items.forEach(it => {
    const el = document.createElement('div');
    el.className = 'fs-item';
  const caret = document.createElement('div'); caret.className='caret'; caret.textContent = it.is_dir ? '▶' : '';
  const icon = document.createElement('div'); icon.className='icon'; icon.textContent = it.is_dir ? '📁' : '📄';
  const name = document.createElement('div'); name.className='name'; name.textContent = it.name;
  el.appendChild(caret); el.appendChild(icon); el.appendChild(name);
    el.onclick = ()=>{
      if(it.is_dir){
        // toggle children visibility
        toggleFolder(it.path, el);
      } else {
        appendMessage('user', `Selected ${it.path}`);
      }
    }
    tree.appendChild(el);
  })
}

function renderFsRoot(items){
  const tree = document.getElementById('fs-tree');
  tree.innerHTML = '';
  items.forEach(it=>{
    const el = document.createElement('div');
    el.className = 'fs-item';
    const caret = document.createElement('div'); caret.className='caret'; caret.textContent = it.is_dir ? '▶' : '';
    const icon = document.createElement('div'); icon.className='icon'; icon.textContent = it.is_dir ? '📁' : '📄';
    const name = document.createElement('div'); name.className='name'; name.textContent = it.name;
    el.appendChild(caret); el.appendChild(icon); el.appendChild(name);
    el.dataset.path = it.path;
    if(it.is_dir) el.setAttribute('aria-expanded','false');
    el.onclick = ()=>{ if(it.is_dir) toggleFolder(it.path, el); else appendMessage('user', `Selected ${it.path}`)};
    tree.appendChild(el);
  })
}

function toggleFolder(path, el){
  // Return a promise that resolves when expansion/collapse completes.
  return new Promise((resolve, reject) => {
    // if already expanded, collapse
    const existing = el.nextElementSibling;
    if(existing && existing.classList && existing.classList.contains('fs-children')){
      existing.remove();
      // collapse marker
      el.setAttribute('aria-expanded','false');
      const caretEl = el.querySelector('.caret'); if(caretEl) caretEl.textContent = '▶';
      resolve();
      return;
    }
    // otherwise fetch children
    fetch(`/api/list_dir?path=${encodeURIComponent(path)}`).then(r=>r.json()).then(d=>{
      const wrap = document.createElement('div'); wrap.className='fs-children';
      (d.items||[]).forEach(it=>{
        const row = document.createElement('div'); row.className='fs-item';
        const caret = document.createElement('div'); caret.className='caret'; caret.textContent = it.is_dir ? '▶' : '';
        const icon = document.createElement('div'); icon.className='icon'; icon.textContent = it.is_dir ? '📁' : '📄';
        const name = document.createElement('div'); name.className='name'; name.textContent = it.name;
        row.appendChild(caret); row.appendChild(icon); row.appendChild(name);
        row.dataset.path = it.path;
        if(it.is_dir) row.setAttribute('aria-expanded','false');
        row.onclick = ()=>{ if(it.is_dir) toggleFolder(it.path, row); else appendMessage('user', `Selected ${it.path}`) };
        wrap.appendChild(row);
      })
      el.parentNode.insertBefore(wrap, el.nextSibling);
      // mark expanded state on the parent element and update caret
      el.setAttribute('aria-expanded','true');
      const caretEl = el.querySelector('.caret'); if(caretEl) caretEl.textContent = '▼';
      resolve();
    }).catch(e=>{console.error('list err',e); reject(e)});
  });
}

// Highlight (and expand if needed) a filesystem path in the sidebar
async function ensurePathVisible(path){
  if(!path) return null;
  // normalize
  try{
    // Try direct match first
    let el = document.querySelector(`[data-path="${path}"]`);
    if(el){ highlightPath(el); return el; }

    // Walk up until we find an ancestor element present in DOM
    const parts = path.split('/');
    for(let i = parts.length-1; i>0; i--){
      const ancestor = parts.slice(0,i).join('/') || '/';
      const ancestorEl = document.querySelector(`[data-path="${ancestor}"]`);
      if(ancestorEl){
        // expand the ancestor (if it's a dir)
        try{ await toggleFolder(ancestor, ancestorEl); }catch(e){}
        // after expansion, try to find the target again
        el = document.querySelector(`[data-path="${path}"]`);
        if(el){ highlightPath(el); return el; }
      }
    }
  }catch(e){console.error('ensurePathVisible err', e)}
  return null;
}

function highlightPath(elOrPath){
  // remove previous selection
  document.querySelectorAll('.fs-selected').forEach(n=>n.classList.remove('fs-selected'));
  let el = typeof elOrPath === 'string' ? document.querySelector(`[data-path="${elOrPath}"]`) : elOrPath;
  if(!el) return;
  el.classList.add('fs-selected');
  // scroll into view
  try{ el.scrollIntoView({block:'center', behavior:'smooth'}); }catch(e){}
}

function renderVisualCards(cards){
  // Each invocation creates a separate visual box (dialog) in the chat stream
  const messages = document.getElementById('messages');
  const box = document.createElement('div');
  box.className = 'msg visual-box';
  const header = document.createElement('div');
  header.className = 'meta';
  header.textContent = 'agent — visualization';
  box.appendChild(header);

  const container = document.createElement('div');
  container.style.display = 'grid';
  container.style.gridTemplateColumns = '1fr';
  container.style.gap = '8px';

  cards.forEach(c=>{
    const div = document.createElement('div');
    div.className = 'visual-card';
    div.innerHTML = `<div class='visual-title'>${c.title}</div><div class='visual-sub'>${c.subtitle}</div>`;
    container.appendChild(div);
  })

  box.appendChild(container);
  messages.appendChild(box);
}

// Render a compact list of tool calls (scalable for other tool types)
function renderToolCalls(calls){
  // calls: [{name:'read_file', args:{file_path:'...'}, id:'call_x', type:'tool_call'}, ...]
  const messages = document.getElementById('messages');
  const box = document.createElement('div');
  box.className = 'msg tool-box';
  const header = document.createElement('div'); header.className='meta'; header.textContent = 'tools';
  box.appendChild(header);

  calls.forEach(call=>{
    const row = document.createElement('div'); row.className = 'tool-row';
    const left = document.createElement('div'); left.className = 'tool-left'; left.textContent = call.name;
    const right = document.createElement('div'); right.className = 'tool-right';
    // Pretty-format based on known tool names
    if(call.name === 'read_file' && call.args && call.args.file_path){
      const fp = call.args.file_path;
      const a = document.createElement('a'); a.href='#'; a.textContent = `Opened ${fp.split('/').pop()}`; a.className='tool-file-link';
      a.onclick = (e)=>{ e.preventDefault(); ensurePathVisible(fp); appendMessage('agent', `Opened ${fp}`); };
      right.appendChild(a);
    } else if(call.name === 'list_directory' && call.args && call.args.path){
      const p = call.args.path;
      const span = document.createElement('span'); span.textContent = `Listed ${p}`;
      right.appendChild(span);
    } else if(call.name === 'file_search' && call.args && call.args.query){
      const s = call.args.query;
      const span = document.createElement('span'); span.textContent = `Searched ${s}`;
      right.appendChild(span);
    } else {
      const span = document.createElement('span'); span.textContent = JSON.stringify(call.args || {});
      right.appendChild(span);
    }

    row.appendChild(left); row.appendChild(right);
    box.appendChild(row);
  });

  messages.appendChild(box);
  window.scrollTo(0, document.body.scrollHeight);
}

// chat-tool buttons removed from UI; no handlers necessary

document.getElementById('send').addEventListener('click', ()=>{
  const q = document.getElementById('query').value;
  appendMessage('user', q);
  ws.send(JSON.stringify({type:'query', payload:{text:q}}));
  document.getElementById('query').value = '';
});
