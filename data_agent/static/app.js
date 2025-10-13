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
    let partial = document.getElementById('streaming-partial');
    if(!partial){
      partial = document.createElement('div');
      partial.id = 'streaming-partial';
      partial.className = 'msg';
      partial.innerHTML = `<div class='meta'>agent (streaming)</div><div class='stream-content'></div>`;
      document.getElementById('messages').appendChild(partial);
    }
    const c = partial.querySelector('.stream-content');
    const incoming = msg.payload.content || '';
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
  }
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
  // if already expanded, collapse
  const existing = el.nextElementSibling;
  if(existing && existing.classList && existing.classList.contains('fs-children')){
    existing.remove();
    // collapse marker
    el.setAttribute('aria-expanded','false');
    const caretEl = el.querySelector('.caret'); if(caretEl) caretEl.textContent = '▶';
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
  }).catch(e=>console.error('list err',e));
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

// chat-tool buttons removed from UI; no handlers necessary

document.getElementById('send').addEventListener('click', ()=>{
  const q = document.getElementById('query').value;
  appendMessage('user', q);
  ws.send(JSON.stringify({type:'query', payload:{text:q}}));
  document.getElementById('query').value = '';
});
