#!/usr/bin/env python3
"""Erpena room device: Raspberry u sali. Kad se u Erpeni pokrene snimanje sastanka u toj sali,
otvara mikrofon, kodira (Opus / FLAC / PCM po podesavanju u Erpeni) i salje zvuk u delovima, sifrovano (HTTPS).
Veza je uvek izlazna ka Erpeni, ne otvaraju se portovi. Ako veza pukne, delovi cekaju na disku i salju se kasnije.

Komande:
  agent.py pair --url https://firma.erpena.rs --code KOD8ZNAK [--name "Pi sala"] [--alsa default]
  agent.py run
  agent.py mics        # spisak mikrofona
  agent.py test        # 5 s probnog snimka u /tmp/erpena-test.wav, za proveru mikrofona
"""
import argparse, json, os, signal, subprocess, sys, time, shutil, glob

try:
    import requests
except ImportError:
    sys.exit("Nedostaje python3-requests: sudo apt install -y python3-requests")

VERSION = "1.0"
CONF = os.environ.get("ERPENA_ROOM_CONF", "/etc/erpena-room/config.json")
SPOOL = os.environ.get("ERPENA_ROOM_SPOOL", "/var/lib/erpena-room/spool")
MAX_SPOOL_MB = 500
EXT = {"opus": ("ogg", "audio/ogg"), "flac": ("flac", "audio/flac"), "pcm": ("wav", "audio/wav")}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def load():
    with open(CONF) as f:
        return json.load(f)


def save(c):
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    with open(CONF, "w") as f:
        json.dump(c, f)
    os.chmod(CONF, 0o600)


def need_https(url):
    if not url.lower().startswith("https://"):
        sys.exit("Adresa mora biti https:// (zvuk se salje samo sifrovano).")


def cmd_pair(a):
    need_https(a.url)
    r = requests.post(a.url.rstrip("/") + "/api/sala/uparivanje", json={"code": a.code, "name": a.name or ""}, timeout=20)
    if r.status_code != 200:
        sys.exit("Uparivanje nije uspelo: " + (r.json().get("error", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text[:200]))
    save({"url": a.url.rstrip("/"), "token": r.json()["token"], "alsa": a.alsa})
    print("Upareno. Pokreni: sudo systemctl enable --now erpena-room")


def ffmpeg_cmd(c, st, sess_dir, seq_start):
    s = st["settings"]
    ext, _ = EXT[s["codec"]]
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "alsa", "-i", c.get("alsa", "default"), "-ac", "1", "-ar", str(s["rate"])]
    if s.get("denoise"):
        cmd += ["-af", "highpass=f=100,afftdn=nf=-25"]
    if s["codec"] == "opus":
        cmd += ["-c:a", "libopus", "-b:a", "%dk" % s["bitrate"], "-application", "voip"]
    elif s["codec"] == "flac":
        cmd += ["-c:a", "flac"]
    else:
        cmd += ["-c:a", "pcm_s16le"]
    cmd += ["-f", "segment", "-segment_format", ext if ext != "ogg" else "ogg", "-segment_time", str(st["chunk_sec"]), "-reset_timestamps", "1",
            "-segment_start_number", str(seq_start), os.path.join(sess_dir, "seg_%06d." + ext)]
    return cmd


def next_seq(meeting):
    p = os.path.join(SPOOL, "seq_%d.txt" % meeting)
    n = 0
    if os.path.exists(p):
        n = int(open(p).read().strip() or 0)
    return n


def set_seq(meeting, n):
    with open(os.path.join(SPOOL, "seq_%d.txt" % meeting), "w") as f:
        f.write(str(n))


class Agent:
    def __init__(self):
        self.c = load()
        need_https(self.c["url"])
        self.h = {"Authorization": "Bearer " + self.c["token"]}
        self.proc = None
        self.sess = None
        os.makedirs(SPOOL, exist_ok=True)

    def state(self):
        r = requests.get(self.c["url"] + "/api/sala/stanje", headers=self.h, params={"v": VERSION}, timeout=15)
        if r.status_code == 401:
            log("Token ne vazi (uredjaj je uklonjen u Erpeni). Upari ponovo.")
            return None
        return r.json() if r.status_code == 200 else None

    def start(self, st):
        mid = st["meeting_id"]
        seq = next_seq(mid)
        d = os.path.join(SPOOL, "m%d_%d" % (mid, int(time.time())))
        os.makedirs(d)
        meta = {"meeting_id": mid, "base": st["offset"], "seq_start": seq, "chunk": st["chunk_sec"], "codec": st["settings"]["codec"]}
        with open(os.path.join(d, "session.json"), "w") as f:
            json.dump(meta, f)
        self.proc = subprocess.Popen(ffmpeg_cmd(self.c, st, d, seq), stderr=subprocess.PIPE)
        self.sess = {"dir": d, "mid": mid}
        log("Snimam sastanak", mid, st["settings"])

    def stop(self):
        if self.proc:
            self.proc.send_signal(signal.SIGINT)
            try:
                self.proc.wait(8)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            log("Snimanje zaustavljeno")
        self.proc = None
        self.sess = None

    def upload_all(self):
        for d in sorted(glob.glob(os.path.join(SPOOL, "m*_*"))):
            mp = os.path.join(d, "session.json")
            if not os.path.exists(mp):
                shutil.rmtree(d, ignore_errors=True)
                continue
            meta = json.load(open(mp))
            ext, mime = EXT[meta["codec"]]
            files = sorted(glob.glob(os.path.join(d, "seg_*." + ext)))
            live = self.sess and self.sess["dir"] == d and self.proc and self.proc.poll() is None
            if live and files:
                files = files[:-1]          # poslednji deo ffmpeg jos pise
            for f in files:
                k = int(os.path.basename(f)[4:10])
                if os.path.getsize(f) < 1500:
                    os.remove(f)
                    continue
                off = int(meta["base"] + (k - meta["seq_start"]) * meta["chunk"])
                try:
                    with open(f, "rb") as fh:
                        r = requests.post(self.c["url"] + "/api/sala/zvuk", headers=self.h, files={"audio": (os.path.basename(f), fh, mime)},
                                          data={"meeting_id": meta["meeting_id"], "seq": k, "offset": off}, timeout=120)
                except requests.RequestException as e:
                    log("Slanje nije uspelo, ostaje na disku:", e)
                    return
                if r.status_code == 200 or r.status_code == 409:
                    os.remove(f)
                    set_seq(meta["meeting_id"], max(next_seq(meta["meeting_id"]), k + 1))
                elif r.status_code == 401:
                    log("Token ne vazi.")
                    return
                else:
                    log("Greska servera", r.status_code, "ponavljam kasnije")
                    return
            if not live and not glob.glob(os.path.join(d, "seg_*")):
                shutil.rmtree(d, ignore_errors=True)
        self.trim()

    def trim(self):
        tot = 0
        for root, _, fs in os.walk(SPOOL):
            tot += sum(os.path.getsize(os.path.join(root, x)) for x in fs)
        if tot > MAX_SPOOL_MB * 1024 * 1024:
            for d in sorted(glob.glob(os.path.join(SPOOL, "m*_*")))[:1]:
                if not (self.sess and self.sess["dir"] == d):
                    log("Disk pun, brisem najstariji neposlat snimak")
                    shutil.rmtree(d, ignore_errors=True)

    def loop(self):
        log("Erpena uredjaj u sali", VERSION, "->", self.c["url"])
        while True:
            try:
                st = self.state()
            except requests.RequestException as e:
                st = "offline"
                log("Nema veze sa Erpenom:", e)
            if st is None:
                time.sleep(30)
                continue
            if st != "offline":
                want = st.get("record")
                if self.proc and self.proc.poll() is not None:
                    log("ffmpeg se zaustavio, proveri mikrofon:", (self.proc.stderr.read() or b"").decode()[-300:])
                    self.proc = None
                    self.sess = None
                if want and (not self.proc or self.sess["mid"] != st["meeting_id"]):
                    self.stop()
                    self.start(st)
                elif not want and self.proc:
                    self.stop()
            self.upload_all()
            time.sleep(3)


def cmd_mics(_):
    subprocess.call(["arecord", "-l"])
    print("\nUpisi u /etc/erpena-room/config.json polje alsa, npr. plughw:1,0")


def cmd_test(_):
    c = load()
    subprocess.call(["ffmpeg", "-y", "-loglevel", "error", "-f", "alsa", "-i", c.get("alsa", "default"), "-t", "5", "-ac", "1", "-ar", "16000", "/tmp/erpena-test.wav"])
    print("Snimljeno u /tmp/erpena-test.wav, preslusaj ga (aplay /tmp/erpena-test.wav).")


def main():
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    q = s.add_parser("pair")
    q.add_argument("--url", required=True)
    q.add_argument("--code", required=True)
    q.add_argument("--name", default="")
    q.add_argument("--alsa", default="default")
    s.add_parser("run")
    s.add_parser("mics")
    s.add_parser("test")
    a = p.parse_args()
    if a.cmd == "pair":
        cmd_pair(a)
    elif a.cmd == "mics":
        cmd_mics(a)
    elif a.cmd == "test":
        cmd_test(a)
    else:
        Agent().loop()


if __name__ == "__main__":
    main()
