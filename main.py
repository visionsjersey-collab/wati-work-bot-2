import os
import sys
import asyncio
import subprocess
import zipfile
import shutil # ADDED for robust file operations
from aiohttp import web
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ✅ Flush logs immediately
sys.stdout.reconfigure(line_buffering=True)

# ✅ Detect environment
ON_RENDER = os.environ.get("RENDER") == "true"

# ✅ Configure Playwright browser path
if ON_RENDER:
    # Use /tmp for ephemeral storage on Render for browsers
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/playwright-browsers"
else:
    local_browser_path = os.path.join(os.getcwd(), "playwright_browsers")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = local_browser_path
os.makedirs(os.environ["PLAYWRIGHT_BROWSERS_PATH"], exist_ok=True)

# ✅ Persistent profile path
# Use the persistent disk path on Render for the user data directory
USER_DATA_DIR = (
    "/opt/render/project/src/wati_profile" if ON_RENDER else os.path.join(os.getcwd(), "wati_profile")
)
os.makedirs(USER_DATA_DIR, exist_ok=True)


# 🌐 Configuration and Environment Variables
WATI_URL = "https://live.wati.io/1037246/teamInbox/"
LOGIN_URL = "https://auth.wati.io/login"
CHECK_INTERVAL = 180  # seconds

# **SECURITY FIX: Fetch credentials from environment variables**
WATI_EMAIL = os.environ.get("WATI_EMAIL")
WATI_PASSWORD = os.environ.get("WATI_PASSWORD")
WATI_CLIENT_ID = os.environ.get("WATI_CLIENT_ID")


# 🧩 Unzip saved login profile (UPDATED FOR ROBUST EXTRACTION)
def unzip_wati_profile():
    zip_path = os.path.join(os.getcwd(), "wati_profile.zip")
    if ON_RENDER and os.path.exists(zip_path):
        storage_path = os.path.join(USER_DATA_DIR, "storage.json")
        
        if not os.path.exists(storage_path):
            print("📦 Extracting saved login (wati_profile.zip)...", flush=True)
            try:
                # 1. Clear the target directory completely before extracting
                if os.path.exists(USER_DATA_DIR):
                    shutil.rmtree(USER_DATA_DIR)
                    os.makedirs(USER_DATA_DIR)
                    print("🗑️ Cleaned up old profile directory.", flush=True)
                else:
                    os.makedirs(USER_DATA_DIR)

                # 2. Extract contents directly into the USER_DATA_DIR
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    # Iterate members to avoid creating an extra top-level folder
                    for member in zip_ref.namelist():
                        # Only extract files, not directories
                        if not member.endswith('/'):
                            filename = os.path.basename(member)
                            source = zip_ref.open(member)
                            target = open(os.path.join(USER_DATA_DIR, filename), "wb")
                            with source, target:
                                shutil.copyfileobj(source, target)
                            
                print("✅ Login data extracted successfully!", flush=True)
            except Exception as e:
                print(f"🚨 Error extracting profile zip: {e}", flush=True)
        else:
            print("✅ Existing login storage file detected — skipping unzip.", flush=True)
            
# ✅ Ensure Chromium installed
async def ensure_chromium_installed():
    browser_path = os.environ["PLAYWRIGHT_BROWSERS_PATH"]
    chromium_path = os.path.join(browser_path, "chromium-1117/chrome-linux/chrome")
    
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
        
        if process.returncode == 0:
            print("✅ Chromium installed successfully!", flush=True)
        else:
            print(f"🚨 Chromium installation failed with return code {process.returncode}", flush=True)
            
    else:
        print("✅ Chromium already installed.", flush=True)

# ✅ Manual login helper 
async def wait_for_manual_login(page, browser_context):
    if ON_RENDER:
        return False
        
    print("\n============================")
    print("🟢 MANUAL LOGIN REQUIRED")
    print("============================", flush=True)
    print("➡️ Complete your WATI login in the opened browser.")
    print("➡️ Once 'Team Inbox' is visible, press ENTER to save the session.\n", flush=True)

    await page.goto(LOGIN_URL, wait_until="networkidle")
    
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, lambda: input("👉 Press ENTER after login is complete... "))
    except EOFError:
        print("🚨 EOFError encountered. Manual login requires an interactive terminal.", flush=True)
        return False

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


# ✅ Automatic login function (FINAL ROBUST VERSION)
async def auto_login(page):
    print("🔑 Attempting automatic login...", flush=True)

    if not all([WATI_EMAIL, WATI_PASSWORD, WATI_CLIENT_ID]):
        print("🚨 Automatic login failed: Missing WATI_EMAIL, WATI_PASSWORD, or WATI_CLIENT_ID environment variables.", flush=True)
        return False

    try:
        # 1. Navigate to the login page first
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        
        # Wait longer for the form to load (30s)
        await page.wait_for_selector('form button[type="submit"]', timeout=30000) 

        # 2. Use page.fill() and page.click() for stability
        print("➡️ Filling credentials...", flush=True)
        
        await page.fill('input[name="email"]', WATI_EMAIL)
        await page.fill('input[name="password"]', WATI_PASSWORD)
        await page.fill('input[name="tenantId"]', WATI_CLIENT_ID)

        # Check the "Remember Me" box if it's not checked
        checkbox_selector = '.right-box__check-box div[role="checkbox"].unchecked'
        if await page.is_visible(checkbox_selector, timeout=5000):
            await page.click(checkbox_selector)
        
        # 3. Click the Login button and wait for the resulting navigation/page change
        print("➡️ Login button clicked. Waiting for successful navigation...", flush=True)
        
        # We wrap the click in expect_navigation for maximum reliability 
        # (this waits for the browser to register the next page load/route change)
        async with page.expect_navigation(url=WATI_URL): # Expect navigation to WATI_URL
            await page.click('form button[type="submit"]')
        
        # 4. Wait for the final element on the page (60s)
        await page.wait_for_selector("text=Team Inbox", timeout=60000) 
        print("✅ Automatic login successful!", flush=True)
        return True
    
    except PlaywrightTimeout as e:
        print("❌ Automatic login failed. Timeout waiting for form elements or 'Team Inbox'.", flush=True)
        
        error_locator = page.locator(".right-box__error-msg")
        if await error_locator.is_visible(timeout=5000):
            error_text = await error_locator.text_content()
            if error_text.strip():
                print(f"⚠️ Page Error Message: {error_text.strip()}", flush=True)
        return False
    except Exception as e:
        print(f"❌ An unexpected error occurred during login: {e}", flush=True)
        return False


# ✅ Main automation loop (No changes)
async def main_automation(page):
    while True:
        print("🔎 Checking for unread chats...", flush=True)
        try:
            await page.wait_for_selector("div.conversation-item__unread-count", timeout=10000)
        except PlaywrightTimeout:
            print("😴 No unread chats found. Waiting 3 mins...", flush=True)
            await asyncio.sleep(CHECK_INTERVAL)
            try:
                await page.reload(wait_until="domcontentloaded")
            except Exception as reload_e:
                print(f"⚠️ Error during reload: {reload_e}. Will attempt to navigate back to WATI_URL.", flush=True)
                await page.goto(WATI_URL, wait_until="domcontentloaded")
            continue

        unread_elements = await page.query_selector_all("div.conversation-item__unread-count")
        
        if not unread_elements:
            print("😴 No unread chats found after initial wait. Waiting 3 mins...", flush=True)
            await asyncio.sleep(CHECK_INTERVAL)
            await page.reload(wait_until="domcontentloaded")
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
                    print("⚠️ 'Ads (CTWA)' flow option not found.", flush=True)

                await asyncio.sleep(2)

            except Exception as e:
                print(f"⚠️ Error in processing chat #{processed}: {e}", flush=True)
                await page.reload(wait_until="domcontentloaded")
                await asyncio.sleep(5)
                break 

        print("🕒 Finished processing batch. Waiting before next check...", flush=True)
        await asyncio.sleep(CHECK_INTERVAL)
        await page.reload(wait_until="domcontentloaded")


# ✅ Main bot flow
async def run_wati_bot():
    print("🌐 Launching WATI automation with persistent browser...", flush=True)
    headless_mode = ON_RENDER 

    async with async_playwright() as p:
        browser_context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=headless_mode,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--single-process"]
        )
        if len(browser_context.pages) == 0:
            page = await browser_context.new_page()
        else:
            page = browser_context.pages[0]
            
        print("🌍 Navigating to WATI Inbox...", flush=True)
        await page.goto(WATI_URL, timeout=60000)
        await asyncio.sleep(3)
        
        login_success = False
        storage_path = os.path.join(USER_DATA_DIR, "storage.json")

        try:
            # Check for existing logged-in session
            await page.wait_for_selector("text=Team Inbox", timeout=60000)
            print("✅ Logged in — session active!", flush=True)
            login_success = True
        except PlaywrightTimeout:
            print("⚠️ Session inactive, attempting automatic login...", flush=True)
            
            # --- FIX: Clear storage on login failure to ensure a clean auto-login attempt ---
            if os.path.exists(storage_path):
                 print("🗑️ Clearing expired persistent storage...", flush=True)
                 os.remove(storage_path)
            # --- END FIX ---
            
            success = await auto_login(page)
            
            if success:
                await browser_context.storage_state(path=storage_path)
                print("✅ New session saved successfully!", flush=True)
                login_success = True
            
            if not success:
                if ON_RENDER:
                    print("🚨 Fatal Error: Auto-login failed and manual login is impossible on Render. Shutting down.", flush=True)
                    return 
                else:
                    print("ℹ️ Falling back to manual login...")
                    login_success = await wait_for_manual_login(page, browser_context)

        if login_success:
            print("🤖 Starting main WATI automation loop...", flush=True)
            await main_automation(page)
        else:
             print("❌ Login failed. Bot loop will not start.", flush=True)
             
        await browser_context.close()


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
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"🔥 Application stopped due to unhandled error: {e}", flush=True)
