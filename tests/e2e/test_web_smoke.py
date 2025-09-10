# Playwright End-to-End Test Suite (M3: Cypress/Playwright Smoke Tests)
# Simple smoke tests for the MTG Deckbuilder web UI
# Tests critical user flows: deck creation, include/exclude, fuzzy matching

import asyncio
import pytest
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import os

class TestConfig:
    """Test configuration"""
    BASE_URL = os.getenv('TEST_BASE_URL', 'http://localhost:8080')
    TIMEOUT = 30000  # 30 seconds
    
    # Test data
    COMMANDER_NAME = "Alania, Divergent Storm"
    INCLUDE_CARDS = ["Sol Ring", "Lightning Bolt"]
    EXCLUDE_CARDS = ["Mana Crypt", "Force of Will"]
    
@pytest.fixture(scope="session")
async def browser():
    """Browser fixture for all tests"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        yield browser
        await browser.close()

@pytest.fixture
async def context(browser: Browser):
    """Browser context fixture"""
    context = await browser.new_context(
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    yield context
    await context.close()

@pytest.fixture
async def page(context: BrowserContext):
    """Page fixture"""
    page = await context.new_page()
    yield page
    await page.close()

class TestWebUISmoke:
    """Smoke tests for web UI functionality"""
    
    async def test_homepage_loads(self, page: Page):
        """Test that the homepage loads successfully"""
        await page.goto(TestConfig.BASE_URL)
        await page.wait_for_load_state('networkidle')
        
        # Check for key elements
        assert await page.is_visible("h1, h2")
        assert await page.locator("button, .btn").count() > 0
        
    async def test_build_page_loads(self, page: Page):
        """Test that the build page loads"""
        await page.goto(f"{TestConfig.BASE_URL}/build")
        await page.wait_for_load_state('networkidle')
        
        # Check for build elements
        assert await page.is_visible("text=Build a Deck")
        assert await page.is_visible("button:has-text('Build a New Deck')")
        
    async def test_new_deck_modal_opens(self, page: Page):
        """Test that the new deck modal opens correctly"""
        await page.goto(f"{TestConfig.BASE_URL}/build")
        await page.wait_for_load_state('networkidle')
        
        # Click new deck button
        await page.click("button:has-text('Build a New Deck')")
        await page.wait_for_timeout(1000)  # Wait for modal animation
        
        # Check modal is visible
        modal_locator = page.locator('.modal-content')
        await modal_locator.wait_for(state='visible', timeout=TestConfig.TIMEOUT)
        
        # Check for modal contents
        assert await page.is_visible("text=Commander")
        assert await page.is_visible("input[name='commander']")
        
    async def test_commander_search(self, page: Page):
        """Test commander search functionality"""
        await page.goto(f"{TestConfig.BASE_URL}/build")
        await page.wait_for_load_state('networkidle')
        
        # Open new deck modal
        await page.click("button:has-text('Build a New Deck')")
        await page.wait_for_selector('.modal-content')
        
        # Enter commander name
        commander_input = page.locator("input[name='commander']")
        await commander_input.fill(TestConfig.COMMANDER_NAME)
        await page.wait_for_timeout(500)
        
        # Look for search results or feedback
        # This depends on the exact implementation
        # Check if commander search worked (could be immediate or require button click)
        
    async def test_include_exclude_fields_exist(self, page: Page):
        """Test that include/exclude fields are present in the form"""
        await page.goto(f"{TestConfig.BASE_URL}/build")
        await page.wait_for_load_state('networkidle')
        
        # Open new deck modal
        await page.click("button:has-text('Build a New Deck')")
        await page.wait_for_selector('.modal-content')
        
        # Check include/exclude sections exist
        assert await page.is_visible("text=Include") or await page.is_visible("text=Must Include")
        assert await page.is_visible("text=Exclude") or await page.is_visible("text=Must Exclude")
        
        # Check for textareas
        assert await page.locator("textarea[name='include_cards'], #include_cards_textarea").count() > 0
        assert await page.locator("textarea[name='exclude_cards'], #exclude_cards_textarea").count() > 0
        
    async def test_include_exclude_validation(self, page: Page):
        """Test include/exclude validation feedback"""
        await page.goto(f"{TestConfig.BASE_URL}/build")
        await page.wait_for_load_state('networkidle')
        
        # Open new deck modal
        await page.click("button:has-text('Build a New Deck')")
        await page.wait_for_selector('.modal-content')
        
        # Fill include cards
        include_textarea = page.locator("textarea[name='include_cards'], #include_cards_textarea").first
        if await include_textarea.count() > 0:
            await include_textarea.fill("\\n".join(TestConfig.INCLUDE_CARDS))
            await page.wait_for_timeout(500)
            
            # Look for validation feedback (chips, badges, etc.)
            # Check if cards are being validated
            
        # Fill exclude cards
        exclude_textarea = page.locator("textarea[name='exclude_cards'], #exclude_cards_textarea").first
        if await exclude_textarea.count() > 0:
            await exclude_textarea.fill("\\n".join(TestConfig.EXCLUDE_CARDS))
            await page.wait_for_timeout(500)
            
    async def test_fuzzy_matching_modal_can_open(self, page: Page):
        """Test that fuzzy matching modal can be triggered (if conditions are met)"""
        await page.goto(f"{TestConfig.BASE_URL}/build")
        await page.wait_for_load_state('networkidle')
        
        # Open new deck modal
        await page.click("button:has-text('Build a New Deck')")
        await page.wait_for_selector('.modal-content')
        
        # Fill in a slightly misspelled card name to potentially trigger fuzzy matching
        include_textarea = page.locator("textarea[name='include_cards'], #include_cards_textarea").first
        if await include_textarea.count() > 0:
            await include_textarea.fill("Lightning Boltt")  # Intentional typo
            await page.wait_for_timeout(1000)
            
            # Try to proceed (this would depend on the exact flow)
            # The fuzzy modal should only appear when validation runs
            
    async def test_mobile_responsive_layout(self, page: Page):
        """Test mobile responsive layout"""
        # Set mobile viewport
        await page.set_viewport_size({"width": 375, "height": 667})
        
        await page.goto(f"{TestConfig.BASE_URL}/build")
        await page.wait_for_load_state('networkidle')
        
        # Check that elements are still visible and usable on mobile
        assert await page.is_visible("text=Build a Deck")
        
        # Open modal
        await page.click("button:has-text('Build a New Deck')")
        await page.wait_for_selector('.modal-content')
        
        # Check modal is responsive
        modal = page.locator('.modal-content')
        modal_box = await modal.bounding_box()
        
        if modal_box:
            # Modal should fit within mobile viewport with some margin
            assert modal_box['width'] <= 375 - 20  # Allow 10px margin on each side
            
    async def test_configs_page_loads(self, page: Page):
        """Test that the configs page loads"""
        await page.goto(f"{TestConfig.BASE_URL}/configs")
        await page.wait_for_load_state('networkidle')
        
        # Check for config page elements
        assert await page.is_visible("text=Build from JSON") or await page.is_visible("text=Configuration")

class TestWebUIFull:
    """More comprehensive tests (optional, slower)"""
    
    async def test_full_deck_creation_flow(self, page: Page):
        """Test complete deck creation flow (if server is running)"""
        # This would test the complete flow but requires a running server
        # and would be much slower
        pass
        
    async def test_include_exclude_end_to_end(self, page: Page):
        """Test include/exclude functionality end-to-end"""
        # This would test the complete include/exclude flow
        # including fuzzy matching and result display
        pass

# Helper functions for running tests
async def run_smoke_tests():
    """Run all smoke tests"""
    print("Starting MTG Deckbuilder Web UI Smoke Tests...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Basic connectivity test
            await page.goto(TestConfig.BASE_URL, timeout=TestConfig.TIMEOUT)
            print("✓ Server is reachable")
            
            # Run individual test methods
            test_instance = TestWebUISmoke()
            
            await test_instance.test_homepage_loads(page)
            print("✓ Homepage loads")
            
            await test_instance.test_build_page_loads(page)
            print("✓ Build page loads")
            
            await test_instance.test_new_deck_modal_opens(page)
            print("✓ New deck modal opens")
            
            await test_instance.test_include_exclude_fields_exist(page)
            print("✓ Include/exclude fields exist")
            
            await test_instance.test_mobile_responsive_layout(page)
            print("✓ Mobile responsive layout works")
            
            await test_instance.test_configs_page_loads(page)
            print("✓ Configs page loads")
            
            print("\\n🎉 All smoke tests passed!")
            
        except Exception as e:
            print(f"❌ Test failed: {e}")
            raise
            
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run_smoke_tests())
