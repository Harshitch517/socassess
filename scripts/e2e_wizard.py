"""Browser end-to-end test of the Analyze wizard (needs a running server; use a COPY of the store,
because it uploads two samples).

    python scripts/e2e_wizard.py http://127.0.0.1:8766

Click through the wizard in real Chrome: sample with no classification, then a pasted file with full
classification. Screenshots go to data/processed/e2e_shots."""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
SHOTS = Path(__file__).resolve().parents[1] / "data" / "processed" / "e2e_shots"
SHOTS.mkdir(parents=True, exist_ok=True)
errors = []

with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True)
    pg = br.new_page(viewport={"width": 1366, "height": 900})
    pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
    pg.on("pageerror", lambda e: errors.append(str(e)))

    # ---- run 1: sample, nothing classified
    pg.goto(B + "/")
    pg.get_by_text("Check a SOC's security health").wait_for()
    pg.screenshot(path=SHOTS / "w1_step1.png", full_page=True)
    pg.get_by_role("button", name="Next: add your data →").click()
    pg.get_by_role("tab", name="Try a sample").click()
    pg.get_by_text("Power utility: alert export").click()
    pg.get_by_text("Here's what we see in your data").wait_for(timeout=30000)
    assert pg.get_by_text("Please classify your input for a better result").is_visible()
    pg.screenshot(path=SHOTS / "w2_detect.png", full_page=True)
    t = time.time()
    pg.get_by_role("button", name="Analyse my data →").click()
    pg.get_by_text("Overall result").wait_for(timeout=120000)
    pg.get_by_text("What we found").wait_for()
    print(f"run 1 analysed in {time.time() - t:.1f}s")
    pg.wait_for_timeout(1500)
    assert pg.get_by_text("Please classify your input for a better result").first.is_visible()
    headlines = pg.locator("li h3").all_inner_texts()
    print("run 1 warnings:", headlines)
    pg.screenshot(path=SHOTS / "w3_report.png", full_page=True)
    # details toggle
    pg.get_by_role("button", name="Show details").first.click()
    assert pg.get_by_text("Technical name:").first.is_visible()

    # ---- run 2: pasted data, fully classified, one check deselected
    pg.get_by_role("button", name="Analyse other data").click()
    pg.get_by_role("button", name="Banking").click()
    pg.get_by_role("button", name="Small").click()
    pg.get_by_text("Security alerts", exact=True).click()
    pg.get_by_placeholder("e.g. State Power Utility").fill("Paste Test Bank")
    pg.get_by_role("button", name="Next: add your data →").click()
    pg.get_by_role("tab", name="Paste data").click()
    rows = ["time,priority,alert name,host"] + [
        f"2026-07-{1 + i % 28:02d} 10:{i % 60:02d},{'P1' if i % 7 == 0 else 'P3'},"
        f"{'Phishing link' if i % 2 else 'Port scan'},ws{i % 9}"
        for i in range(60)]
    pg.get_by_label("Paste CSV or JSON data").fill("\n".join(rows))
    pg.get_by_role("button", name="Check my data").click()
    pg.get_by_text("Here's what we see in your data").wait_for(timeout=30000)
    assert not pg.get_by_text("Please classify your input for a better result").is_visible()
    pg.get_by_role("button", name="Analyse my data →").click()
    pg.get_by_text("Overall result").wait_for(timeout=120000)
    pg.wait_for_timeout(1500)
    assert not pg.get_by_text("Please classify your input for a better result").is_visible()
    print("run 2 report for:", pg.locator("text=Report for").first.inner_text())
    pg.screenshot(path=SHOTS / "w4_report_classified.png", full_page=True)

    # ---- results page + advanced nav
    pg.goto(B + "/results")
    pg.get_by_text("Overall result").wait_for(timeout=30000)
    pg.wait_for_timeout(1500)
    pg.screenshot(path=SHOTS / "w5_results_all.png")
    pg.get_by_role("button", name="Advanced (for analysts)").click()
    pg.get_by_role("link", name="Dashboard").click()
    pg.get_by_text("Risk ranking").wait_for()
    br.close()

print("console errors:", errors or "none")
sys.exit(1 if errors else 0)
