import os
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext, Page
import playwright_stealth
from utils.logger import get_logger
from utils.config import settings

logger = get_logger("Browser")

class BrowserManager:
    def __init__(self):
        self._playwright = None
        self._browser = None
        self.context: BrowserContext = None
        self.page: Page = None
        
    async def start(self):
        logger.info("Starting browser...")
        
        self._playwright = await async_playwright().start()
        profile_dir = Path("browser_profile").absolute()
        
        self.context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=settings.HEADLESS,
            channel="chrome",
            viewport={"width": 1920, "height": 1080},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars"
            ]
        )
        
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        
        logger.info(f"Browser started with persistent profile at {profile_dir}")
        
        # Cloudflare warming logic
        logger.info("Warming up Cloudflare via organic redirect...")
        try:
            await self.page.goto("https://www.google.com/search?q=jobstreet+indonesia", wait_until="commit", timeout=15000)
            await self.page.wait_for_timeout(2000)
            await self.page.goto("https://id.jobstreet.com/", wait_until="domcontentloaded", timeout=15000)
            await self.page.wait_for_timeout(3000)
            logger.info("Cloudflare warm-up complete.")
        except Exception as e:
            logger.warning(f"Cloudflare warm-up failed, continuing anyway: {e}")
            
    async def stop(self):
        logger.info("Stopping browser...")
        if self.context:
            await self.context.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser stopped.")
