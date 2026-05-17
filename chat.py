import http.server
import socketserver
import json
import threading
import queue
import socket
import time
from urllib.parse import urlparse

PORT = 8080
MAX_HISTORY = 200
MAX_TEXT_LEN = 50000
MAX_BODY_BYTES = 1_000_000

clients = []
clients_lock = threading.Lock()
history = []
history_lock = threading.Lock()

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
  form { display: flex; padding: 10px 12px; gap: 8px; background: #181825; border-top: 1px solid #313244; align-items: flex-end; }
  input, textarea, button { font-size: 14px; padding: 9px 12px; border-radius: 6px; border: 1px solid #313244; background: #313244; color: #cdd6f4; font-family: inherit; }
  input:focus, textarea:focus { outline: none; border-color: #89b4fa; }
  #name { width: 140px; }
  #text { flex: 1; min-width: 0; resize: none; max-height: 200px; line-height: 1.4; font-family: inherit; }
  button { background: #89b4fa; color: #1e1e2e; cursor: pointer; border-color: #89b4fa; font-weight: 600; }
  button:hover { background: #74c7ec; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
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
  <textarea id="text" placeholder="Message... (Entree = envoyer, Maj+Entree = nouvelle ligne)" rows="1" required></textarea>
  <button type="submit">Envoyer</button>
</form>
<script>
const messagesEl = document.getElementById('messages');
const form = document.getElementById('form');
const nameInput = document.getElementById('name');
const textInput = document.getElementById('text');
const statusEl = document.getElementById('status');

nameInput.value = localStorage.getItem('chat-name') || '';
nameInput.addEventListener('input', () => localStorage.setItem('chat-name', nameInput.value));

function addMessage(msg) {
  const el = document.createElement('div');
  el.className = 'msg' + (msg.system ? ' system' : '');
  const time = new Date(msg.time * 1000).toLocaleTimeString();
  const body = document.createElement('span'); body.className = 'body'; body.textContent = msg.text;
  if (msg.system) {
    el.appendChild(body);
  } else {
    const n = document.createElement('span'); n.className = 'name'; n.textContent = msg.name + ':';
    el.appendChild(n);
    el.appendChild(body);
  }
  const t = document.createElement('span'); t.className = 'time'; t.textContent = time;
  el.appendChild(t);
  const stick = messagesEl.scrollTop + messagesEl.clientHeight >= messagesEl.scrollHeight - 40;
  messagesEl.appendChild(el);
  if (stick) messagesEl.scrollTop = messagesEl.scrollHeight;
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
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path != '/send':
            self.send_error(404); return
        length = int(self.headers.get('Content-Length', '0') or 0)
        if length <= 0 or length > MAX_BODY_BYTES:
            self.send_error(413); return
        try:
            data = json.loads(self.rfile.read(length))
            name = str(data.get('name', '')).strip()[:40]
            text = str(data.get('text', '')).strip()[:MAX_TEXT_LEN]
        except Exception:
            self.send_error(400); return
        if not name or not text:
            self.send_error(400); return
        broadcast({'name': name, 'text': text, 'time': time.time()})
        self.send_response(204); self.end_headers()

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
