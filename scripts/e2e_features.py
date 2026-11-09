"""Browser end-to-end test (run against a server on a COPY of the store, it uploads a sample):

    python scripts/e2e_features.py http://127.0.0.1:8766

Covers: draft cache (back + reload), pie explanations, report actions, saved reports,
print layout, analyse another. Uses the test server on a store copy."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
SHOTS = Path(__file__).resolve().parents[1] / "data" / "processed" / "e2e_shots"
SHOTS.mkdir(parents=True, exist_ok=True)
errors = []


def ok(cond, what):
    print(("PASS " if cond else "FAIL ") + what)
    if not cond:
        errors.append(what)


with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True)
    ctx = br.new_context(viewport={"width": 1440, "height": 950})
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.on("console", lambda m: m.type == "error" and errors.append(f"console: {m.text}"))

    pg.goto(B + "/")
    pg.get_by_text("Check a SOC's security health").first.wait_for()
    ok(pg.evaluate("document.documentElement.dataset.theme") == "dark", "dark theme is the default")
    pg.wait_for_timeout(800)
    pg.screenshot(path=SHOTS / "f1_home_dark.png")

    # 1. draft cache: choose sector, load sample, go back, come forward
    pg.get_by_role("button", name="Power").click()
    pg.get_by_role("button", name="Next: add your data →").click()
    pg.get_by_role("tab", name="Try a sample").click()
    pg.get_by_text("Bank: full SOC export").click()
    pg.get_by_text("Here's what we see in your data").wait_for(timeout=30000)
    pg.get_by_role("button", name="← Back").click()
    ok(pg.get_by_text("Your data is kept:").is_visible(), "going back keeps the file (step 1 shows it)")
    pg.get_by_role("button", name="Next: add your data →").click()
    ok(pg.get_by_text("Here's what we see in your data").is_visible(), "coming forward still shows the detection")

    # 2. reload: draft restored from IndexedDB
    pg.wait_for_timeout(1200)  # debounce save
    pg.reload()
    pg.get_by_text("from last time on this computer").wait_for(timeout=15000)
    ok(True, "after a page reload the file is restored (banner shown)")
    ok("sample_bank_full_export.zip" in pg.locator("text=from last time").inner_text(), "restored banner names the file")
    ok(pg.get_by_text("Here's what we see in your data").is_visible(), "restored detection panel shown")
    pg.screenshot(path=SHOTS / "f2_restored.png", full_page=True)

    # 3. analyse -> actions + saved
    pg.get_by_role("button", name="Analyse my data →").click()
    pg.get_by_text("Overall result").wait_for(timeout=240000)
    pg.get_by_text("Saved on this computer").first.wait_for(timeout=15000)
    ok(pg.get_by_role("button", name="Save report as PDF").count() == 2, "Save as PDF at top and bottom")
    ok(pg.get_by_role("link", name="Detailed PDF").count() == 2, "Detailed PDF links present")
    ok(pg.get_by_role("button", name="Analyse another").count() == 2, "Analyse another at top and bottom")
    headlines = pg.locator("li h3").all_inner_texts()
    print("   warnings:", headlines)

    # 4. pie explanations
    pg.get_by_role("button", name="Explain").first.click()
    ok(pg.get_by_text("In your data:").first.is_visible(), "pie chart Explain shows 'In your data'")
    print("   explanation:", pg.locator("text=In your data:").first.locator("..").inner_text()[:160])
    pg.wait_for_timeout(500)
    pg.screenshot(path=SHOTS / "f3_report_dark.png", full_page=True)

    # 5. print layout + real PDF
    pg.emulate_media(media="print")
    pg.wait_for_timeout(300)
    bg = pg.evaluate("getComputedStyle(document.querySelector('li.card-hover')).backgroundColor")
    ok(bg in ("rgb(255, 255, 255)", "rgba(0, 0, 0, 0)"), f"print cards are white immediately (got {bg})")
    ok(not pg.locator("aside").is_visible(), "print hides the sidebar")
    ok(not pg.get_by_role("button", name="Save report as PDF").first.is_visible(), "print hides buttons")
    pg.screenshot(path=SHOTS / "f4_print.png", full_page=True)
    pg.pdf(path=str(SHOTS / "report.pdf"), format="A4", print_background=True)
    ok((SHOTS / "report.pdf").stat().st_size > 20000, f"PDF generated ({(SHOTS / 'report.pdf').stat().st_size // 1024} KB)")
    pg.emulate_media(media="screen")

    # 6. saved reports page
    pg.goto(B + "/results?tab=saved")
    pg.get_by_text("Stored on this computer").wait_for()
    ok(pg.get_by_text("Sample Bank").first.is_visible() or pg.locator("li").count() > 0, "saved report listed")
    pg.screenshot(path=SHOTS / "f5_saved_list.png")
    pg.locator("li button").first.click()
    pg.get_by_text("Overall result").wait_for(timeout=15000)
    ok(pg.get_by_text("the live data may have changed since").is_visible(), "saved report reopens from the snapshot")

    # 7. analyse another clears the draft
    pg.goto(B + "/")
    pg.wait_for_timeout(1500)
    if pg.get_by_role("button", name="Analyse another").count():
        pg.get_by_role("button", name="Analyse another").first.click()
    pg.goto(B + "/")
    pg.get_by_text("Check a SOC's security health").first.wait_for()
    pg.wait_for_timeout(1500)
    ok(not pg.get_by_text("from last time on this computer").is_visible(), "after a finished analysis the draft is cleared")
    br.close()

print("errors:", errors or "none")
sys.exit(1 if errors else 0)
