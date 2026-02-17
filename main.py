import os
import asyncio
import time
from datetime import datetime

import discord
from discord.ext import commands

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


# =========================
# 🔐 DISCORD CONFIG
# =========================

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


def create_driver():
    options = Options()
    options.binary_location = "/usr/bin/chromium"
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    service = Service("/usr/bin/chromedriver")

    return webdriver.Chrome(service=service, options=options)


content_script = r"""
(function() {
  'use strict';

  // Configuration
  const CONFIG = {
    POLL_INTERVAL: 200,
    CLICK_DELAY: 80,
    DEBUG: false
  };

  // Centralized state
  const state = {
    active: true,
    busy: {
      fd2w: false,
      w2e: false,
      flashcard: false
    },
    store: { cards: [], seen: new Set() }
  };

  // Utility functions
  const log = (...args) => CONFIG.DEBUG && console.log(...args);
  
  const normalize = (t) => (t || '').toLowerCase().replace(/\s+/g, ' ').trim();
  
  const normalizeExample = (t) => (t || '').toLowerCase().replace(/___/g, ' ').replace(/[^\w\s]/g, '').replace(/\s+/g, ' ').trim();

  const fuzzyMatch = (pageText, storedExample) => {
    const pageNorm = normalizeExample(pageText);
    const storedNorm = normalizeExample(storedExample);
    const words = storedNorm.split(' ');
    
    for (let i = 0; i < words.length; i++) {
      const testWords = [...words];
      testWords.splice(i, 1);
      if (testWords.join(' ') === pageNorm) return true;
    }
    return false;
  };

  // Initialize store from localStorage
  try {
    const saved = localStorage.getItem('rwStore');
    if (saved) {
      const parsed = JSON.parse(saved);
      state.store.cards = parsed;
      state.store.seen = new Set(parsed.map(c => c.word));
      log('📦 Loaded', parsed.length, 'cards from localStorage');
    }
  } catch (e) {
    log('⚠️ Failed to load from localStorage:', e);
  }

  // Automation functions
  const automations = {
    // Click Next/Submit buttons
    clickNextButton() {
      const buttons = document.querySelectorAll('a.btn.btn-primary.btn-rounded');
      buttons.forEach(btn => {
        const text = btn.textContent.trim().toLowerCase();
        const isTarget = ['next', 'submit'].includes(text);
        if (isTarget && !btn.classList.contains('disabled')) {
          btn.click();
        }
      });
    },

    // Click arrow next buttons
    clickArrowNext() {
      const nextArrow = document.querySelector('.item-controls a.next:not(.disabled)');
      if (nextArrow) nextArrow.click();
    },

    // Store flashcard data
    storeFlashcard() {
      const flipped = document.querySelector('.flipcard.flipped');
      if (!flipped) return;

      const word = document.querySelector('.item-name')?.textContent.trim();
      if (!word || state.store.seen.has(word)) return;

      const defHeader = [...document.querySelectorAll('p')].find(p => p.textContent.trim() === 'Definition:');
      const definition = defHeader?.nextElementSibling?.textContent.trim();
      const exampleRaw = document.querySelector('.example p:last-of-type')?.textContent.trim();
      
      if (!definition || !exampleRaw) return;

      const example = normalizeExample(exampleRaw);
      const entry = { word, definition, example };
      state.store.cards.push(entry);
      state.store.seen.add(word);

      log(word + ': ' + definition);
      log('📦 Total cards:', state.store.cards.length);

      try {
        localStorage.setItem('rwStore', JSON.stringify(state.store.cards));
      } catch (e) {
        log('⚠️ Failed to save to localStorage:', e);
      }
    },

    // Solve Definition-to-Word matching
    solveFD2W() {
      if (state.busy.fd2w) return;
      const root = document.querySelector('.items-list');
      if (!root || !state.store.cards.length) return;

      const rows = [...root.querySelectorAll('.items-list-row:not(.filled)')];
      if (!rows.length) return;

      for (const row of rows) {
        const defEl = row.querySelector('.cell-ending .text');
        if (!defEl) continue;
        
        const defText = normalize(defEl.textContent);
        const match = state.store.cards.find(c => normalize(c.definition) === defText);
        if (!match) continue;

        const words = [...root.querySelectorAll('.cell-beginning .word-piece.beginning')];
        const word = words.find(w => {
          const t = w.querySelector('.text');
          return t && normalize(t.textContent) === normalize(match.word);
        });
        if (!word) continue;

        const defClick = row.querySelector('.cell-ending .inner');
        const wordClick = word.querySelector('.inner');
        if (!defClick || !wordClick) continue;

        state.busy.fd2w = true;
        defClick.click();
        setTimeout(() => {
          if (wordClick && document.body.contains(wordClick)) {
            wordClick.click();
          }
          state.busy.fd2w = false;
        }, CONFIG.CLICK_DELAY);
        break;
      }
    },

    // Solve Word-to-Example matching
    solveW2E() {
      if (state.busy.w2e) return;
      const root = document.querySelector('.items-list');
      if (!root || !state.store.cards.length) return;

      const rows = [...root.querySelectorAll('.items-list-row:not(.filled)')];
      if (!rows.length) return;

      let matched = false;

      for (const row of rows) {
        const exampleCard = row.querySelector('.example-sentence, .example-sencence');
        if (!exampleCard) continue;
        
        const exampleEl = exampleCard.querySelector('.text');
        if (!exampleEl) continue;
        
        const exampleText = exampleEl.textContent.trim();
        log('🔍 Looking for:', normalizeExample(exampleText));
        
        const match = state.store.cards.find(c => fuzzyMatch(exampleText, c.example));
        if (!match) {
          log('❌ No match');
          continue;
        }
        log('✅ Matched:', match.word);

        const words = [...root.querySelectorAll('.cell-word')];
        const word = words.find(w => {
          const t = w.querySelector('.text');
          return t && normalize(t.textContent) === normalize(match.word);
        });
        if (!word) {
          log('❌ Word not found on page');
          continue;
        }

        const wordClick = word.querySelector('.inner');
        if (!wordClick) {
          log('❌ Missing click elements');
          continue;
         }

        state.busy.w2e = true;
        log('🎯 CLICKING:', match.word);
        exampleCard.click();
        setTimeout(() => {
          if (wordClick && document.body.contains(wordClick)) {
            wordClick.click();
          }
          state.busy.w2e = false;
        }, CONFIG.CLICK_DELAY);
        matched = true;
        break;
      }

      if (matched) return;

      const remainingExampleTargets = rows
        .map(row => row.querySelector('.example-sentence, .example-sencence'))
        .map(card => {
          if (!card) return null;
          const text = card.querySelector('.text')?.textContent.trim();
          const dropzone = card.querySelector('.text-dropzone');
          const isVisible = Boolean(card.offsetParent);
          if (!isVisible) return null;
          if (dropzone) return { card, clickTarget: dropzone, hasText: Boolean(text) };
          if (text) return { card, clickTarget: card, hasText: true };
          return null;
        })
        .filter(Boolean);

      const remainingWords = [...root.querySelectorAll('.cell-word .inner')].filter(innerEl => {
        const text = innerEl.querySelector('.text')?.textContent.trim();
        const isVisible = Boolean(innerEl.offsetParent);
        const isDisabled = innerEl.classList.contains('disabled') || innerEl.closest('.cell-word')?.classList.contains('disabled');
        const isFilled = innerEl.closest('.cell-word')?.classList.contains('filled') || innerEl.closest('.items-list-row')?.classList.contains('filled');
        return Boolean(text) && isVisible && !isDisabled && !isFilled;
      });

      if (remainingExampleTargets.length === 1 && remainingWords.length === 1) {
        const { clickTarget } = remainingExampleTargets[0];
        const wordClick = remainingWords[0];
        if (!wordClick) return;

        state.busy.w2e = true;
        log('🎯 FALLBACK CLICK');
        clickTarget.click();
        setTimeout(() => {
          if (wordClick && document.body.contains(wordClick)) {
            wordClick.click();
          }
          state.busy.w2e = false;
        }, CONFIG.CLICK_DELAY);
      }
    },

    // Step through flashcards
    stepFlashcard() {
      if (state.busy.flashcard) return;
      const flipcard = document.querySelector('a.flipcard');
      const nextBtn = document.querySelector('.item-controls a.next:not(.disabled)');
      if (!flipcard && !nextBtn) return;

      state.busy.flashcard = true;
      if (nextBtn) {
        nextBtn.click();
        setTimeout(() => state.busy.flashcard = false, CONFIG.CLICK_DELAY);
        return;
      }
      if (flipcard && !flipcard.classList.contains('flipped')) {
        flipcard.click();
      }
      setTimeout(() => state.busy.flashcard = false, CONFIG.CLICK_DELAY);
    }
  };

  // Main execution loop
  const runAutomations = () => {
    if (!state.active) return; // Kill switch check
    
    automations.clickNextButton();
    automations.clickArrowNext();
    automations.storeFlashcard();
    automations.solveFD2W();
    automations.solveW2E();
    automations.stepFlashcard();
  };

  // Flashcard bulk collection system
  const flashcardCollector = {
    isCollecting: false,

    async openFlashcardMenu() {
      const menuToggle = document.querySelector('.flashcards-menu-toggle');
      if (!menuToggle) {
        console.log('❌ Flashcard menu toggle not found');
        return false;
      }

      menuToggle.click();
      console.log('📂 Opening flashcard menu...');

      // Wait for flashcard grid to appear
      return new Promise((resolve) => {
        const checkInterval = setInterval(() => {
          const grid = document.querySelector('.flashcards-grid');
          if (grid && grid.offsetParent) {
            clearInterval(checkInterval);
            console.log('✅ Flashcard menu opened');
            resolve(true);
          }
        }, 100);

        // Timeout after 3 seconds
        setTimeout(() => {
          clearInterval(checkInterval);
          resolve(false);
        }, 3000);
      });
    },

    extractFlashcardData(flipcard) {
      const word = flipcard.querySelector('.item-name')?.textContent.trim();
      if (!word) return null;

      const paragraphs = [...flipcard.querySelectorAll('p')];
      
      const defHeader = paragraphs.find(p => p.textContent.trim() === 'Definition:');
      const definition = defHeader?.nextElementSibling?.textContent.trim();

      const exampleHeader = paragraphs.find(p => p.textContent.trim() === 'Example:');
      const exampleRaw = exampleHeader?.nextElementSibling?.textContent.trim();

      if (!definition) return null;

      const example = exampleRaw ? normalizeExample(exampleRaw) : '';

      return { word, definition, example };
    },

    collectAllFlashcards() {
      const flashcards = document.querySelectorAll('.flashcards-grid .flipcard');
      if (!flashcards.length) {
        console.log('❌ No flashcards found in grid');
        return 0;
      }

      let newCount = 0;
      flashcards.forEach(flipcard => {
        const data = this.extractFlashcardData(flipcard);
        if (!data) return;

        if (!state.store.seen.has(data.word)) {
          state.store.cards.push(data);
          state.store.seen.add(data.word);
          newCount++;
          log(`✅ ${data.word}: ${data.definition}`);
        }
      });

      return newCount;
    },

    saveStore() {
      try {
        localStorage.setItem('rwStore', JSON.stringify(state.store.cards));
        console.log('💾 Saved to localStorage');
      } catch (e) {
        console.log('⚠️ Failed to save to localStorage:', e);
      }
    },

    closeFlashcardMenu() {
      const menuToggle = document.querySelector('.flashcards-menu-toggle');
      if (menuToggle && document.querySelector('.flashcards-grid')?.offsetParent) {
        menuToggle.click();
        console.log('📁 Closing flashcard menu');
      }
    },

    async collect(autoClose = false) {
      if (this.isCollecting) {
        log('⏳ Already collecting...');
        return;
      }

      this.isCollecting = true;
      log('🚀 Starting flashcard collection...');

      const opened = await this.openFlashcardMenu();
      if (!opened) {
        console.log('❌ Failed to open flashcard menu');
        this.isCollecting = false;
        return;
      }

      // Small delay to ensure DOM is ready
      await new Promise(resolve => setTimeout(resolve, 300));

      const newCount = this.collectAllFlashcards();
      this.saveStore();

      log(`✅ Collection complete! Added ${newCount} new cards. Total: ${state.store.cards.length}`);

      if (autoClose) {
        // Small delay before closing
        await new Promise(resolve => setTimeout(resolve, 200));
        this.closeFlashcardMenu();
      }

      this.isCollecting = false;
    }
  };

  // Hotkey setup
  document.addEventListener('keydown', (e) => {
    // Q - Toggle automation on/off
    if (e.key.toLowerCase() === 'q') {
      state.active = !state.active;
      console.log(state.active ? '🟢 Automation STARTED' : '🔴 Automation STOPPED');
    }

    // E - Collect all flashcards from menu
    if (e.key.toLowerCase() === 'e') {
      flashcardCollector.collect();
    }
  });

  // Auto-collect flashcards every 5 seconds (open, collect, close)
  setInterval(() => {
    flashcardCollector.collect(true);
  }, 5000);

  // Single observer for all DOM changes
  const observer = new MutationObserver(runAutomations);
  observer.observe(document.body, { childList: true, subtree: true });

  // Single interval for polling
  setInterval(runAutomations, CONFIG.POLL_INTERVAL);

  // Expose store for debugging
  window.__RW_STORE__ = state.store;
})();
"""

async def run_automation(ctx, username, password):
    await ctx.send("🚀 Starting automation...")

    driver = create_driver()
    wait = WebDriverWait(driver, 20)

    try:
        driver.get("https://app.readingwise.com/users/sign_in")

        wait.until(EC.presence_of_element_located((By.ID, "user_email"))).send_keys(username)
        wait.until(EC.presence_of_element_located((By.ID, "user_password"))).send_keys(password)
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))).click()

        await ctx.send("🔐 Login submitted...")

        time.sleep(3)

        if "sign_in" in driver.current_url:
            await ctx.send("❌ Login failed.")
            driver.quit()
            return

        await ctx.send("✅ Login successful!")

        # Wait for dashboard
        wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a.learner-menu-toggle"))
        )

        await ctx.send("📚 Opening homework...")

        wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.learner-menu-toggle"))
        ).click()

        time.sleep(2)

        continue_btn = driver.find_element(
            By.CSS_SELECTOR,
            ".homeworks-list .card.homework .btn.btn-primary"
        )
        continue_btn.click()

        await ctx.send("🧠 Homework started...")

        start_time = datetime.now()
        driver.execute_script(content_script)

        await ctx.send("⚙️ Running automation...")

        # WAIT LOOP SIMPLIFIED
        max_wait = 1800
        start = time.time()

        while time.time() - start < max_wait:
            try:
                complete = driver.find_element(
                    By.XPATH,
                    "//*[contains(text(),'HOMEWORK COMPLETE!')]"
                )
                if complete:
                    break
            except:
                pass

            await asyncio.sleep(5)

        total_time = (datetime.now() - start_time).total_seconds()

        embed = discord.Embed(
            title="🎉 Homework Complete!",
            color=0x2ecc71
        )
        embed.add_field(name="Username", value=username, inline=True)
        embed.add_field(name="Total Time", value=f"{total_time/60:.1f} minutes", inline=True)

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)[:200]}")
    finally:
        driver.quit()


@bot.command()
async def start(ctx, username: str, password: str):
    await run_automation(ctx, username, password)

from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running.")

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

Thread(target=run_dummy_server).start()

bot.run(TOKEN)
