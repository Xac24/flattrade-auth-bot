# main.py
# Playwright-based automation for AlgoTest -> Flattrade daily auth
# Uses environment variables for secrets and account list.

import os, json, time, traceback, requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ----------------------------
# Configuration from env
# ----------------------------
ALGO_EMAIL = os.getenv("ALGO_EMAIL")
ALGO_PASSWORD = os.getenv("ALGO_PASSWORD")
ACCOUNT_JSON = os.getenv("ACCOUNT_JSON")  # JSON array string
ALGOTEST_LOGIN_URL = os.getenv("ALGOTEST_LOGIN_URL", "https://algotest.in/broker")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HEADLESS = os.getenv("HEADLESS", "1") != "0"

if not ALGO_EMAIL or not ALGO_PASSWORD or not ACCOUNT_JSON:
    raise SystemExit("Set ALGO_EMAIL, ALGO_PASSWORD and ACCOUNT_JSON environment variables before running.")

try:
    accounts = json.loads(ACCOUNT_JSON)
    assert isinstance(accounts, list)
except Exception as e:
    print("Failed to parse ACCOUNT_JSON. It must be a JSON array of objects.")
    raise

def send_telegram(msg: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except Exception:
        print("Telegram send failed")

def first_fill(page, selectors, value):
    for s in selectors:
        try:
            el = page.locator(s)
            if el.count() and el.is_visible():
                el.fill(value)
                return True
        except Exception:
            pass
    return False

def first_click(page, selectors):
    for s in selectors:
        try:
            el = page.locator(s)
            if el.count() and el.is_visible():
                el.click()
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
        if not first_fill(fpage, user_selectors, acc.get("username","")):
            txts = fpage.locator("input[type='text'], input:not([type])")
            if txts.count():
                txts.first.fill(acc.get("username",""))
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
        print("Exception during Flattrade login attempt:", e)
        traceback.print_exc()
        return False

def main():
    result = {"success": [], "fail": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, args=["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage"])
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(20000)

        print("Opening AlgoTest page...")
        page.goto(ALGOTEST_LOGIN_URL)
        time.sleep(1)

        try:
            login_attempted = False
            if page.locator("input[name='email']").count():
                page.fill("input[name='email']", ALGO_EMAIL); login_attempted = True
            elif page.locator("input[name='username']").count():
                page.fill("input[name='username']", ALGO_EMAIL); login_attempted = True
            if login_attempted:
                if page.locator("input[name='password']").count():
                    page.fill("input[name='password']", ALGO_PASSWORD)
                elif page.locator("input[type='password']").count():
                    page.fill("input[type='password']", ALGO_PASSWORD)
                if page.locator("button:has-text('Login')").count():
                    page.click("button:has-text('Login')")
                elif page.locator("button[type='submit']").count():
                    page.click("button[type='submit']")
                print("Clicked AlgoTest login; waiting for dashboard...")
                page.wait_for_load_state("networkidle")
                time.sleep(2)
            else:
                print("No AlgoTest credential fields detected (already logged in?).")
        except PWTimeout:
            print("Timeout while trying to login to AlgoTest - continuing assuming already logged in.")
        except Exception as e:
            print("Error attempting AlgoTest login:", e)

        page.wait_for_load_state("networkidle")
        time.sleep(2)

        btns = page.locator("button:has-text('Login')")
        count = btns.count()
        print(f"Found {count} 'Login' buttons on the page.")
        if count == 0:
            lks = page.locator("a:has-text('Login')")
            count = lks.count()
            print(f"Found {count} 'Login' links instead.")
            btns = lks

        to_process = min(count, len(accounts))
        if to_process == 0:
            print("Nothing to process. Exiting.")
            send_telegram("Flattrade Auth: nothing to process on AlgoTest page.")
            browser.close()
            return

        for i in range(to_process):
            acc = accounts[i]
            print(f"Processing account #{i+1}: {acc.get('username')}")
            try:
                with context.expect_page() as new_page_info:
                    selector = f"(//button[contains(normalize-space(.),'Login')])[{i+1}]"
                    try:
                        page.locator(selector).click(timeout=10000)
                    except Exception:
                        page.locator("button:has-text('Login')").nth(i).click()
                fpage = new_page_info.value
                fpage.wait_for_load_state("domcontentloaded", timeout=15000)
                time.sleep(1.0)
                print("Flattrade page opened. URL:", fpage.url)
                success = attempt_login_on_flattrade(fpage, acc)
                if success:
                    print(f"Account {acc.get('username')} authenticated (attempted).")
                    result["success"].append(acc.get("username"))
                else:
                    print(f"Account {acc.get('username')} failed to authenticate.")
                    result["fail"].append(acc.get("username"))
                try:
                    if not fpage.is_closed():
                        fpage.close()
                except:
                    pass
                time.sleep(2)
            except Exception as e:
                print(f"Exception while processing account #{i+1}: {e}")
                traceback.print_exc()
                result["fail"].append(acc.get("username"))
                time.sleep(2)
        browser.close()

    msg = f"Flattrade Auth Done. Success: {len(result['success'])}, Fail: {len(result['fail'])}\n"
    msg += "Success list:\n" + "\n".join(result["success"]) + "\n"
    msg += "Fail list:\n" + "\n".join(result["fail"])
    print(msg)
    send_telegram(msg)

if name == "__main__":
    main()