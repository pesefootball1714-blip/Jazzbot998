import os, re, time, threading, queue, subprocess, requests, zipfile, telebot, shutil
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

# Default parent folder in JazzDrive
DEFAULT_JAZZ_FOLDER = "Uploads"

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
    if os.path.exists(f):
        os.remove(f)

def take_screenshot(page, caption="📸"):
    try:
        page.screenshot(path="s.png")
        with open("s.png", "rb") as f:
            bot.send_photo(CHAT_ID, f, caption=caption)
        os.remove("s.png")
    except:
        pass

# ═══════════════════════════════════════
# 🔑 Login
# ═══════════════════════════════════════
def do_login(page, context):
    msg("🔐 *LOGIN REQUIRED*\n\n📱 Jazz number bhejein\nFormat: `03XXXXXXXXX`")
    user_context["state"] = "WAITING_FOR_NUMBER"

    for _ in range(300):
        if user_context["state"] == "NUMBER_RECEIVED":
            break
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
        if user_context["state"] == "OTP_RECEIVED":
            break
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
        except:
            pass

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
# 📁 JazzDrive Folder Helpers
# ═══════════════════════════════════════
def folder_exists(page, folder_name):
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except:
        pass

    selectors = [
        f"text={folder_name}",
        f"[title='{folder_name}']",
        f"div:has-text('{folder_name}')",
        f"span:has-text('{folder_name}')"
    ]

    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=2000):
                return True
        except:
            pass
    return False

def open_folder(page, folder_name):
    selectors = [
        f"text={folder_name}",
        f"[title='{folder_name}']",
        f"div:has-text('{folder_name}')",
        f"span:has-text('{folder_name}')"
    ]

    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=3000):
                el.click()
                time.sleep(2)
                return True
        except:
            pass
    return False

def create_folder(page, folder_name):
    # multiple possible selectors because JazzDrive UI change ho sakta hai
    attempts = [
        lambda: page.click("button:has-text('New')", timeout=4000),
        lambda: page.click("button:has-text('Create')", timeout=4000),
        lambda: page.click("button:has-text('Add')", timeout=4000),
        lambda: page.click("text=New", timeout=4000),
    ]

    clicked = False
    for a in attempts:
        try:
            a()
            clicked = True
            time.sleep(1)
            break
        except:
            pass

    if not clicked:
        return False

    # folder option
    folder_clicked = False
    folder_attempts = [
        lambda: page.click("text=Folder", timeout=4000),
        lambda: page.click("button:has-text('Folder')", timeout=4000),
        lambda: page.click("div:has-text('Folder')", timeout=4000),
    ]

    for a in folder_attempts:
        try:
            a()
            folder_clicked = True
            time.sleep(1)
            break
        except:
            pass

    if not folder_clicked:
        return False

    # input folder name
    inputs = [
        "input[type='text']",
        "input",
        "input[placeholder*='name']",
        "input[placeholder*='Name']"
    ]

    filled = False
    for inp in inputs:
        try:
            el = page.locator(inp).first
            if el.is_visible(timeout=3000):
                el.fill(folder_name)
                filled = True
                time.sleep(1)
                break
        except:
            pass

    if not filled:
        return False

    # create confirm
    confirms = [
        lambda: page.click("button:has-text('Create')", timeout=4000),
        lambda: page.click("button:has-text('OK')", timeout=4000),
        lambda: page.click("button:has-text('Done')", timeout=4000),
        lambda: page.click("text=Create", timeout=4000),
    ]

    for c in confirms:
        try:
            c()
            time.sleep(2)
            return True
        except:
            pass

    return False

def ensure_folder(page, folder_name):
    try:
        if folder_exists(page, folder_name):
            if open_folder(page, folder_name):
                msg(f"📂 Folder *{folder_name}* open ho gaya!")
                return True

        msg(f"📁 Folder *{folder_name}* nahi mila, create kar raha hoon...")
        if create_folder(page, folder_name):
            time.sleep(2)
            if open_folder(page, folder_name):
                msg(f"✅ Folder *{folder_name}* create + open ho gaya!")
                return True

        # final try
        if open_folder(page, folder_name):
            msg(f"📂 Folder *{folder_name}* open ho gaya!")
            return True

        msg("⚠️ Folder create/open fail. Root me upload hoga.")
        return False
    except Exception as e:
        msg(f"⚠️ Folder error:\n`{str(e)[:120]}`")
        return False

# ═══════════════════════════════════════
# 🤖 Bot Commands
# ═══════════════════════════════════════
@bot.message_handler(commands=["start"])
def welcome(m):
    msg(
        "🤖 *JAZZ DRIVE BOT*\n\n"
        "📎 Direct link → Upload\n"
        "📦 ZIP/RAR link → Extract → Sab episodes upload\n"
        "📁 Har upload folder ke andar jayega\n\n"
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
            bot.reply_to(
                m,
                f"📦 *ZIP/RAR link add!*\n"
                f"Bot download → extract → sab episodes upload karega!\n"
                f"Queue: *{task_queue.qsize()}*",
                parse_mode="Markdown"
            )
        else:
            task_queue.put({"link": text, "type": "direct"})
            bot.reply_to(
                m,
                f"✅ *Direct link add!*\n"
                f"Queue: *{task_queue.qsize()}*",
                parse_mode="Markdown"
            )

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
        if not out_path.endswith('.mp4'):
            out_path = out_path.rsplit('.', 1)[0] + '.mp4'
        try:
            print("M3U8 detected - using ffmpeg")
            subprocess.run([
                "ffmpeg", "-y",
                "-user_agent", WEB_UA,
                "-i", url,
                "-c", "copy",
                "-bsf:a", "aac_adtstoasc",
                out_path
            ], capture_output=True, timeout=600)
            if file_ok(out_path):
                return True
        except Exception as e:
            print(f"ffmpeg error: {e}")
        return False

    # Method 1: aria2c
    try:
        out_dir = os.path.dirname(out_path)
        out_name = os.path.basename(out_path)
        subprocess.run([
            "aria2c", "-x", "16", "-s", "16", "-k", "1M",
            "--timeout=60", "--retry-wait=3", "--max-tries=5",
            f"--user-agent={WEB_UA}",
            "--allow-overwrite=true",
            "-d", out_dir, "-o", out_name, url
        ], capture_output=True, timeout=300)
        if file_ok(out_path):
            return True
    except:
        pass

    # Method 2: curl
    try:
        subprocess.run([
            "curl", "-L", "--retry", "3", "--max-time", "300",
            "-H", f"User-Agent: {WEB_UA}", "-o", out_path, url
        ], timeout=300)
        if file_ok(out_path):
            return True
    except:
        pass

    # Method 3: requests
    try:
        with requests.get(url, headers={"User-Agent": WEB_UA}, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        if file_ok(out_path):
            return True
    except:
        pass

    return False

# ═══════════════════════════════════════
# 📦 ZIP Process
# ═══════════════════════════════════════
def process_zip(url):
    zip_path = "/tmp/series_download.zip"
    extract_dir = "/tmp/series_extracted"

    clean(zip_path)
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)
    os.makedirs(extract_dir, exist_ok=True)

    # ZIP file name se folder name banao
    zip_name = url.split("/")[-1].split("?")[0] or "Series"
    series_folder = safe_filename(os.path.splitext(zip_name)[0]) or "Series"

    msg(f"⬇️ *ZIP download ho raha hai...*")
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
            # fallback
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
        f"\n\n☁️ *JazzDrive upload shuru...*\n📂 Folder: *{series_folder}*"
    )

    # Upload one by one into same series folder
    for i, video_path in enumerate(video_files, 1):
        fname = os.path.basename(video_path)
        fsize = os.path.getsize(video_path)/(1024*1024)
        msg(f"📤 *Episode {i}/{len(video_files)}*\n📁 {fname}\n📦 {fsize:.1f} MB")
        jazz_drive_upload(video_path, folder_name=series_folder)
        msg(f"✅ *Episode {i}/{len(video_files)} uploaded!*")

    shutil.rmtree(extract_dir, ignore_errors=True)

    msg(
        f"🎉 *SERIES UPLOAD COMPLETE!*\n\n"
        f"✅ *{len(video_files)} episodes* JazzDrive pe!\n"
        f"📂 Folder: *{series_folder}*\n"
        f"Agla link bhejein 🚀"
    )

# ═══════════════════════════════════════
# 📎 Direct Link Process
# ═══════════════════════════════════════
def process_direct(url):
    out_name = url.split("/")[-1].split("?")[0] or "downloaded_file.mp4"
    out_name = safe_filename(out_name)
    if "." not in out_name:
        out_name += ".mp4"

    if ".m3u8" in out_name.lower():
        out_name = out_name.lower().replace(".m3u8", ".mp4")
        out_name = re.sub(r'[.]av[0-9]+', '', out_name)

    out_path = f"/tmp/{out_name}"
    clean(out_path)

    msg(f"⬇️ *Downloading...*\n📁 {out_name}")
    success = download_file(url, out_path)

    if not success:
        msg("❌ Download fail!\nFresh link bhejein.")
        return

    sz = os.path.getsize(out_path)/(1024*1024)
    msg(f"✅ Downloaded! *{sz:.1f} MB*\n\n☁️ JazzDrive upload ho raha hai...\n📂 Folder: *{DEFAULT_JAZZ_FOLDER}*")

    jazz_drive_upload(out_path, folder_name=DEFAULT_JAZZ_FOLDER)
    clean(out_path)

# ═══════════════════════════════════════
# ☁️ JazzDrive Upload
# ═══════════════════════════════════════
def jazz_drive_upload(filename, folder_name=DEFAULT_JAZZ_FOLDER):
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

            # 🔐 Login check
            if page.locator("#msisdn").is_visible():
                msg("⚠️ Session expire!\nLogin karo...")
                ok = do_login(page, ctx)
                if not ok:
                    msg("❌ Login fail.")
                    return
                page.goto("https://cloud.jazzdrive.com.pk/", wait_until="networkidle", timeout=90000)
                time.sleep(3)

            ctx.storage_state(path="state.json")

            # 📁 Ensure folder
            ensure_folder(page, folder_name)

            abs_path = os.path.abspath(filename)

            # Upload button
            upload_opened = False
            try:
                page.evaluate("""
                    document.querySelectorAll('button').forEach(b => {
                        const t = (b.innerText || b.textContent || '').toLowerCase();
                        if (t.includes('upload')) b.click();
                    });
                """)
                time.sleep(2)
                upload_opened = True
            except:
                pass

            # File chooser / input
            try:
                dialog = page.locator("div[role='dialog']")
                if dialog.is_visible(timeout=3000):
                    try:
                        with page.expect_file_chooser(timeout=5000) as fc_info:
                            dialog.locator("text=/upload/i").first.click()
                        fc_info.value.set_files(abs_path)
                    except:
                        page.locator("input[type=file]").set_input_files(abs_path)
                else:
                    page.locator("input[type=file]").set_input_files(abs_path)
            except:
                try:
                    page.locator("input[type=file]").set_input_files(abs_path)
                except Exception as e:
                    msg(f"❌ File chooser fail:\n`{str(e)[:150]}`")
                    take_screenshot(page, "❌ Upload chooser fail")
                    return

            time.sleep(3)

            try:
