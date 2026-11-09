import re, sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://aditya-merch-store-analytics.streamlit.app/"

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.goto(URL, wait_until="domcontentloaded", timeout=120000)
    pg.wait_for_timeout(8000)
    btn = pg.get_by_role("button", name=re.compile("get this app back up", re.I))
    if btn.count():
        btn.first.click()
        print("App was asleep, woke it")
        pg.wait_for_timeout(90000)
    else:
        print("App already awake")
    b.close()
