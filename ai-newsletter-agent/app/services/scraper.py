import asyncio
import trafilatura
from playwright.async_api import async_playwright


def is_valid_content(text: str) -> bool:
    """
    Quality Gate: Checks if the scraped text is a real article.
    """
    if not text:
        return False

    # 1. Hard Length Limit
    if len(text) < 600:
        return False

    # 2. Paywall Triggers
    header_sample = text[:1000].lower()
    block_triggers = [
        "subscription required",
        "subscribe to read",
        "log in to continue",
        "access this article",
        "create an account",
        "verify you are human",
        "turn on javascript",
    ]
    if any(trigger in header_sample for trigger in block_triggers):
        return False

    # 3. The "Sidebar Trap" Detector (STRICT MODE)
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    # Headlines are usually < 100 chars. Real paragraphs are > 150.
    # We set the bar at 120 to filter out long headlines while keeping short-ish paragraphs.
    long_paragraphs = [line for line in lines if len(line) >= 150]

    # We need at least 2 substantial paragraphs to call it an "Article"
    if len(long_paragraphs) < 2:
        return False

    return True


async def apply_stealth_async(page):
    """
    Async version of stealth injection.
    """
    await page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    await page.add_init_script("window.chrome = {runtime: {}};")
    await page.add_init_script(
        "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});"
    )
    await page.add_init_script(
        "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});"
    )


async def scrape_url(url: str) -> str:
    """
    Async scraper.
    """
    print(f"   -> Scraping: {url}")
    content = None
    is_blocked = False

    # --- ATTEMPT 1: Fast Static Scrape (Trafilatura) ---
    # Trafilatura is blocking, so we offload just this part to a thread
    try:
        downloaded = await asyncio.to_thread(trafilatura.fetch_url, url)
        if downloaded:
            content = await asyncio.to_thread(
                trafilatura.extract,
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

    # --- ATTEMPT 2: Stealth Browser (Async Playwright) ---
    if not content or len(content) < 600 or is_blocked:
        print("      x Static scrape failed/blocked. Launching Stealth Browser...")

        async with async_playwright() as p:
            try:
                # Launch browser
                browser = await p.chromium.launch(
                    headless=True, args=["--disable-blink-features=AutomationControlled"]
                )

                # Context configuration
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    locale="en-US",
                    timezone_id="America/New_York",
                )

                page = await context.new_page()
                await apply_stealth_async(page)

                # Navigation
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                    await page.wait_for_timeout(5000)  # Wait for Cloudflare

                    # Scroll to trigger lazy loading
                    for _ in range(3):
                        await page.mouse.wheel(0, 3000)
                        await page.wait_for_timeout(1500)

                    html = await page.content()

                    # Extract content (Trafilatura is CPU bound, run in thread)
                    content = await asyncio.to_thread(
                        trafilatura.extract,
                        html,
                        output_format="markdown",
                        include_links=True,
                        include_images=False,
                    )
                    if not is_valid_content(content):
                        print(f"      x Browser scrape rejected (Still Paywalled/Junk).")
                        content = None

                except Exception as e:
                    print(f"      x Browser timeout/error: {e}")
                finally:
                    await browser.close()

            except Exception as e:
                print(f"      x Browser failed to launch: {e}")

    # --- FINAL FORMATTING ---
    if content and "Cloudflare Ray ID" not in content:
        if len(content) > 20000:
            content = content[:20000] + "... [TRUNCATED]"
        return f"FULL ARTICLE CONTENT:\n{content}\n---\n"

    return None
