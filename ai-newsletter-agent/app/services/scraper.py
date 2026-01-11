import time
import trafilatura
from playwright.sync_api import sync_playwright


def apply_stealth(page):
    """
    Manually injects JavaScript to hide automation signals.
    """
    page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    page.add_init_script("window.chrome = {runtime: {}};")
    page.add_init_script(
        "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});"
    )
    page.add_init_script(
        "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});"
    )


def scrape_url(url: str) -> str:
    """
    Attempts to scrape a URL using Trafilatura (fast) first,
    falling back to Playwright (stealth) if blocked or empty.
    """
    print(f"   -> Scraping: {url}")
    content = None
    is_blocked = False

    # --- ATTEMPT 1: Fast Static Scrape ---
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            content = trafilatura.extract(
                downloaded,
                output_format="markdown",
                include_links=True,
                include_images=False,
            )
    except Exception:
        pass

    # Check for "Anti-Bot" signals
    if content:
        if "Cloudflare Ray ID" in content or "security service" in content:
            is_blocked = True

    # --- ATTEMPT 2: Stealth Browser ---
    if not content or len(content) < 600 or is_blocked:
        print("      x Static scrape failed/blocked. Launching Stealth Browser...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    locale="en-US",
                    timezone_id="America/New_York",
                )
                page = context.new_page()
                apply_stealth(page)

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=25000)
                    page.wait_for_timeout(5000)  # Wait for Cloudflare

                    # Scroll to trigger lazy loading
                    for _ in range(3):
                        page.mouse.wheel(0, 3000)
                        page.wait_for_timeout(1500)

                    html = page.content()
                    content = trafilatura.extract(
                        html,
                        output_format="markdown",
                        include_links=True,
                        include_images=False,
                    )
                except Exception as e:
                    print(f"      x Browser timeout/error: {e}")
                finally:
                    browser.close()
        except Exception as e:
            print(f"      x Browser failed to launch: {e}")

    # --- FINAL FORMATTING ---
    if content and "Cloudflare Ray ID" not in content:
        if len(content) > 20000:
            content = content[:20000] + "... [TRUNCATED]"
        return f"FULL ARTICLE CONTENT ({url}):\n{content}\n---\n"

    return ""  # Return empty string on failure
