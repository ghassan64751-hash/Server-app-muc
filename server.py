# pip install flask flask-cors yt-dlp   (and install ffmpeg)
# run: python server.py
import os, glob, shutil, tempfile, urllib.parse
from urllib.parse import urlparse
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app, expose_headers=["X-Title", "X-Ext"])
MAX_SECONDS = 2 * 60 * 60  # reject media longer than 2 hours
OK_HOSTS = ("youtube.com", "youtu.be", "soundcloud.com")


def host_of(url):
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def is_host(host, base):
    return host == base or host.endswith("." + base)


@app.get("/")
def root():
    return "ok"


@app.get("/api/download")
def download():
    url = request.args.get("url", "")
    kind = request.args.get("kind", "audio")
    q = request.args.get("q", "")
    host = host_of(url)

    if is_host(host, "spotify.com"):
        return jsonify(error="سبوتيفاي محمي (DRM) وما ينحمل منه"), 400
    if not any(is_host(host, h) for h in OK_HOSTS):
        return jsonify(error="الموقع غير مدعوم (يوتيوب وساوند كلاود فقط)"), 400
    if is_host(host, "soundcloud.com"):
        kind = "audio"  # no video on soundcloud

    tmp = tempfile.mkdtemp()
    ok = False
    try:
        opts = {
            "outtmpl": os.path.join(tmp, "a.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
        }
        if kind == "video":
            h = int(q) if q in ("360", "480", "720", "1080") else 720
            opts["format"] = (
                f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/"
                f"best[height<={h}][ext=mp4]/best[height<={h}]/best"
            )
            opts["merge_output_format"] = "mp4"
            want, mime, ext = "a.mp4", "video/mp4", "mp4"
        else:
            br = q if q in ("128", "192", "320") else "128"
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": br,
            }]
            want, mime, ext = "a.mp3", "audio/mpeg", "mp3"

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if (info.get("duration") or 0) > MAX_SECONDS:
                return jsonify(error="المقطع طويل جدًا (الحد ساعتين)"), 400
            ydl.download([url])

        path = os.path.join(tmp, want)
        if not os.path.exists(path):
            found = glob.glob(os.path.join(tmp, "a.*"))
            if not found:
                return jsonify(error="ما انتج ملف"), 500
            path = found[0]

        resp = send_file(path, mimetype=mime)
        resp.headers["X-Title"] = urllib.parse.quote(info.get("title") or "تحميل")
        resp.headers["X-Ext"] = ext
        resp.call_on_close(lambda: shutil.rmtree(tmp, ignore_errors=True))
        ok = True
        return resp
    except Exception as e:
        return jsonify(error="فشل التحميل: " + str(e)[:150]), 500
    finally:
        if not ok:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
