import os, re, time, threading, queue, subprocess, requests, zipfile, telebot
from telebot import types
from playwright.sync_api import sync_playwright

TOKEN = "8617995670:AAHGqu84ueii64ptU6OO6KXtgUNY3WfZgxI"
CHAT_ID = 5562046180
bot = telebot.TeleBot(TOKEN)

task_queue = queue.Queue()
is_working = False
worker_lock = threading.Lock()
user_context = {"state": "IDLE", "number": None, "otp": None, "pending_link": None}

BROWSER_ARGS = ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--single-process"]
WEB_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

VIDEO_EXTS = [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts"]
ZIP_EXTS = [".zip", ".rar", ".7z", ".tar", ".gz"]

def is_zip_url(link):
    return any(link.lower().endswith(ext) or ext in link.lower() for ext in ZIP_EXTS)

def is_video_file(filename):
    return any(filename.lower().endswith(ext) for ext in VIDEO_EXTS)

def safe_filename(t):
    return re.sub(r'[\\/*?:"<>|]', '', t).strip().replace(' ', '_')[:80]

def msg(text, **kw):
    bot.send_message(CHAT_ID, text, parse_mode="Markdown", **kw)

def file_ok(f, min_mb=1):
    return os.path.exists(f) and os.path.getsize(f)/(1024*1024) >= min_mb

def clean(f):
    if os.path.exists(f): os.remove(f)

def take_screenshot(page, caption="📸"):
    try:
        page.screenshot(path="s.png")
        with open("s.png", "rb") as f: bot.send_photo(CHAT_ID, f, caption=caption)
        os.remove("s.png")
    except: pass

# ═══════════════════════════════════════
# 🔑 Login
# ═══════════════════════════════════════
def do_login(page, context):
    msg("🔐 *LOGIN REQUIRED*\n\n📱 Jazz number bhejein\nFormat: `03XXXXXXXXX`")
    user_context["state"] = "WAITING_FOR_NUMBER"
    for _ in range(300):
        if user_context["state"] == "NUMBER_RECEIVED": break
        time.sleep(1)
    else:
        msg("⏰ Timeout! Task cancel.")
        return False

    page.locator("#msisdn").fill(user_context["number"])
    time.sleep(1)
    page.locator("#signinbtn").first.click()
    time.sleep(3)
    take_screenshot(page, "📱 Number submit")
    msg("✅ Number accept!\n\n🔢 *OTP bhejein:*")
    user_context["state"] = "WAITING_FOR_OTP"
    for _ in range(300):
        if user_context["state"] == "OTP_RECEIVED": break
        time.sleep(1)
    else:
        msg("⏰ Timeout! Task cancel.")
        return False

    for i, digit in enumerate(user_context["otp"].strip()[:6], 1):
        try:
            f = page.locator(f"//input[@aria-label='Digit {i}']")
            if f.is_visible():
                f.fill(digit)
                time.sleep(0.2)
        except: pass

    time.sleep(5)
    take_screenshot(page, "🔢 OTP submit")
    context.storage_state(path="state.json")
    msg("✅ *LOGIN SUCCESSFUL!*\n\n🍪 Session save!\nLink bhejein 🚀")
    user_context["state"] = "IDLE"
    return True

def check_login_status():
    msg("🔍 Jazz Drive login check...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 720},
            storage_state="state.json" if os.path.exists("state.json") else None
        )
        page = ctx.new_page()
        try:
            page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
            time.sleep(3)
            if page.locator("#msisdn").is_visible():
                msg("⚠️ Session expire!\nLogin karte hain...")
                do_login(page, ctx)
            else:
                msg("✅ *LOGIN VALID!*\n\n🚀 Link bhejein!")
        except Exception as e:
            msg(f"❌ Error:\n`{str(e)[:150]}`")
        finally:
            browser.close()

# ═══════════════════════════════════════
# 🤖 Bot Commands
# ═══════════════════════════════════════
@bot.message_handler(commands=["start"])
def welcome(m):
    msg(
        "🤖 *JAZZ DRIVE BOT*\n\n"
        "📎 Direct link → Upload\n"
        "📦 ZIP/RAR link → Extract → Sab episodes upload\n\n"
        "─────────────────────\n"
        "/checklogin — Login status\n"
        "/status — Queue status\n"
        "/cmd — Server command",
        reply_markup=types.ReplyKeyboardRemove()
    )

@bot.message_handler(commands=["checklogin"])
def cmd_check(m):
    threading.Thread(target=check_login_status, daemon=True).start()

@bot.message_handler(commands=["status"])
def cmd_status(m):
    icon = "🟢" if is_working else "🔴"
    cookie = "✅" if os.path.exists("state.json") else "❌"
    msg(f"📊 *STATUS*\n\n{icon} {'Working' if is_working else 'Idle'}\n📋 Queue: {task_queue.qsize()}\n🍪 Session: {cookie}")

@bot.message_handler(commands=["cmd"])
def cmd_shell(m):
    try:
        c = m.text.replace("/cmd ", "", 1).strip()
        out = subprocess.check_output(c, shell=True, stderr=subprocess.STDOUT).decode()
        bot.reply_to(m, f"```\n{out[:4000]}\n```", parse_mode="Markdown")
    except subprocess.CalledProcessError as e:
        bot.reply_to(m, f"❌\n```\n{e.output.decode()[:3000]}\n```", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(m, f"❌ `{e}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def handle(m):
    global is_working
    text = (m.text or "").strip()

    if user_context["state"] == "WAITING_FOR_NUMBER":
        user_context["number"] = text
        user_context["state"] = "NUMBER_RECEIVED"
        bot.reply_to(m, "✅ Number receive hua...")
        return

    if user_context["state"] == "WAITING_FOR_OTP":
        user_context["otp"] = text
        user_context["state"] = "OTP_RECEIVED"
        bot.reply_to(m, "✅ OTP receive hua...")
        return

    if text.startswith("http"):
        if is_zip_url(text):
            task_queue.put({"link": text, "type": "zip"})
            bot.reply_to(m,
                f"📦 *ZIP/RAR link add!*\n"
                f"Bot download → extract → sab episodes upload karega!\n"
                f"Queue: *{task_queue.qsize()}*",
                parse_mode="Markdown")
        else:
            task_queue.put({"link": text, "type": "direct"})
            bot.reply_to(m,
                f"✅ *Direct link add!*\n"
                f"Queue: *{task_queue.qsize()}*",
                parse_mode="Markdown")

        with worker_lock:
            if not is_working:
                is_working = True
                threading.Thread(target=worker_loop, daemon=True).start()
    else:
        bot.reply_to(m, "ℹ️ Link bhejein ya /checklogin")

# ═══════════════════════════════════════
# 🔄 Worker
# ═══════════════════════════════════════
def worker_loop():
    global is_working
    try:
        while not task_queue.empty():
            item = task_queue.get()
            short = item["link"][:55] + "..." if len(item["link"]) > 55 else item["link"]
            msg(f"🎬 *PROCESSING...*\n\n🔗 `{short}`")
            try:
                if item["type"] == "zip":
                    process_zip(item["link"])
                else:
                    process_direct(item["link"])
            except Exception as e:
                msg(f"❌ Error:\n`{str(e)[:150]}`")
            finally:
                task_queue.task_done()
        msg("✅ *QUEUE COMPLETE!*\n\nAgla link bhejein 😊")
    except Exception as e:
        msg(f"⚠️ Worker crash:\n`{str(e)[:150]}`")
    finally:
        with worker_lock:
            is_working = False

# ═══════════════════════════════════════
# ⬇️ Download Helper
# ═══════════════════════════════════════
def is_m3u8(url):
    return '.m3u8' in url.lower() or 'm3u8' in url.lower()

def download_file(url, out_path):
    # M3U8/HLS stream - ffmpeg use karo
    if is_m3u8(url):
        # mp4 extension force karo
        if not out_path.endswith('.mp4'):
            out_path = out_path.rsplit('.', 1)[0] + '.mp4'
        try:
            print(f"M3U8 detected - using ffmpeg")
            result = subprocess.run([
                "ffmpeg", "-y",
                "-user_agent", WEB_UA,
                "-i", url,
                "-c", "copy",
                "-bsf:a", "aac_adtstoasc",
                out_path
            ], capture_output=True, timeout=600)
            if file_ok(out_path): return True
        except Exception as e:
            print(f"ffmpeg error: {e}")
        return False

    # Method 1: aria2c
    try:
        out_dir = os.path.dirname(out_path)
        out_name = os.path.basename(out_path)
        result = subprocess.run([
            "aria2c", "-x", "16", "-s", "16", "-k", "1M",
            "--timeout=60", "--retry-wait=3", "--max-tries=5",
            f"--user-agent={WEB_UA}",
            "--allow-overwrite=true",
            "-d", out_dir, "-o", out_name, url
        ], capture_output=True, timeout=300)
        if file_ok(out_path): return True
    except: pass

    # Method 2: curl
    try:
        subprocess.run([
            "curl", "-L", "--retry", "3", "--max-time", "300",
            "-H", f"User-Agent: {WEB_UA}", "-o", out_path, url
        ], timeout=300)
        if file_ok(out_path): return True
    except: pass

    # Method 3: requests
    try:
        with requests.get(url, headers={"User-Agent": WEB_UA}, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk: f.write(chunk)
        if file_ok(out_path): return True
    except: pass

    return False

# ═══════════════════════════════════════
# 📦 ZIP Process
# ═══════════════════════════════════════
def process_zip(url):
    zip_path = "/tmp/series_download.zip"
    extract_dir = "/tmp/series_extracted"

    # Cleanup
    clean(zip_path)
    if os.path.exists(extract_dir):
        import shutil
        shutil.rmtree(extract_dir)
    os.makedirs(extract_dir, exist_ok=True)

    # Download ZIP
    sz_hint = ""
    msg(f"⬇️ *ZIP download ho raha hai...*\n{sz_hint}")
    success = download_file(url, zip_path)

    if not success or not file_ok(zip_path):
        msg("❌ ZIP download fail!\nLink check karo.")
        return

    zip_size = os.path.getsize(zip_path)/(1024*1024)
    msg(f"✅ ZIP downloaded! *{zip_size:.1f} MB*\n\n📂 Extract ho raha hai...")

    # Extract
    try:
        if url.lower().endswith(".zip") or zipfile.is_zipfile(zip_path):
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
        else:
            # rar/7z ke liye
            subprocess.run(["unzip", "-o", zip_path, "-d", extract_dir], timeout=120)
    except Exception as e:
        msg(f"❌ Extract fail:\n`{str(e)[:100]}`")
        return

    clean(zip_path)

    # Video files dhundo
    video_files = []
    for root, dirs, files in os.walk(extract_dir):
        for f in sorted(files):
            if is_video_file(f):
                video_files.append(os.path.join(root, f))

    if not video_files:
        msg("❌ ZIP mein koi video file nahi mili!")
        return

    msg(
        f"✅ *Extract complete!*\n\n"
        f"📁 *{len(video_files)} episodes* mile:\n" +
        "\n".join([f"• {os.path.basename(v)}" for v in video_files[:10]]) +
        ("\n..." if len(video_files) > 10 else "") +
        f"\n\n☁️ *JazzDrive upload shuru...*"
    )

    # Upload one by one
    for i, video_path in enumerate(video_files, 1):
        fname = os.path.basename(video_path)
        fsize = os.path.getsize(video_path)/(1024*1024)
        msg(f"📤 *Episode {i}/{len(video_files)}*\n📁 {fname}\n📦 {fsize:.1f} MB")
        jazz_drive_upload(video_path)
        msg(f"✅ *Episode {i}/{len(video_files)} uploaded!*")

    # Cleanup
    import shutil
    shutil.rmtree(extract_dir, ignore_errors=True)

    msg(
        f"🎉 *SERIES UPLOAD COMPLETE!*\n\n"
        f"✅ *{len(video_files)} episodes* JazzDrive pe!\n"
        f"Agla link bhejein 🚀"
    )

# ═══════════════════════════════════════
# 📎 Direct Link Process
# ═══════════════════════════════════════
def process_direct(url):
    out_name = url.split("/")[-1].split("?")[0] or "downloaded_file.mp4"
    out_name = safe_filename(out_name)
    if "." not in out_name: out_name += ".mp4"
    # M3U8 ko mp4 mein convert karenge
    if ".m3u8" in out_name.lower():
        out_name = out_name.lower().replace(".m3u8", ".mp4")
        out_name = re.sub(r'[.]av[0-9]+', '', out_name)  # .av1 etc remove
    out_path = f"/tmp/{out_name}"

    clean(out_path)
    msg(f"⬇️ *Downloading...*\n📁 {out_name}")

    success = download_file(url, out_path)

    if not success:
        msg("❌ Download fail!\nFresh link bhejein.")
        return

    sz = os.path.getsize(out_path)/(1024*1024)
    msg(f"✅ Downloaded! *{sz:.1f} MB*\n\n☁️ JazzDrive upload ho raha hai...")
    jazz_drive_upload(out_path)
    clean(out_path)

# ═══════════════════════════════════════
# ☁️ JazzDrive Upload
# ═══════════════════════════════════════
def jazz_drive_upload(filename):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 720},
            storage_state="state.json" if os.path.exists("state.json") else None
        )
        page = ctx.new_page()
        try:
            page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
            time.sleep(3)

            if page.locator("#msisdn").is_visible():
                msg("⚠️ Session expire!\nLogin karo...")
                ok = do_login(page, ctx)
                if not ok:
                    msg("❌ Login fail.")
                    return
                page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
                time.sleep(3)

            ctx.storage_state(path="state.json")
            abs_path = os.path.abspath(filename)

            # Upload button
            try:
                page.evaluate("document.querySelectorAll('header button').forEach(b => { if(b.innerHTML.includes('svg') || b.innerHTML.includes('upload')) b.click(); })")
                time.sleep(2)
            except: pass

            # File chooser
            try:
                dialog = page.locator("div[role='dialog']")
                if dialog.is_visible():
                    with page.expect_file_chooser() as fc_info:
                        dialog.locator("text=/upload/i").first.click()
                    fc_info.value.set_files(abs_path)
                else:
                    page.locator("input[type=file]").set_input_files(abs_path)
            except:
                page.locator("input[type=file]").set_input_files(abs_path)

            time.sleep(3)
            try:
                yes_btn = page.get_by_text("Yes", exact=True)
                if yes_btn.is_visible(): yes_btn.click()
            except: pass

            sz = os.path.getsize(filename)/(1024*1024)
            wait_sec = max(60, int(sz * 4))
            msg(f"⏳ Uploading {os.path.basename(filename)}... (~{wait_sec}s)")
            
            # Upload complete detect karo - max wait_sec tak
            elapsed = 0
            interval = 30
            upload_done = False
            
            while elapsed < wait_sec:
                time.sleep(interval)
                elapsed += interval
                
                # "Uploads completed" text check karo
                try:
                    completed = page.locator("text=Uploads completed").is_visible()
                    if completed:
                        msg(f"✅ Upload detected complete at {elapsed}s!")
                        upload_done = True
                        time.sleep(3)
                        break
                except: pass
                
                # Har 60 second mein screenshot
                if elapsed % 60 == 0:
                    take_screenshot(page, f"📸 Upload progress | {elapsed}s / {wait_sec}s")
            
            if not upload_done:
                take_screenshot(page, f"📸 Final state | {elapsed}s")
            
            ctx.storage_state(path="state.json")

        except Exception as e:
            msg(f"❌ Upload error:\n`{str(e)[:200]}`")
        finally:
            browser.close()

if __name__ == "__main__":
    msg("🤖 *BOT ONLINE!*\n\n✅ Ready!\n\n📎 Direct link\n📦 ZIP/RAR link → Auto extract + upload")
    bot.infinity_polling()
