"""Drive the running web app with a headless system Chrome (Playwright) and take screenshots.

Usage (servers running on :3000 / :8000):
    uv run --with playwright python scripts/ui_drive.py out_dir < steps.txt
Steps, one per line:
    nav <url> | wait <text> | waitsel <css> | click <css> | fill <css> | <text> | press <key>
    shot <name> | sleep <ms> | dark | light | viewport <w> <h>
Console errors and failed requests are printed at the end.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path(sys.argv[1] if len(sys.argv) > 1 else "ui-shots")
out.mkdir(parents=True, exist_ok=True)
errors: list[str] = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: m.type == "error" and errors.append(f"console: {m.text}"))
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}\n{(e.stack or '')[:1500]}"))
    page.on("requestfailed", lambda r: errors.append(f"requestfailed: {r.url} {r.failure}"))
    for raw in sys.stdin:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cmd, _, arg = line.partition(" ")
        try:
            if cmd == "nav":
                page.goto(arg, wait_until="domcontentloaded")
            elif cmd == "wait":
                page.get_by_text(arg, exact=False).first.wait_for(timeout=180_000)
            elif cmd == "waitsel":
                page.locator(arg).first.wait_for(timeout=180_000)
            elif cmd == "click":
                page.locator(arg).first.click()
            elif cmd == "fill":
                sel, _, text = arg.partition(" | ")
                page.locator(sel.strip()).first.fill(text)
            elif cmd == "press":
                page.keyboard.press(arg)
            elif cmd == "sleep":
                page.wait_for_timeout(int(arg))
            elif cmd == "shot":
                page.screenshot(path=str(out / f"{arg}.png"), full_page=True)
                print(f"shot {out / arg}.png")
            elif cmd in ("dark", "light"):
                page.emulate_media(color_scheme=cmd)
            elif cmd == "viewport":
                w, h = arg.split()
                page.set_viewport_size({"width": int(w), "height": int(h)})
            else:
                print(f"unknown command {cmd}")
        except Exception as e:  # keep going so one failed step doesn't hide the rest
            print(f"FAILED {line}: {type(e).__name__}: {str(e)[:300]}")
            page.screenshot(path=str(out / "failure.png"), full_page=True)
    browser.close()
print("\n".join(errors) if errors else "no console errors")
