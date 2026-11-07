#!/usr/bin/env python3
"""
MOVA Custom Voice Pack add-on server.

Self-serve web UI (HA ingress) to set, per trigger, either typed text (Piper
TTS) or an uploaded audio file, then build a Dreame/MOVA voice pack and install
it to the robot over the LAN.

The proprietary base pack is NOT shipped with this add-on; it is uploaded once
through the UI and kept in /data (never leaves the HA box).
"""
import os, io, json, time, hashlib, shutil, subprocess, tarfile, tempfile, traceback
import urllib.request
from aiohttp import web

# ---- paths / config -------------------------------------------------------
DATA      = "/data"
BASE_DIR  = os.path.join(DATA, "base")          # extracted base pack (<id>.ogg + tts.json)
UPLOADS   = os.path.join(DATA, "uploads")        # per-slot uploaded audio
CONFIG    = os.path.join(DATA, "config.json")
WWW       = "/homeassistant/www/voicepack"       # -> served at {HA}/local/voicepack/
PIPER_MODEL = "/opt/piper/en_US-lessac-medium.onnx"
LANG_ID   = "custom_mova"
HERE      = os.path.dirname(os.path.abspath(__file__))
INDEX     = os.path.join(HERE, "static", "index.html")

VACUUM_ENTITY = os.environ.get("VACUUM_ENTITY", "vacuum.p10_pro_ultra")
HA_BASE_URL   = os.environ.get("HA_BASE_URL", "http://192.168.1.136").rstrip("/")
SUP_TOKEN     = os.environ.get("SUPERVISOR_TOKEN", "")
SUP_CORE      = "http://supervisor/core/api"

# trigger -> sound IDs it overwrites (from the decoded official EN pack)
EVENTS = {
    "dock":    [202, 203, 139, 188],   # returning to dock / task ended
    "start":   [0, 190, 126, 105, 195],# ok, start to clean
    "finish":  [143, 113],             # cleaning completed
    "playnow": [246, 45, 40],          # locate / "I'm here"
}
TRIGGER_ORDER  = ["dock", "start", "finish", "playnow"]
TRIGGER_LABELS = {
    "dock":    "Returning to dock",
    "start":   "Start cleaning",
    "finish":  "Finished cleaning",
    "playnow": "Play now (locate button)",
}

for d in (DATA, UPLOADS):
    os.makedirs(d, exist_ok=True)


# ---- small helpers --------------------------------------------------------
def load_config():
    try:
        with open(CONFIG) as f:
            return json.load(f)
    except Exception:
        return {"slots": {}, "last_build": None, "installed": None}

def save_config(c):
    with open(CONFIG, "w") as f:
        json.dump(c, f, indent=2)

def base_ready():
    return os.path.isdir(BASE_DIR) and any(
        n.endswith(".ogg") for n in os.listdir(BASE_DIR))

def _run(cmd, **kw):
    p = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, **kw)
    if p.returncode != 0:
        raise RuntimeError(" ".join(cmd[:2]) + ": " +
                           p.stderr.decode("utf-8", "replace")[:300])

def tts_to_wav(text, out_wav):
    p = subprocess.run(["piper", "-m", PIPER_MODEL, "-f", out_wav],
                       input=text.encode("utf-8"),
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if p.returncode != 0 or not os.path.exists(out_wav):
        raise RuntimeError("piper: " + p.stderr.decode("utf-8", "replace")[:300])

def to_ogg(src, out_ogg):
    _run(["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1",
          "-c:a", "libvorbis", "-q:a", "4", out_ogg])

def slot_to_ogg(slot, spec, workdir):
    """Produce one ogg for a slot from its spec {type, text|file}."""
    out = os.path.join(workdir, slot + ".ogg")
    if spec.get("type") == "audio":
        src = spec.get("file")
        if not src or not os.path.exists(src):
            raise RuntimeError(f"{slot}: uploaded audio missing")
        to_ogg(src, out)
    else:
        text = (spec.get("text") or "").strip()
        if not text:
            raise RuntimeError(f"{slot}: empty text")
        wav = os.path.join(workdir, slot + ".wav")
        tts_to_wav(text, wav)
        to_ogg(wav, out)
    return out

def ha_service(domain, service, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{SUP_CORE}/services/{domain}/{service}",
        data=body, method="POST",
        headers={"Authorization": "Bearer " + SUP_TOKEN,
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode("utf-8", "replace")


# ---- handlers -------------------------------------------------------------
async def index(_req):
    return web.FileResponse(INDEX)

async def status(_req):
    c = load_config()
    out = {
        "base_ready": base_ready(),
        "vacuum_entity": VACUUM_ENTITY,
        "ha_base_url": HA_BASE_URL,
        "triggers": [{"key": k, "label": TRIGGER_LABELS[k],
                      "slot": c["slots"].get(k)} for k in TRIGGER_ORDER],
        "last_build": c.get("last_build"),
        "installed": c.get("installed"),
    }
    return web.json_response(out)

async def upload_base(req):
    reader = await req.multipart()
    field = await reader.next()
    if field is None:
        return web.json_response({"error": "no file"}, status=400)
    tmp = BASE_DIR + ".tar.gz"
    with open(tmp, "wb") as f:
        while True:
            chunk = await field.read_chunk()
            if not chunk:
                break
            f.write(chunk)
    # extract (flat) to BASE_DIR
    if os.path.isdir(BASE_DIR):
        shutil.rmtree(BASE_DIR)
    os.makedirs(BASE_DIR, exist_ok=True)
    try:
        with tarfile.open(tmp, "r:gz") as tar:
            for m in tar.getmembers():
                m.name = os.path.basename(m.name)   # force flat, strip paths
                if m.name and (m.name.endswith(".ogg") or m.name == "tts.json"):
                    tar.extract(m, BASE_DIR)
    finally:
        try: os.remove(tmp)
        except OSError: pass
    n = len([x for x in os.listdir(BASE_DIR) if x.endswith(".ogg")])
    if n == 0:
        return web.json_response({"error": "no .ogg found in archive"}, status=400)
    return web.json_response({"ok": True, "clips": n})

async def set_slot(req):
    """Set one trigger: form fields key, type, text  OR  key + file upload."""
    c = load_config()
    reader = await req.multipart()
    fields, key = {}, None
    audio_path = None
    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "file" and part.filename:
            key = fields.get("key") or key
            os.makedirs(UPLOADS, exist_ok=True)
            dest = os.path.join(UPLOADS, (fields.get("key") or "slot") + "_up")
            with open(dest, "wb") as f:
                while True:
                    chunk = await part.read_chunk()
                    if not chunk:
                        break
                    f.write(chunk)
            audio_path = dest
        else:
            fields[part.name] = (await part.read()).decode("utf-8", "replace")
    key = fields.get("key")
    if key not in EVENTS:
        return web.json_response({"error": "bad trigger"}, status=400)
    if audio_path or fields.get("type") == "audio":
        c["slots"][key] = {"type": "audio", "file": audio_path or
                           c["slots"].get(key, {}).get("file")}
    else:
        c["slots"][key] = {"type": "text", "text": fields.get("text", "")}
    save_config(c)
    return web.json_response({"ok": True, "slot": c["slots"][key]})

async def clear_slot(req):
    c = load_config()
    key = (await req.json()).get("key")
    c["slots"].pop(key, None)
    save_config(c)
    return web.json_response({"ok": True})

async def preview(req):
    """Return an ogg for a single text/audio spec (not saved)."""
    data = await req.json() if req.content_type == "application/json" else {}
    work = tempfile.mkdtemp(prefix="prev_")
    try:
        spec = {"type": data.get("type", "text"),
                "text": data.get("text", ""),
                "file": data.get("file")}
        ogg = slot_to_ogg("preview", spec, work)
        body = open(ogg, "rb").read()
        return web.Response(body=body, content_type="audio/ogg")
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)
    finally:
        shutil.rmtree(work, ignore_errors=True)

async def build(_req):
    if not base_ready():
        return web.json_response({"error": "base pack not loaded"}, status=400)
    c = load_config()
    work = tempfile.mkdtemp(prefix="vp_")
    try:
        pack = os.path.join(work, "pack")
        shutil.copytree(BASE_DIR, pack)
        tmp = os.path.join(work, "tmp"); os.makedirs(tmp)
        changed = {}
        for slot, spec in c["slots"].items():
            if slot not in EVENTS:
                continue
            ogg = slot_to_ogg(slot, spec, tmp)
            for sid in EVENTS[slot]:
                shutil.copyfile(ogg, os.path.join(pack, f"{sid}.ogg"))
            changed[slot] = EVENTS[slot]
        # flat tar.gz
        out_tmp = os.path.join(work, "pack.tar.gz")
        with tarfile.open(out_tmp, "w:gz") as tar:
            for fn in sorted(os.listdir(pack)):
                tar.add(os.path.join(pack, fn), arcname=fn)
        data = open(out_tmp, "rb").read()
        md5 = hashlib.md5(data).hexdigest()
        size = len(data)
        # publish to HA www (robot fetches it over LAN); bust cache via md5 name
        os.makedirs(WWW, exist_ok=True)
        for old in os.listdir(WWW):
            if old.startswith("pack-") and old.endswith(".tar.gz"):
                try: os.remove(os.path.join(WWW, old))
                except OSError: pass
        fname = f"pack-{md5[:8]}.tar.gz"
        with open(os.path.join(WWW, fname), "wb") as f:
            f.write(data)
        url = f"{HA_BASE_URL}/local/voicepack/{fname}"
        c["last_build"] = {"url": url, "md5": md5, "size": size,
                           "changed": changed, "at": int(time.time())}
        save_config(c)
        return web.json_response({"ok": True, **c["last_build"]})
    except Exception as e:
        traceback.print_exc()
        return web.json_response({"error": str(e)}, status=500)
    finally:
        shutil.rmtree(work, ignore_errors=True)

async def install(_req):
    c = load_config()
    b = c.get("last_build")
    if not b:
        return web.json_response({"error": "build first"}, status=400)
    try:
        st, resp = ha_service("dreame_vacuum", "vacuum_install_voice_pack", {
            "entity_id": VACUUM_ENTITY,
            "lang_id": LANG_ID,
            "url": b["url"],
            "md5": b["md5"],
            "size": b["size"],
        })
        c["installed"] = {"lang_id": LANG_ID, "md5": b["md5"],
                          "at": int(time.time())}
        save_config(c)
        return web.json_response({"ok": True, "status": st})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def playnow(_req):
    try:
        st, _ = ha_service("vacuum", "locate", {"entity_id": VACUUM_ENTITY})
        return web.json_response({"ok": True, "status": st})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


def make_app():
    app = web.Application(client_max_size=64 * 1024 * 1024)
    app.add_routes([
        web.get("/", index),
        web.get("/api/status", status),
        web.post("/api/base", upload_base),
        web.post("/api/slot", set_slot),
        web.post("/api/slot/clear", clear_slot),
        web.post("/api/preview", preview),
        web.post("/api/build", build),
        web.post("/api/install", install),
        web.post("/api/playnow", playnow),
    ])
    return app


if __name__ == "__main__":
    web.run_app(make_app(), host="0.0.0.0", port=8099)
