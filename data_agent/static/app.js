const clientId = Math.random().toString(36).slice(2,9);
const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/${clientId}`);

ws.addEventListener('open', ()=>{
  console.log('ws open')
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
    c.textContent = (c.textContent || '') + (msg.payload.content || '');
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
  el.innerHTML = `<div class='meta'>${role}</div><div>${text}</div>`;
  document.getElementById('messages').appendChild(el);
  window.scrollTo(0, document.body.scrollHeight);
}

function renderList(items){
  const tree = document.getElementById('fs-tree');
  tree.innerHTML = '';
  items.forEach(it => {
    const el = document.createElement('div');
    el.className = 'item';
    el.textContent = it.name;
    el.onclick = ()=>{
      // request listing of this folder
      if(it.is_dir){
        ws.send(JSON.stringify({type:'list', payload:{path:it.path}}));
        appendMessage('user', `List ${it.path}`);
      } else {
        appendMessage('user', `Selected ${it.path}`);
      }
    }
    tree.appendChild(el);
  })
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

document.getElementById('btn-list').addEventListener('click', ()=>{
  ws.send(JSON.stringify({type:'list', payload:{path:'./'}}));
  appendMessage('user','Analyze @data folder. How many images are there?');
});

document.getElementById('btn-describe').addEventListener('click', ()=>{
  appendMessage('user','Describe the other dataset types');
  ws.send(JSON.stringify({type:'query', payload:{text:'Describe the other dataset types'}}));
});

document.getElementById('send').addEventListener('click', ()=>{
  const q = document.getElementById('query').value;
  appendMessage('user', q);
  ws.send(JSON.stringify({type:'query', payload:{text:q}}));
  document.getElementById('query').value = '';
});
