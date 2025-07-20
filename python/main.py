import logging
import sys
from typing import List, Any, Optional
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI

# --- Logging Configuration ---
def setup_logging():
    """Configure logging with pretty formatting and colors"""
    # Create formatter with timestamp, level, and message
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    
    # Create logger for this module
    logger = logging.getLogger(__name__)
    logger.info("🚀 Application started - Logging configured")
    return logger


# Initialize logging
logger = setup_logging()


client = OpenAI(
    api_key="sk-or-vv-332479a389752e4e178aacf60daa99709ebd4dbcaf7ee44b78c3fd2491293534",
    base_url="https://api.vsegpt.ru/v1",

)


def ask_ai(prompt: str) -> str:
    """Send prompt to AI and return response"""
    logger.debug("🤖 Sending prompt to AI")
    try:
        messages = [
            {"role": "system", "content": "You are an LLM that is used for testing web pages (unit tests and integration tests)"},
            {"role": "user", "content": prompt}
        ]
        completion = client.chat.completions.create(
            model='deepseek/deepseek-r1-alt-0528',
            messages=messages,
            temperature=0.1,
            extra_headers={ "X-Title": "Innotester" },
        )
        response = completion.choices[0].message.content
        if response is None:
            logger.error("❌ AI returned None response")
            return ""
        logger.debug("✅ AI response received")
        return response.strip()
    except Exception as e:
        logger.error(f"❌ AI request failed: {e}")
        raise


class APIResponse(BaseModel):
    data: Optional[Any] = None


class InputData(BaseModel):
    url: str
    tests: List[str]


app = FastAPI()


class WebTestRunner:
    def __init__(self, start_url: str):
        self.current_url = start_url
        self.current_html = ""
        self.logger = logging.getLogger(f"{__name__}.WebTestRunner")


    def fetch_page(self, url: str) -> str:
        """Fetch page HTML using Playwright"""
        self.logger.info(f"🌐 Fetching page: {url}")
        # Use Playwright in headless mode to fetch the page HTML (bypasses Cloudflare)
        try:
            from playwright.sync_api import sync_playwright
            html = ""
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                self.logger.debug("📄 Navigating to page...")
                page.goto(url, timeout=60000)
                page.wait_for_load_state('networkidle', timeout=60000)
                html = page.content()
                browser.close()
            self.current_url = url
            self.current_html = html
            self.logger.info(f"✅ Page fetched successfully ({len(html)} characters)")
            return html
        except Exception as e:
            self.logger.error(f"❌ Failed to fetch page: {e}")
            raise


    def check_page(self, url: str, prompts: List[str]) -> List[bool]:
        """Check page against given criteria"""
        self.logger.info(f"🔍 Checking page against {len(prompts)} criteria")
        try:
            # Fetch page via Selenium for JS-rendered content
            raw_html = self.fetch_page(url)
            soup = BeautifulSoup(raw_html, 'lxml')
            results: List[bool] = []
            
            for i, criterion in enumerate(prompts, 1):
                self.logger.info(f"🔍 Criterion {i}/{len(prompts)}: {criterion}")
                # Extract context for AI if no simple rule
                excerpt = soup
                c_lower = criterion.lower()
                # Choose prompt based on criterion template
                if c_lower.startswith("does") and "exist" in c_lower:
                    instruct = (
                        "Please answer 'Yes' or 'No'.\n"
                        f"Criterion: \"{criterion}\" means check if the specified element exists on the page.\n"
                        "Example: Does logo exist? -> Yes if a logo image is present near the company name.\n"
                    )
                elif c_lower.startswith("is") and "clickable" in c_lower:
                    instruct = (
                        "Please answer 'Yes' or 'No'.\n"
                        f"Criterion: \"{criterion}\" means check if the specified element is clickable (e.g., links, buttons).\n"
                        "Example: Is 'Submit' button clickable? -> Yes if it responds to clicks.\n"
                    )
                elif c_lower.startswith("does") and ("attribute" in c_lower or "value" in c_lower):
                    instruct = (
                        "Please answer 'Yes' or 'No'.\n"
                        f"Criterion: \"{criterion}\" means check if the element has the given attribute or value.\n"
                        "Example: Does input have attribute 'placeholder'? -> Yes if the input tag includes placeholder attribute.\n"
                    )
                else:
                    instruct = (
                        "Please answer 'Yes' or 'No'.\n"
                        f"Criterion: \"{criterion}\". Assess based on page content intelligently.\n"
                    )
                question = f"{instruct}Context: {excerpt}"
                answer = ask_ai(question).lower()
                self.logger.info(f"🤖 AI answer for '{criterion}': {answer}")
                result = answer.startswith("yes")
                results.append(result)
                self.logger.info(f"✅ Criterion {i} result: {'PASS' if result else 'FAIL'}")
            
            self.logger.info(f"📊 Page check completed: {sum(results)}/{len(results)} criteria passed")
            return results
        except Exception as e:
            self.logger.error(f"❌ Error while testing page: {e}")
            return [False] * len(prompts)


    def integration_test(self, test: str, **kwargs) -> tuple[bool, str]:
        """Run integration test using Playwright"""
        try:
            try:
                from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
            except ImportError:
                self.logger.error("❌ Playwright not installed")
                return False, "Playwright not installed"
                
            import time
            import json

            def parse_llm_json(text: str) -> dict:
                try:
                    start = text.find("<json>")
                    end = text.find("</json>", start)
                    if start != -1 and end != -1:
                        json_str = text[start + 6:end]
                        return json.loads(json_str)
                except Exception:
                    pass
                raise ValueError("Failed to parse JSON from LLM response")

            self.logger.info(f"\U0001F9EA Starting integration test: {test}")
            self.logger.info(f"\U0001F4CB Test parameters: {kwargs}")
            history = []
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                try:
                    self.logger.info(f"\U0001F310 Navigating to: {self.current_url}")
                    page.goto(self.current_url, timeout=60000)
                    page.wait_for_load_state('networkidle', timeout=60000)
                    self.logger.info("✅ Page loaded successfully")

                    while True:
                        html = page.content()
                        # Remove <style>, <script>, <img> tags, <link> tags with as="script" or href containing .css, and <svg>, <meta>, <image> tags
                        soup = BeautifulSoup(html, 'lxml')
                        for tag in soup(['style', 'script', 'img', 'svg', 'meta', 'image']):
                            tag.decompose()
                        for link_tag in soup.find_all('link', attrs={'as': 'script'}):
                            link_tag.decompose()
                        for link_tag in soup.find_all('link', href=True):
                            if '.css' in link_tag.get('href', ''):
                                link_tag.decompose()
                        cleaned_html = str(soup)
                        while '\n\n' in cleaned_html:
                            cleaned_html = cleaned_html.replace('\n\n', '\n')

                        # Remove all <jdiv> containers
                        for jdiv_tag in soup.find_all('jdiv'):
                            jdiv_tag.decompose()
                        # Remove all attributes from <div> tags, including 'class' and 'style'
                        for div_tag in soup.find_all('div'):
                            if hasattr(div_tag, 'attrs'):
                                div_tag.attrs.pop('class', None)
                                div_tag.attrs.pop('style', None)
                                div_tag.attrs.clear()
                        # Remove all attributes from <span> tags, including 'class' and 'style'
                        for span_tag in soup.find_all('span'):
                            if hasattr(span_tag, 'attrs'):
                                span_tag.attrs.pop('class', None)
                                span_tag.attrs.pop('style', None)
                                span_tag.attrs.clear()
                        # Remove 'class' attribute from all h1-h4 tags
                        for tag_name in ['h1', 'h2', 'h3', 'h4']:
                            for tag in soup.find_all(tag_name):
                                if getattr(tag, 'attrs', None) and 'class' in tag.attrs:
                                    tag.attrs.pop('class', None)

                        prompt = f'''
                            You are simulating an integration test for the following scenario:

                            Test: "{test}"
                            Parameters: {kwargs}

                            Use this page HTML:
                            {cleaned_html}  <!-- Limit size to avoid overlength -->

                            Available actions:
                            - click(css_selector)
                            - fill(css_selector, text)
                            - wait(seconds)
                            - reload()

                            History of actions taken: {history}

                            Your task is to execute the next logical step(s).
                            - You MAY perform several actions in one step, for example: fill several fields, then click a button.
                            - If you need to fill multiple text fields and then click a button, you can do it in one response.
                            - DO NOT repeat any actions from history.
                            - Think: which step are we on in the scenario?
                            - Think: do I need to perform something on this page or go to another page?
                            - If it is impossible to perform some action on this page, can you transfer to another page, where needed action can be performed?
                            - If test is complete or failed, STOP and return result.
                            - If action cannot be performed, STOP with failure and reason.
                            - REMEMBER: you can only perform actions on the current page (actions from example can be unusable for this page).
                            - **IMPORTANT:** Always make sure that all parentheses and quotes in your action strings are properly closed. For example, fill('input[name="username"]', 'arcenty') must have both parentheses and both single/double quotes closed. Do not return incomplete actions.

                            Respond ONLY with JSON inside <json> tags, like:
                            <json>{{{{"actions": ["fill('#login', 'admin')", "fill('#password', '1234')", "click('#submit')"]}}}}</json>
                            OR
                            <json>{{{{"status": "success", "message": "Login successful"}}}}</json>
                            OR
                            <json>{{{{"status": "fail", "message": "Password field not found"}}}}</json>
                        '''
                        try:
                            self.logger.info("🤖 Sending prompt to LLM...")
                            llm_response = ask_ai(prompt)
                            self.logger.debug(f"🤖 LLM response: {llm_response}")
                            parsed = parse_llm_json(llm_response)
                            self.logger.debug(f"🔍 Parsed response: {parsed}")
                        except Exception as e:
                            self.logger.error(f"❌ Error with LLM or parsing: {e}")
                            browser.close()
                            return False, f"AI or parsing error: {str(e)}"

                        # Handle response
                        if parsed.get("status") == "success":
                            message = parsed.get("message", "Success")
                            self.logger.info(f"✅ Test completed successfully: {message}")
                            browser.close()
                            return True, message
                        if parsed.get("status") == "fail":
                            message = parsed.get("message", "Failure")
                            self.logger.error(f"❌ Test failed: {message}")
                            browser.close()
                            return False, message
                        actions = parsed.get("actions")
                        # Универсальная обработка actions
                        if actions is None:
                            # fallback for single action (старый формат)
                            action = parsed.get("action")
                            if not action:
                                self.logger.error("❌ No valid action(s) received from LLM")
                                browser.close()
                                return False, "No valid action(s) from LLM"
                            actions = [action]
                        elif isinstance(actions, str):
                            actions = [actions]
                        elif isinstance(actions, dict):
                            # Возможно, это статус
                            if actions.get("status") == "success":
                                message = actions.get("message", "Success")
                                self.logger.info(f"✅ Test completed successfully: {message}")
                                browser.close()
                                return True, message
                            if actions.get("status") == "fail":
                                message = actions.get("message", "Failure")
                                self.logger.error(f"❌ Test failed: {message}")
                                browser.close()
                                return False, message
                            # Если не статус — обернём в список на всякий случай
                            actions = [actions]
                        elif not isinstance(actions, list):
                            # Любой другой тип — обернём в список
                            actions = [actions]
                        self.logger.info(f"⚡ Executing actions: {actions!r}")
                        for action in actions:
                            # Check if action is статус-словарь (LLM может вернуть статус внутри списка)
                            if isinstance(action, dict):
                                if action.get("status") == "success":
                                    message = action.get("message", "Success")
                                    self.logger.info(f"✅ Test completed successfully: {message}")
                                    browser.close()
                                    return True, message
                                if action.get("status") == "fail":
                                    message = action.get("message", "Failure")
                                    self.logger.error(f"❌ Test failed: {message}")
                                    browser.close()
                                    return False, message
                                continue
                            history.append(action)
                            try:
                                if action.startswith("click("):
                                    selector = action[len("click("):-1].strip("'\"")
                                    self.logger.info(f"🖱️ Clicking element: {selector}")
                                    page.click(selector, timeout=10000)
                                    self.logger.info("✅ Click successful")
                                elif action.startswith("fill("):
                                    inside = action[len("fill("):-1]
                                    if "," not in inside:
                                        self.logger.error(f"❌ Malformed fill action: {action}")
                                        browser.close()
                                        return False, f"Malformed fill action: {action}"
                                    sel, val = inside.split(",", 1)
                                    sel = sel.strip("'\" ")
                                    val = val.strip("'\" ")
                                    self.logger.info(f"✏️ Filling element {sel} with value: {val}")
                                    page.fill(sel, val, timeout=10000)
                                    self.logger.info("✅ Fill successful")
                                elif action.startswith("wait("):
                                    seconds = float(action[len("wait("):-1])
                                    self.logger.info(f"⏳ Waiting for {seconds} seconds")
                                    time.sleep(seconds)
                                    self.logger.info("✅ Wait completed")
                                elif action == "reload()":
                                    self.logger.info("🔄 Reloading page")
                                    page.reload(timeout=10000)
                                    self.logger.info("✅ Page reloaded")
                                else:
                                    self.logger.error(f"❌ Unknown action: {action}")
                                    browser.close()
                                    return False, f"Unknown action: {action}"
                                time.sleep(1)
                                self.logger.debug(f"📝 Action completed. History: {history}")
                            except PlaywrightTimeoutError as e:
                                self.logger.error(f"⏰ Action timeout: {action}, error: {e}")
                                browser.close()
                                return False, f"Action timeout: {action}, error: {e}"
                            except Exception as e:
                                self.logger.error(f"❌ Action failed: {action}, error: {e}")
                                browser.close()
                                return False, f"Action failed: {action}, error: {e}"
                        # После выполнения всех действий — если среди них был статус, мы уже завершили тест выше
                        # иначе — продолжаем цикл
                        time.sleep(2)
                finally:
                    browser.close()
                    self.logger.info("🔒 Browser closed")
            return False, "Error while testing"
        except Exception as e:
            # raise e
            self.logger.error(f"❌ Error while testing integration: {e}")
            return False, "Error while testing"


@app.post("/run", response_model=APIResponse)
def run_tests(data: InputData):
    """API endpoint to run tests"""
    logger.info(f"🚀 Starting test run for URL: {data.url}")
    logger.info(f"📋 Tests to run: {data.tests}")
    
    runner = WebTestRunner(data.url)
    a = data.tests
    unit_tests = []
    integration_tests = []
    for test in data.tests:
        if test.lower().startswith("does") or test.lower().startswith("is"):
            unit_tests.append(test)
        else:
            integration_tests.append(test)
    try:
        result = runner.check_page(data.url, unit_tests)
        for integration_test in integration_tests:
            flag, comment = runner.integration_test(integration_test)
            result.append({'test': integration_test, 'result': flag, 'comment': comment})
    except Exception as e:
        logger.error(f"❌ Test execution failed: {e}")
        return APIResponse(data=None)

    go_payload = [
        {"test": test, "result": result}
        for test, result in zip(data.tests, result)
    ]

    try:
        logger.info("📤 Sending results to Go API...")
        post_resp = requests.post(
            "http://go-api:8081/api/results",
            json=go_payload,
            timeout=5
        )
        post_resp.raise_for_status()
        logger.info("✅ Results sent successfully")
    except Exception as e:
        logger.error(f"❌ Failed to send results to Go API: {e}")
        return APIResponse(data=None)

    logger.info(f"📊 Test results: {go_payload}")
    return APIResponse(data=go_payload)



if __name__ == "__main__":
    import uvicorn
    logger.info("🌐 Starting FastAPI server on port 3000")
    uvicorn.run(app, host="0.0.0.0", port=3000)
