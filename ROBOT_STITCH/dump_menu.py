import sys
import re
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
    page.wait_for_timeout(10000)
    
    # Trova il bottone
    clicked = False
    for frame in page.frames:
        buttons = frame.locator("button, [role=button], [role=combobox]")
        count = buttons.count()
        for i in range(count):
            b = buttons.nth(i)
            if b.is_visible() and ("3 Flash" in b.inner_text() or "3.1 Pro" in b.inner_text()):
                print("Trovato bottone! Clicco...")
                b.click(timeout=1000)
                page.wait_for_timeout(2000)
                clicked = True
                break
        if clicked:
            break
            
    # Dump HTML dei frame
    html_parts = []
    for frame in page.frames:
        html_parts.append(frame.content())
    
    html = "\n".join(html_parts)
    with open("debug/menu_dump.html", "w") as f:
        f.write(html)
        
    # parse the options
    items = re.findall(r'<[^>]*role=[\"\']?(?:option|menuitem)[^>]*>.*?</[^>]+>', html, flags=re.IGNORECASE|re.DOTALL)
    print(f"Trovate {len(items)} opzioni menu:")
    for item in items:
        text = re.sub(r'<[^>]+>', ' ', item)
        text = ' '.join(text.split())
        print(f" - {text}")

    browser.close()
