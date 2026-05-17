import http.server
import socketserver
import json
import threading
import queue
import socket
import time
import os
import base64
import mimetypes
from urllib.parse import urlparse, parse_qs
from io import BytesIO

PORT = 8080
MAX_HISTORY = 200
MAX_TEXT_LEN = 50000
MAX_FILE_SIZE = 10_000_000
MAX_BODY_BYTES = 15_000_000

clients = []
clients_lock = threading.Lock()
history = []
history_lock = threading.Lock()
files = {}
files_lock = threading.Lock()

INDEX_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chat LAN</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "Segoe UI", sans-serif; margin: 0; display: flex; flex-direction: column; height: 100vh; background: #1e1e2e; color: #cdd6f4; }
  header { padding: 12px 16px; background: #181825; border-bottom: 1px solid #313244; display: flex; justify-content: space-between; align-items: center; }
  header h1 { margin: 0; font-size: 16px; font-weight: 600; }
  #status { font-size: 12px; color: #a6e3a1; }
  #status.off { color: #f38ba8; }
  #messages { flex: 1; overflow-y: auto; padding: 12px 16px; }
  .msg { margin-bottom: 6px; line-height: 1.4; overflow-wrap: anywhere; }
  .msg .name { font-weight: 600; color: #89b4fa; margin-right: 6px; }
  .msg .body { white-space: pre-wrap; }
  .msg .time { color: #6c7086; font-size: 11px; margin-left: 6px; }
  .msg.system { color: #6c7086; font-style: italic; font-size: 13px; }
  .msg .file-link { display: inline-block; margin-top: 4px; padding: 6px 10px; background: #313244; border-radius: 6px; color: #89b4fa; text-decoration: none; font-size: 13px; border: 1px solid #45475a; }
  .msg .file-link:hover { background: #45475a; }
  form { display: flex; padding: 10px 12px; gap: 8px; background: #181825; border-top: 1px solid #313244; align-items: flex-end; }
  input, textarea, button { font-size: 14px; padding: 9px 12px; border-radius: 6px; border: 1px solid #313244; background: #313244; color: #cdd6f4; font-family: inherit; }
  input:focus, textarea:focus { outline: none; border-color: #89b4fa; }
  #name { width: 140px; }
  #text { flex: 1; min-width: 0; resize: none; max-height: 200px; line-height: 1.4; font-family: inherit; }
  button { background: #89b4fa; color: #1e1e2e; cursor: pointer; border-color: #89b4fa; font-weight: 600; }
  button:hover { background: #74c7ec; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  #fileBtn { background: #a6e3a1; border-color: #a6e3a1; padding: 9px 12px; font-size: 14px; min-width: auto; }
  #fileBtn:hover { background: #94e2d5; }
  #fileInput { display: none; }
</style>
</head>
<body>
<header>
  <h1>Chat LAN</h1>
  <span id="status" class="off">connexion...</span>
</header>
<div id="messages"></div>
<form id="form" autocomplete="off">
  <input id="name" placeholder="Nom" maxlength="40" required>
  <textarea id="text" placeholder="Message... (Entree = envoyer, Maj+Entree = nouvelle ligne)" rows="1"></textarea>
  <input type="file" id="fileInput" multiple>
  <button type="button" id="fileBtn">📎</button>
  <button type="submit">Envoyer</button>
</form>
<script>
const messagesEl = document.getElementById('messages');
const form = document.getElementById('form');
const nameInput = document.getElementById('name');
const textInput = document.getElementById('text');
const statusEl = document.getElementById('status');
const fileInput = document.getElementById('fileInput');
const fileBtn = document.getElementById('fileBtn');

nameInput.value = localStorage.getItem('chat-name') || '';
nameInput.addEventListener('input', () => localStorage.setItem('chat-name', nameInput.value));

function addMessage(msg) {
  if (msg.clear) {
    messagesEl.innerHTML = '';
    return;
  }
  
  const el = document.createElement('div');
  el.className = 'msg' + (msg.system ? ' system' : '');
  const time = new Date(msg.time * 1000).toLocaleTimeString();
  
  if (msg.system) {
    const body = document.createElement('span');
    body.className = 'body';
    body.textContent = msg.text;
    el.appendChild(body);
  } else {
    const n = document.createElement('span');
    n.className = 'name';
    n.textContent = msg.name + ':';
    el.appendChild(n);
    
    if (msg.file) {
      const link = document.createElement('a');
      link.className = 'file-link';
      link.href = '/file/' + msg.file.id;
      link.textContent = '📎 ' + msg.file.name + ' (' + formatBytes(msg.file.size) + ')';
      link.target = '_blank';
      el.appendChild(link);
    } else {
      const body = document.createElement('span');
      body.className = 'body';
      body.textContent = msg.text;
      el.appendChild(body);
    }
  }
  
  const t = document.createElement('span');
  t.className = 'time';
  t.textContent = time;
  el.appendChild(t);
  
  const stick = messagesEl.scrollTop + messagesEl.clientHeight >= messagesEl.scrollHeight - 40;
  messagesEl.appendChild(el);
  if (stick) messagesEl.scrollTop = messagesEl.scrollHeight;
}

function formatBytes(bytes) {
  if (bytes < 1024) return bytes + ' o';
  if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' Ko';
  return (bytes/(1024*1024)).toFixed(1) + ' Mo';
}

function connect() {
  const evt = new EventSource('/events');
  evt.onopen = () => { statusEl.textContent = 'en ligne'; statusEl.classList.remove('off'); };
  evt.onerror = () => { statusEl.textContent = 'deconnecte'; statusEl.classList.add('off'); };
  evt.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (Array.isArray(data)) data.forEach(addMessage); else addMessage(data);
  };
}
connect();

function autosize() {
  textInput.style.height = 'auto';
  textInput.style.height = Math.min(textInput.scrollHeight, 200) + 'px';
}
textInput.addEventListener('input', autosize);

textInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.altKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

fileBtn.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', async () => {
  const name = nameInput.value.trim();
  if (!name) { alert('Entrez votre nom'); return; }
  
  const files = Array.from(fileInput.files);
  if (!files.length) return;
  
  for (const file of files) {
    if (file.size > 10*1024*1024) {
      alert('Fichier trop volumineux (max 10 Mo): ' + file.name);
      continue;
    }
    
    const formData = new FormData();
    formData.append('name', name);
    formData.append('file', file);
    
    try {
      await fetch('/upload', { method: 'POST', body: formData });
    } catch (err) {
      statusEl.textContent = 'erreur envoi';
      statusEl.classList.add('off');
    }
  }
  
  fileInput.value = '';
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const name = nameInput.value.trim();
  const text = textInput.value.trim();
  if (!name || !text) return;
  try {
    await fetch('/send', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name, text})
    });
    textInput.value = '';
    autosize();
  } catch (err) {
    statusEl.textContent = 'erreur envoi';
    statusEl.classList.add('off');
  }
  textInput.focus();
});
</script>
</body>
</html>
"""

def broadcast(msg):
    with history_lock:
        history.append(msg)
        if len(history) > MAX_HISTORY:
            del history[:len(history) - MAX_HISTORY]
    with clients_lock:
        dead = []
        for q in clients:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            try:
                clients.remove(q)
            except ValueError:
                pass

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ('/', '/index.html'):
            body = INDEX_HTML.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        
        if path == '/events':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('X-Accel-Buffering', 'no')
            self.end_headers()
            q = queue.Queue(maxsize=100)
            with clients_lock:
                clients.append(q)
            try:
                with history_lock:
                    snapshot = list(history)
                if snapshot:
                    self.wfile.write(f"data: {json.dumps(snapshot)}\n\n".encode('utf-8'))
                    self.wfile.flush()
                while True:
                    try:
                        msg = q.get(timeout=15)
                        self.wfile.write(f"data: {json.dumps(msg)}\n\n".encode('utf-8'))
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            finally:
                with clients_lock:
                    try:
                        clients.remove(q)
                    except ValueError:
                        pass
            return
        
        if path.startswith('/file/'):
            file_id = path[6:]
            with files_lock:
                file_data = files.get(file_id)
            if not file_data:
                self.send_error(404)
                return
            
            self.send_response(200)
            mime_type = file_data.get('mime', 'application/octet-stream')
            self.send_header('Content-Type', mime_type)
            self.send_header('Content-Disposition', f'attachment; filename="{file_data["name"]}"')
            self.send_header('Content-Length', str(len(file_data['data'])))
            self.end_headers()
            self.wfile.write(file_data['data'])
            return
        
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        
        if path == '/send':
            length = int(self.headers.get('Content-Length', '0') or 0)
            if length <= 0 or length > MAX_BODY_BYTES:
                self.send_error(413)
                return
            try:
                data = json.loads(self.rfile.read(length))
                name = str(data.get('name', '')).strip()[:40]
                text = str(data.get('text', '')).strip()[:MAX_TEXT_LEN]
            except Exception:
                self.send_error(400)
                return
            if not name or not text:
                self.send_error(400)
                return
            
            if text == '/clear':
                with history_lock:
                    history.clear()
                broadcast({'clear': True, 'time': time.time()})
            else:
                broadcast({'name': name, 'text': text, 'time': time.time()})
            
            self.send_response(204)
            self.end_headers()
            return
        
        if path == '/upload':
            content_type = self.headers.get('Content-Type', '')
            if not content_type.startswith('multipart/form-data'):
                self.send_error(400)
                return
            
            length = int(self.headers.get('Content-Length', '0') or 0)
            if length <= 0 or length > MAX_BODY_BYTES:
                self.send_error(413)
                return
            
            try:
                boundary = content_type.split('boundary=')[1].encode()
                body = self.rfile.read(length)
                
                parts = body.split(b'--' + boundary)
                name = None
                file_name = None
                file_data = None
                
                for part in parts:
                    if b'Content-Disposition' not in part:
                        continue
                    
                    headers_end = part.find(b'\r\n\r\n')
                    if headers_end == -1:
                        continue
                    
                    headers = part[:headers_end].decode('utf-8', errors='ignore')
                    content = part[headers_end+4:]
                    
                    if content.endswith(b'\r\n'):
                        content = content[:-2]
                    
                    if 'name="name"' in headers:
                        name = content.decode('utf-8', errors='ignore').strip()[:40]
                    elif 'name="file"' in headers and 'filename=' in headers:
                        filename_start = headers.find('filename="') + 10
                        filename_end = headers.find('"', filename_start)
                        file_name = headers[filename_start:filename_end]
                        file_data = content
                
                if not name or not file_name or not file_data:
                    self.send_error(400)
                    return
                
                if len(file_data) > MAX_FILE_SIZE:
                    self.send_error(413)
                    return
                
                file_id = base64.urlsafe_b64encode(os.urandom(12)).decode()
                mime_type, _ = mimetypes.guess_type(file_name)
                
                with files_lock:
                    files[file_id] = {
                        'name': file_name,
                        'data': file_data,
                        'mime': mime_type or 'application/octet-stream',
                        'size': len(file_data),
                        'time': time.time()
                    }
                
                broadcast({
                    'name': name,
                    'file': {
                        'id': file_id,
                        'name': file_name,
                        'size': len(file_data)
                    },
                    'time': time.time()
                })
                
                self.send_response(204)
                self.end_headers()
                return
                
            except Exception as e:
                self.send_error(400)
                return
        
        self.send_error(404)

class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except OSError:
        return '127.0.0.1'
    finally:
        s.close()

if __name__ == '__main__':
    server = ThreadingServer(('0.0.0.0', PORT), Handler)
    ip = get_lan_ip()
    print("Chat LAN demarre")
    print(f"  Local  : http://localhost:{PORT}")
    print(f"  Reseau : http://{ip}:{PORT}")
    print("Ctrl+C pour arreter.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArret.")
        server.shutdown()
