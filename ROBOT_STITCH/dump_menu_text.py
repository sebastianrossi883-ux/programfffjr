import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = Path("/Volumes/Extreme Pro/ROBOT_STITCH/pw-browsers/playwright_chrome_profile")
with sync_playwright() as p:
    try:
        browser = p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=True,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"]
        )
    except Exception as e:
        print("Errore:", e)
        sys.exit(1)
        
    page = browser.pages[0]
    page.goto("https://stitch.withgoogle.com/")
    page.wait_for_timeout(5000)
    
    for frame in page.frames:
        buttons = frame.locator("button, [role=button], [role=combobox]")
        count = buttons.count()
        for i in range(count):
            b = buttons.nth(i)
            if b.is_visible() and ("3 Flash" in b.inner_text() or "3.1 Pro" in b.inner_text()):
                b.click(timeout=1000)
                page.wait_for_timeout(2000)
                break
                
    print("--- OPZIONI ---")
    for frame in page.frames:
        options = frame.locator("[role=option], [role=menuitem]")
        c = options.count()
        if c > 0:
            for i in range(c):
                op = options.nth(i)
                text = " ".join(op.inner_text().split())
                print(f"- {text}")
                
    browser.close()
