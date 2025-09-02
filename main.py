# main.py
# Playwright-based automation for AlgoTest -> Flattrade 3-account daily auth
# Reads credentials from environment variables.
# Sends optional Telegram notification.

import os
import json
import time
import traceback
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------- Config from env ----------
ALGOTEST_PHONE = os.getenv("ALGOTEST_PHONE")           # AlgoTest login phone
ALGOTEST_PASSWORD = os.getenv("ALGOTEST_PASSWORD")     # AlgoTest login password
ACCOUNT_JSON = os.getenv("ACCOUNT_JSON")               # JSON array for 3 Flattrade accounts
HEADLESS = os.getenv("HEADLESS", "1") != "0"           # "0" to disable headless for debugging

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ---------- sanity checks ----------
if not ACCOUNT_JSON:
    raise SystemExit("Set ACCOUNT_JSON environment variable (JSON array of accounts).")

try:
    ACCOUNTS = json.loads(ACCOUNT_JSON)
    if not isinstance(ACCOUNTS, list) or len(ACCOUNTS) == 0:
        raise ValueError()
except Exception:
    raise SystemExit("ACCOUNT_JSON must be a valid JSON array of account objects.")

# ---------- helpers ----------
def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text})
    except Exception as e:
        print("Telegram send failed:", e)

def first_fill(page, selectors, value, timeout=3000):
    for s in selectors:
        try:
            locator = page.locator(s)
            if locator.count() and locator.first.is_visible():
                locator.first.fill(value, timeout=timeout)
                return True
        except Exception:
            pass
    return False

def first_click(page, selectors, timeout=5000):
    for s in selectors:
        try:
            locator = page.locator(s)
            if locator.count() and locator.first.is_visible():
                locator.first.click(timeout=timeout)
                return True
        except Exception:
            pass
    return False

def attempt_login_on_flattrade(fpage, acc):
    user_selectors = [
        "input[name='user_id']",
        "input[name='userid']",
        "input[name='username']",
        "input[id*='user']",
        "input[placeholder*='User']",
        "input[type='text']"
    ]
    pass_selectors = [
        "input[name='password']",
        "input[type='password']",
        "input[id*='pass']",
        "input[placeholder*='Password']"
    ]
    otp_selectors = [
        "input[name='otp']",
        "input[id*='otp']",
        "input[placeholder*='OTP']",
        "input[placeholder*='TOTP']",
    ]
    submit_selectors = [
        "button:has-text('Login')",
        "button:has-text('Submit')",
        "button[type='submit']",
        "input[type='submit']"
    ]

    try:
        fpage.wait_for_timeout(700)
        if not first_fill(fpage, user_selectors, acc.get("userid","")):
            txt = fpage.locator("input[type='text'], input:not([type])")
            if txt.count():
                txt.first.fill(acc.get("userid",""))
        time.sleep(0.2)
        first_fill(fpage, pass_selectors, acc.get("password",""))
        time.sleep(0.2)
        if acc.get("totp"):
            first_fill(fpage, otp_selectors, acc.get("totp",""))
        time.sleep(0.2)
        clicked = first_click(fpage, submit_selectors)
        if not clicked:
            try:
                fpage.keyboard.press("Enter")
            except:
                pass
        for _ in range(40):
            try:
                if "algotest" in fpage.url.lower() or "dashboard" in fpage.url.lower():
                    return True
            except:
                pass
            if fpage.is_closed():
                return True
            time.sleep(0.5)
        return True
    except Exception as e:
        print("Error during Flattrade login:", e)
        traceback.print_exc()
        return False

# ---------- main ----------
def main():
    successes = []
    fails = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=HEADLESS,
                args=["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage"]
            )
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(30000)

            # STEP 1: Open AlgoTest homepage
            print("Opening AlgoTest homepage...")
            page.goto("https://algotest.in")

            # STEP 2: Locate and click Login
            try:
                print("Looking for Login button...")
                if page.locator("text=Login").count():
                    page.locator("text=Login").first.click()
                elif page.locator("button:has-text('Login')").count():
                    page.locator("button:has-text('Login')").first.click()
                elif page.locator("a:has-text('Login')").count():
                    page.locator("a:has-text('Login')").first.click()
                else:
                    raise Exception("Login button not found on homepage")

                print("Clicked Login button")
                page.wait_for_load_state("networkidle")
                time.sleep(2)

                # Fill login form
                if page.locator("input[name='phone']").count():
                    page.fill("input[name='phone']", ALGOTEST_PHONE or "")
                if page.locator("input[type='password']").count():
                    page.fill("input[type='password']", ALGOTEST_PASSWORD or "")
                if page.locator("button:has-text('Login')").count():
                    page.locator("button:has-text('Login')").click()

                page.wait_for_load_state("networkidle")
                time.sleep(3)

            except Exception as e:
                print("Could not complete login:", e)

            # STEP 3: Click Algo Trade
            try:
                page.wait_for_selector("text=Algo Trade", timeout=15000)
                page.locator("text=Algo Trade").first.click()
                print("Clicked Algo Trade")
                time.sleep(2)
            except Exception as e:
                print("Could not click Algo Trade:", e)

            # STEP 4: Click Broker Login
            try:
                page.wait_for_selector("text=Broker Login", timeout=15000)
                page.locator("text=Broker Login").first.click()
                print("Clicked Broker Login")
                page.wait_for_load_state("networkidle")
                time.sleep(3)
            except Exception as e:
                print("Could not click Broker Login:", e)

            # STEP 5: Flattrade flow
            print("Waiting for Broker page to load (Flattrade)...")
            page.wait_for_selector("text=Flattrade", timeout=30000)
            time.sleep(1)

            try:
                page.locator("text=Flattrade").first.click()
                print("Clicked Flattrade broker")
                time.sleep(1.0)
            except Exception:
                print("Could not click Flattrade element; continuing.")

            # STEP 6: Loop over 3 accounts
            login_buttons = page.locator("button:has-text('Login')")
            count = login_buttons.count()
            print("Found total 'Login' buttons on page:", count)
            to_do = min(3, len(ACCOUNTS), count)
            if to_do == 0:
                print("No login buttons found to process. Exiting.")
                send_telegram("Flattrade Auth: no Login buttons found on AlgoTest page.")
                return

            for i in range(to_do):
                acc = ACCOUNTS[i]
                print(f"Processing account #{i+1} userid={acc.get('userid')}")
                try:
                    new_page = None
                    try:
                        with context.expect_page(timeout=7000) as new_page_info:
                            login_buttons = page.locator("button:has-text('Login')")
                            login_buttons.nth(i).click()
                        new_page = new_page_info.value
                    except Exception:
                        try:
                            login_buttons = page.locator("button:has-text('Login')")
                            login_buttons.nth(i).click()
                        except Exception as e:
                            print("Failed to click login button:", e)
                        new_page = page

                    try:
                        new_page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except:
                        pass
                    time.sleep(1)
                    print("Flattrade page URL:", new_page.url)
                    ok = attempt_login_on_flattrade(new_page, acc)
                    if ok:
                        successes.append(acc.get("userid"))
                        print("OK:", acc.get("userid"))
                    else:
                        fails.append(acc.get("userid"))
                        print("Failed:", acc.get("userid"))
                    if new_page is not page:
                        try:
                            if not new_page.is_closed():
                                new_page.close()
                        except:
                            pass
                    time.sleep(2)
                except Exception as e:
                    print("Exception while processing account:", e)
                    traceback.print_exc()
                    fails.append(acc.get("userid"))
                    time.sleep(2)

            browser.close()
    except Exception as e:
        print("Fatal exception:", e)
        traceback.print_exc()
        send_telegram("Flattrade Auth: fatal error. Check logs.")
        raise

    # summary
    msg = f"Flattrade Auth Completed. Success: {len(successes)}, Fail: {len(fails)}\nSuccesses: {successes}\nFails: {fails}"
    print(msg)
    send_telegram(msg)

if __name__ == "__main__":
    main()
