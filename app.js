const fileInput = document.getElementById('fileInput');
const editor = document.getElementById('editor');
const applyCorrectionsBtn = document.getElementById('applyCorrections');
const exportBtn = document.getElementById('exportSRT');
const saveBtn = document.getElementById('savePatched');
const loadHistoryBtn = document.getElementById('loadHistory');
const clearHistoryBtn = document.getElementById('clearHistory');
const speechToggle = document.getElementById('speechToggle');
const speechStatus = document.getElementById('speechStatus');

const STORAGE_KEY = 'srt-fix-history-v1';
let subs = [];
let recognition;
let activeId = null;

function parseSrt(text){
  const parts = text.split(/\r?\n\r?\n/);
  return parts.map(block=>{
    const lines = block.split(/\r?\n/);
    if(lines.length<3) return null;
    const idx = lines[0].trim();
    const time = lines[1].trim();
    const content = lines.slice(2).join('\n');
    return {id:idx,time,content};
  }).filter(Boolean);
}

function formatSrt(entries){
  return entries.map(e=>`${e.id}\n${e.time}\n${e.content}`).join('\n\n');
}

function render(){
  editor.innerHTML = '';
  subs.forEach((sub, i)=>{
    const block = document.createElement('article');
    block.className = 'entry' + (sub.modified ? ' modified' : '');

    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.innerHTML = `<span>#${sub.id}</span><span>${sub.time}</span>`;

    const textarea = document.createElement('textarea');
    textarea.value = sub.content;
    textarea.dataset.id = sub.id;
    textarea.addEventListener('input', (e)=>{
      sub.content = e.target.value;
      sub.modified = true;
      block.classList.add('modified');
      updateHistory(sub.id, sub.content);
    });
    textarea.addEventListener('focus', ()=>{ activeId=sub.id; });

    block.appendChild(meta);
    block.appendChild(textarea);
    editor.appendChild(block);
  });
}

function updateHistory(id, content){
  const history = JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}');
  history[id] = content;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
}

function applyHistory(){
  const history = JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}');
  let changed=0;
  subs.forEach(sub=>{
    if(history[sub.id] && history[sub.id]!==sub.content){
      sub.content = history[sub.id];
      sub.modified=true;
      changed++;
    }
  });
  if(changed) render();
  alert(`Aplikováno ${changed} historických úprav.`);
}

function saveHistory(){
  const history = {};
  subs.forEach(sub=>{ if(sub.modified) history[sub.id]=sub.content; });
  localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
  alert('Uloženo do lokální historie.');
}

function loadHistory(){
  const history = JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}');
  const entries = Object.keys(history).length;
  alert(`Nalezeno ${entries} záznamů v historii.`);
}

function clearHistory(){
  localStorage.removeItem(STORAGE_KEY);
  alert('Historie smazána.');
}

fileInput.addEventListener('change', ev=>{
  const file = ev.target.files[0];
  if(!file) return;
  const rdr = new FileReader();
  rdr.onload = ()=>{
    subs = parseSrt(rdr.result);
    render();
  };
  rdr.readAsText(file,'utf-8');
});

applyCorrectionsBtn.addEventListener('click', applyHistory);
exportBtn.addEventListener('click', ()=>{
  const blob = new Blob([formatSrt(subs)], {type:'text/plain;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href=url; link.download='patched.srt'; link.click();
  URL.revokeObjectURL(url);
});
saveBtn.addEventListener('click', saveHistory);
loadHistoryBtn.addEventListener('click', loadHistory);
clearHistoryBtn.addEventListener('click', clearHistory);

if('webkitSpeechRecognition' in window || 'SpeechRecognition' in window){
  const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new Speech();
  recognition.lang='cs-CZ';
  recognition.interimResults=false;
  recognition.maxAlternatives=1;

  recognition.addEventListener('result', e=>{
    if(!activeId) return;
    const text=e.results[0][0].transcript;
    const sub = subs.find(s=>s.id===activeId);
    if(sub){ sub.content = sub.content ? `${sub.content} ${text}` : text; sub.modified=true; updateHistory(sub.id,sub.content); render(); }
  });
  recognition.addEventListener('end', ()=>{ speechStatus.textContent='vypnuto'; });
  recognition.addEventListener('error', err => { speechStatus.textContent='chyba: '+err.error; });

  speechToggle.addEventListener('click', ()=>{
    if(speechStatus.textContent==='nahrávání...'){
      recognition.stop();
      speechStatus.textContent='vypnuto';
    } else {
      recognition.start();
      speechStatus.textContent='nahrávání...';
    }
  });
} else {
  speechToggle.disabled=true;
  speechStatus.textContent='váš prohlížeč nepodporuje diktát.';
}

if('serviceWorker' in navigator){
  navigator.serviceWorker.register('service-worker.js').catch(()=>{});
}
