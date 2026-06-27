import os, sys, json, signal, subprocess, threading, time, io
from functools import wraps
from flask import Flask, request, Response, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

CONFIG_PATH = os.path.expanduser("~/.cctv_config.json")

if not os.path.exists(CONFIG_PATH):
    print("Config not found. Run install.sh first.")
    sys.exit(1)

with open(CONFIG_PATH) as f:
    config = json.load(f)

STREAM_PID = None
TORCH_ON = False

def cmd(args, capture=False, timeout=10):
    try:
        r = subprocess.run(args, capture_output=capture, text=True, timeout=timeout)
        return r.stdout.strip() if capture else True
    except:
        return "" if capture else False

def start_stream():
    global STREAM_PID
    if STREAM_PID:
        return False
    proc = subprocess.Popen([
        "ffmpeg", "-f", "android_camera", "-input_device", "0",
        "-i", "0", "-c:v", "libx264", "-preset", "ultrafast",
        "-f", "rtsp", f"rtsp://0.0.0.0:{config['stream_port']}/live"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    STREAM_PID = proc.pid
    return True

def stop_stream():
    global STREAM_PID
    if not STREAM_PID:
        return False
    subprocess.run(["pkill", "-f", "ffmpeg.*android_camera"], capture_output=True)
    STREAM_PID = None
    return True

def get_ip():
    raw = cmd(["hostname", "-I"], capture=True)
    return raw.split()[0] if raw else "?"

app = Flask(__name__)

def check_auth(pw):
    return pw == config["web_password"]

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        a = request.authorization
        if not a or not check_auth(a.password):
            return Response("Auth required", 401, {"WWW-Authenticate": 'Basic realm="Home CCTV"'})
        return f(*args, **kwargs)
    return decorated

DASH = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Home CCTV</title><style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#111;color:#eee;padding:16px;max-width:800px;margin:auto}
h1{font-size:1.3em;margin-bottom:12px}
.feed{width:100%;aspect-ratio:16/9;background:#000;border-radius:10px;overflow:hidden;margin-bottom:12px;display:flex;align-items:center;justify-content:center}
.feed img{width:100%;height:100%;object-fit:contain}
.feed .off{color:#555;font-size:.9em}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}
.btn{background:#1a1a1a;border:none;color:#eee;padding:14px;border-radius:8px;font-size:1em;cursor:pointer;transition:.15s}
.btn:active{transform:scale(.95)}
.btn.on{background:#00cc66;color:#000}
.info{background:#1a1a1a;padding:12px;border-radius:8px;font-size:.85em;line-height:1.7}
.info span{color:#666}
</style></head><body>
<h1>📹 Home CCTV</h1>
<div class="feed"><img id="feed" src="/feed" alt="feed"><div id="placeholder" class="off" style="display:none">Camera in use by RTSP stream<br><small>Use VLC: rtsp://IP:8554/live</small></div></div>
<div class="grid">
<button class="btn" onclick="doAct('photo')">📸 Photo</button>
<button class="btn" id="tb" onclick="doAct('torch')">🔦 Torch</button>
<button class="btn" id="sb" onclick="doAct('stream')">▶️ Stream</button>
<button class="btn" onclick="doAct('lock')">🔒 Lock</button>
</div>
<div class="info" id="status">Loading...</div>
<script>
let feed=document.getElementById('feed'),ph=document.getElementById('placeholder');
async function doAct(c){
 let r=await fetch('/'+c,{method:'POST'});
 if(c=='photo'&&r.ok){
  let b=await r.blob();let u=URL.createObjectURL(b);feed.src=u;setTimeout(()=>{feed.src='/feed';URL.revokeObjectURL(u)},3000)
 }
}
async function refresh(){
 let r=await fetch('/status'),s=await r.json();
 document.getElementById('status').innerHTML='⚡ '+s.battery+'% | 📡 '+s.proximity+'cm | 💻 Stream: '+(s.stream?'running':'off');
 let sb=document.getElementById('sb');sb.textContent=s.stream?'⏹️ Stream':'▶️ Stream';sb.className='btn'+(s.stream?' on':'');
 let tb=document.getElementById('tb');tb.textContent=s.torch?'🔦 Torch ON':'🔦 Torch';tb.className='btn'+(s.torch?' on':'');
 if(s.stream){feed.style.display='none';ph.style.display='block'}else{feed.style.display='block';ph.style.display='none'}
}
setInterval(refresh,3000);refresh();
</script></body></html>"""

@app.route("/")
@require_auth
def dash():
    return DASH

@app.route("/photo", methods=["POST"])
@require_auth
def photo():
    cmd(["termux-camera-photo", "/tmp/cctv.jpg"], timeout=3)
    try:
        return Response(open("/tmp/cctv.jpg", "rb").read(), mimetype="image/jpeg")
    except:
        return "", 500

@app.route("/torch", methods=["POST"])
@require_auth
def torch():
    global TORCH_ON
    TORCH_ON = not TORCH_ON
    cmd(["termux-torch", "on" if TORCH_ON else "off"])
    return jsonify({"torch": TORCH_ON})

@app.route("/stream", methods=["POST"])
@require_auth
def stream():
    if STREAM_PID:
        stop_stream()
        return jsonify({"stream": False})
    else:
        ok = start_stream()
        return jsonify({"stream": ok})

@app.route("/lock", methods=["POST"])
@require_auth
def lock():
    cmd(["input", "keyevent", "26"])
    return "", 204

@app.route("/feed")
@require_auth
def feed():
    def gen():
        while True:
            if STREAM_PID:
                time.sleep(1)
                continue
            try:
                cmd(["termux-camera-photo", "/tmp/feed.jpg"], timeout=2)
                with open("/tmp/feed.jpg", "rb") as f:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + f.read() + b"\r\n"
            except:
                time.sleep(1)
            time.sleep(0.3)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/status")
@require_auth
def status():
    global TORCH_ON
    bat = "?"
    pro = "?"
    try:
        bj = json.loads(cmd(["termux-battery-status"], capture=True))
        bat = bj.get("percentage", "?")
    except:
        pass
    try:
        sj = json.loads(cmd(["termux-sensor", "-s", "Proximity sensor", "-n", "1"], capture=True))
        if sj and isinstance(sj, list) and "values" in sj[0]:
            pro = round(sj[0]["values"][0], 1)
    except:
        pass
    return jsonify({"battery": bat, "proximity": pro, "stream": STREAM_PID is not None, "torch": TORCH_ON})

app_bot = Application.builder().token(config["token"]).build()

async def auth(update):
    return update.effective_user.id in config["allowed_users"]

async def h_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return await update.message.reply_text("Unauthorized")
    ip = get_ip()
    await update.message.reply_text(
        f"📹 Home CCTV Ready\n\n"
        f"Commands:\n"
        f"/photo   - Take a photo\n"
        f"/torch   - Toggle flashlight\n"
        f"/stream  - Toggle RTSP stream\n"
        f"/lock    - Lock screen\n"
        f"/battery - Battery status\n"
        f"/sensors - Read sensors\n"
        f"/reboot  - Reboot phone\n"
        f"/speak   - Text-to-speech\n"
        f"/ping    - Health check\n\n"
        f"🌐 Web: http://{ip}:{config['web_port']}"
    )

async def h_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return
    await update.message.reply_text("📸 Capturing...")
    cmd(["termux-camera-photo", "/tmp/tg.jpg"], timeout=3)
    try:
        await update.message.reply_photo(open("/tmp/tg.jpg", "rb"))
    except:
        await update.message.reply_text("❌ Camera failed")

async def h_torch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return
    global TORCH_ON
    TORCH_ON = not TORCH_ON
    cmd(["termux-torch", "on" if TORCH_ON else "off"])
    await update.message.reply_text(f"🔦 {'ON' if TORCH_ON else 'OFF'}")

async def h_stream(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return
    if STREAM_PID:
        stop_stream()
        await update.message.reply_text("⏹️ Stream stopped")
    else:
        ok = start_stream()
        if ok:
            ip = get_ip()
            await update.message.reply_text(f"▶️ Stream: rtsp://{ip}:{config['stream_port']}/live")
        else:
            await update.message.reply_text("❌ Failed to start stream")

async def h_lock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return
    cmd(["input", "keyevent", "26"])
    await update.message.reply_text("🔒 Screen locked")

async def h_battery(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return
    out = cmd(["termux-battery-status"], capture=True)
    try:
        d = json.loads(out)
        await update.message.reply_text(
            f"🔋 Battery\n"
            f"Level: {d.get('percentage')}%\n"
            f"Status: {d.get('status')}\n"
            f"Temp: {d.get('temperature')}°C\n"
            f"Health: {d.get('health')}"
        )
    except:
        await update.message.reply_text("❌ Could not read battery")

async def h_sensors(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return
    out = cmd(["termux-sensor", "-n", "1"], capture=True)
    try:
        data = json.loads(out)
        lines = ["📡 Sensors"]
        for s in data[:5]:
            name = s.get("type", "?")
            vals = s.get("values", [])
            lines.append(f"  {name}: {', '.join(str(round(v,2)) for v in vals)}")
        await update.message.reply_text("\n".join(lines)[:4000])
    except:
        await update.message.reply_text("❌ Could not read sensors")

async def h_reboot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return
    await update.message.reply_text("🔄 Rebooting...")
    subprocess.run(["reboot"])

async def h_speak(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return
    text = " ".join(ctx.args) if ctx.args else "Hello"
    cmd(["termux-tts-speak", text])
    await update.message.reply_text(f"🔊 Said: {text[:200]}")

async def h_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await auth(update): return
    await update.message.reply_text("pong")

for c, h in [("start", h_start), ("photo", h_photo), ("torch", h_torch),
             ("stream", h_stream), ("lock", h_lock), ("battery", h_battery),
             ("sensors", h_sensors), ("reboot", h_reboot), ("speak", h_speak),
             ("ping", h_ping)]:
    app_bot.add_handler(CommandHandler(c, h))

if __name__ == "__main__":
    t = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=config["web_port"], debug=False), daemon=True)
    t.start()
    print(f"✅ Bot + Web running on port {config['web_port']}")
    app_bot.run_polling()
