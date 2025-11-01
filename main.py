import os
import sys
import asyncio
import subprocess
import zipfile
from aiohttp import web
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ✅ Flush logs immediately
sys.stdout.reconfigure(line_buffering=True)

# ✅ Detect environment
ON_RENDER = os.environ.get("RENDER") == "true"

# ✅ Configure Playwright browser path
if ON_RENDER:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/playwright-browsers"
else:
    local_browser_path = os.path.join(os.getcwd(), "playwright_browsers")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = local_browser_path
os.makedirs(os.environ["PLAYWRIGHT_BROWSERS_PATH"], exist_ok=True)

# ✅ Persistent profile path
USER_DATA_DIR = (
    "/opt/render/project/src/wati_profile" if ON_RENDER else os.path.join(os.getcwd(), "wati_profile")
)

# 🧩 Unzip saved login profile
def unzip_wati_profile():
    zip_path = os.path.join(os.getcwd(), "wati_profile.zip")
    if ON_RENDER and os.path.exists(zip_path):
        if not os.path.exists(USER_DATA_DIR):
            print("📦 Extracting saved login (wati_profile.zip)...", flush=True)
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(os.path.dirname(USER_DATA_DIR))
            print("✅ Login data extracted successfully!", flush=True)
        else:
            print("✅ Existing login folder detected — skipping unzip.", flush=True)

# ✅ Ensure Chromium installed
async def ensure_chromium_installed():
    chromium_path = os.path.join(os.environ["PLAYWRIGHT_BROWSERS_PATH"], "chromium-1117/chrome-linux/chrome")
    if not os.path.exists(chromium_path):
        print("🧩 Installing Chromium...", flush=True)
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "playwright", "install", "chromium",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            print(line.decode().strip(), flush=True)
        await process.wait()
        print("✅ Chromium installed successfully!", flush=True)
    else:
        print("✅ Chromium already installed.", flush=True)

# 🌐 Configuration
WATI_URL = "https://live.wati.io/1037246/teamInbox/"
LOGIN_URL = "https://auth.wati.io/login"
CHECK_INTERVAL = 180  # seconds

# ✅ Manual login helper
async def wait_for_manual_login(page, browser_context):
    print("\n============================")
    print("🟢 MANUAL LOGIN REQUIRED")
    print("============================", flush=True)
    print("➡️ Complete your WATI login in the opened browser.")
    print("➡️ Once 'Team Inbox' is visible, press ENTER to save the session.\n", flush=True)

    await page.goto(LOGIN_URL, wait_until="networkidle")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: input("👉 Press ENTER after login is complete... "))

    try:
        await page.goto(WATI_URL, timeout=60000)
        await page.wait_for_selector("text=Team Inbox", timeout=30000)
        print("✅ Login detected! Saving session...", flush=True)
        await browser_context.storage_state(path=os.path.join(USER_DATA_DIR, "storage.json"))
        print("✅ Session saved successfully as storage.json", flush=True)
        return True
    except PlaywrightTimeout:
        print("🚨 Login was not detected. Please retry.", flush=True)
        return False

# ✅ Automatic login function (corrected)
async def auto_login(page):
    print("🔑 Attempting automatic login...", flush=True)

    js_script = """() => {
        function setReactInputValue(element, value) {
            const nativeSetter = Object.getOwnPropertyDescriptor(element.__proto__, 'value').set;
            nativeSetter.call(element, value);
            element.dispatchEvent(new Event('input', { bubbles: true }));
            element.dispatchEvent(new Event('change', { bubbles: true }));
            element.dispatchEvent(new Event('blur', { bubbles: true }));
        }

        const emailInput = document.querySelector('input[name="email"]');
        if (emailInput) setReactInputValue(emailInput, "Visionsjersey@gmail.com");

        const passwordInput = document.querySelector('input[name="password"]');
        if (passwordInput) setReactInputValue(passwordInput, "27557434@rR");

        const clientIdInput = document.querySelector('input[name="tenantId"]');
        if (clientIdInput) {
            clientIdInput.focus();
            setReactInputValue(clientIdInput, "1037246");
            clientIdInput.blur();
        }

        const checkbox = document.querySelector('.right-box__check-box [role="checkbox"]');
        if (checkbox && checkbox.classList.contains('unchecked')) checkbox.click();

        const loginButton = document.querySelector('form button[type="submit"]');
        if (loginButton) loginButton.click();
    }"""

    try:
        await page.evaluate(js_script)
        await page.wait_for_selector("text=Team Inbox", timeout=30000)
        print("✅ Automatic login successful!", flush=True)
        return True
    except PlaywrightTimeout:
        print("❌ Automatic login failed. Check credentials or page structure.", flush=True)
        return False

# ✅ Main automation loop
async def main_automation(page):
    while True:
        print("🔎 Checking for unread chats...", flush=True)
        try:
            await page.wait_for_selector("div.conversation-item__unread-count", timeout=10000)
        except PlaywrightTimeout:
            print("😴 No unread chats found. Waiting 3 mins...", flush=True)
            await asyncio.sleep(CHECK_INTERVAL)
            await page.reload()
            continue

        unread_elements = await page.query_selector_all("div.conversation-item__unread-count")
        if not unread_elements:
            print("😴 No unread chats. Waiting 3 mins...", flush=True)
            await asyncio.sleep(CHECK_INTERVAL)
            await page.reload()
            continue

        print(f"💬 Found {len(unread_elements)} unread chat(s). Processing...", flush=True)
        processed = 0

        for elem in unread_elements:
            processed += 1
            print(f"👉 Opening unread chat {processed}/{len(unread_elements)}", flush=True)
            try:
                await elem.scroll_into_view_if_needed()
                await elem.click()
                print("🟢 Clicked unread chat successfully", flush=True)
                await asyncio.sleep(2.5)

                await page.click(
                    "#mainTeamInbox div.chat-side-content div span.chat-input__icon-option",
                    timeout=10000,
                )
                await asyncio.sleep(1.5)

                ads_ctwa = await page.query_selector("#flow-nav-68ff67df4f393f0757f108d8")
                if ads_ctwa:
                    await ads_ctwa.click()
                    print("✅ Clicked Ads (CTWA) successfully!", flush=True)
                else:
                    print("⚠️ 'Ads (CTWA)' not found.", flush=True)

                await asyncio.sleep(2)

            except Exception as e:
                print(f"⚠️ Error in chat #{processed}: {e}", flush=True)
                continue

        print("🕒 Waiting before next check...", flush=True)
        await asyncio.sleep(CHECK_INTERVAL)
        await page.reload()

# ✅ Main bot flow
async def run_wati_bot():
    print("🌐 Launching WATI automation with persistent browser...", flush=True)
    headless_mode = True

    async with async_playwright() as p:
        browser_context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=headless_mode,
        )
        page = await browser_context.new_page()
        print("🌍 Navigating to WATI Inbox...", flush=True)
        await page.goto(WATI_URL, timeout=60000)
        await asyncio.sleep(3)

        try:
            await page.wait_for_selector("text=Team Inbox", timeout=60000)
            print("✅ Logged in — session active!", flush=True)
        except PlaywrightTimeout:
            success = await auto_login(page)
            if not success:
                print("ℹ️ Falling back to manual login...")
                success = await wait_for_manual_login(page, browser_context)

        print("🤖 Starting main WATI automation loop...", flush=True)
        await main_automation(page)

# ✅ Web server for health checks
async def start_web_server():
    async def handle(request):
        return web.Response(text="✅ WATI AutoBot running successfully!")

    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    await site.start()
    print("🌍 Web server running!", flush=True)

# 🚀 Entry point
async def main():
    print("🚀 Initializing environment...", flush=True)
    unzip_wati_profile()
    await ensure_chromium_installed()
    print("🚀 Starting bot and web server...", flush=True)
    await asyncio.gather(start_web_server(), run_wati_bot())

if __name__ == "__main__":
    asyncio.run(main())
