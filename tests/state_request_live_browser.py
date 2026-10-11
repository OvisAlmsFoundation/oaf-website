"""Real Chromium worker; no route interception, credential access, or DB mocks.

Invoked by ops/state_request_live_check.py with the existing shared Playwright
interpreter. JSON lines on stdin/stdout coordinate an actual Flask restart.
Cookie/CSRF values stay in process memory and are excluded from evidence.
"""

import json
import sys
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def emit(value):
    print(json.dumps(value), flush=True)


def main():
    settings = json.loads(sys.stdin.readline())
    origin = settings["origin"]
    baseline = settings["baseline"]
    expected = dict(baseline)
    evidence, page_errors, external = [], [], []
    post_calls = []

    def record(test, **details):
        item = {"test": test, "status": "PASS", **details}
        evidence.append(item)
        emit({"event": "check", "check": item})

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            contexts = [browser.new_context(viewport={"width": 1280, "height": 900})
                        for _ in range(3)]
            pages = [context.new_page() for context in contexts]
            a, b, c = pages
            for page in pages:
                page.on("pageerror", lambda error: page_errors.append(type(error).__name__))

                def observe(request):
                    if urlsplit(request.url).netloc != urlsplit(origin).netloc:
                        external.append(urlsplit(request.url).netloc)
                    if request.method == "POST":
                        post_calls.append(request.url)

                page.on("request", observe)

            def visit(page):
                response = page.goto(origin + "/gramanna.html")
                assert response.status == 200
                expect(page.get_by_role("button", name="Request consideration")).to_be_enabled()
                page.get_by_label("Your state", exact=True).select_option("CA")
                expect(page.locator("#request-total")).to_contain_text("for California.")

            def totals(page):
                result = page.evaluate("""async () => {
                    const r = await fetch('/api/state-requests/totals', {cache: 'no-store'});
                    return {code: r.status, data: await r.json()};
                }""")
                assert result["code"] == 200
                return result["data"]["totals"]

            def match_counts(page):
                assert totals(page) == expected, "Actual API totals differ from submission deltas."

            def display(page, state):
                name = "California" if state == "CA" else "Texas"
                number = expected[state]
                text = f"{number} counted request{'s' if number != 1 else ''} for {name}."
                expect(page.locator("#request-total")).to_have_text(text)

            def submit(page, state, accepted, keyboard=False):
                page.get_by_label("Your state", exact=True).select_option(state)
                button = page.get_by_role("button", name="Request consideration")
                with page.expect_response(lambda r: r.url == origin + "/api/state-requests"
                                          and r.request.method == "POST") as pending:
                    if keyboard:
                        page.get_by_label("Your state", exact=True).focus()
                        page.keyboard.press("Tab")
                        expect(button).to_be_focused()
                        page.keyboard.press("Enter")
                    else:
                        button.click()
                response = pending.value
                assert response.status == (201 if accepted else 200)
                assert response.json()["status"] == ("accepted" if accepted else "duplicate")
                if accepted:
                    expected[state] += 1
                note = page.locator("#request-note")
                expect(note).to_contain_text("counted. Thank you." if accepted else "already requested")
                expect(note).to_have_attribute("role", "status")
                expect(note).to_have_attribute("aria-live", "polite")
                expect(button).to_be_enabled()
                expect(page.locator("#state-request-form")).not_to_have_attribute("aria-busy", "true")
                display(page, state)
                match_counts(page)
                return response.status

            visit(a)
            assert a.get_by_label("Your state", exact=True).locator("option").count() == 51
            match_counts(a)
            record("A", http=submit(a, "CA", True, keyboard=True), california=expected["CA"])
            cookie_a = contexts[0].cookies()[0]
            assert cookie_a["name"] == "oaf-state-browser"
            assert cookie_a["httpOnly"] and cookie_a["sameSite"] == "Lax"
            assert not cookie_a["secure"] and cookie_a["path"] == "/" and cookie_a["expires"] > 0
            assert a.evaluate("document.cookie") == ""
            record("B", http=submit(a, "CA", False), california=expected["CA"])
            visit(b)
            record("C", http=submit(b, "CA", True), california=expected["CA"])
            assert contexts[1].cookies()[0]["value"] != cookie_a["value"]
            record("D", http=submit(a, "TX", True), texas=expected["TX"])

            # Native HTML required validation makes no mutation request.
            state = a.get_by_label("Your state", exact=True)
            state.select_option("")
            before = len(post_calls)
            a.get_by_role("button", name="Request consideration").click()
            assert not state.evaluate("node => node.checkValidity()")
            assert len(post_calls) == before
            statuses = a.evaluate("""async () => {
                const s = await (await fetch('/api/state-requests/session')).json();
                const results = [];
                for (const value of ['', 'ZZ', 'California', null]) {
                    const r = await fetch('/api/state-requests', {method: 'POST',
                        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': s.csrf_token},
                        body: JSON.stringify({state: value})});
                    results.push(r.status);
                }
                return results;
            }""")
            assert statuses == [400] * 4
            # Exercise displayed accessible server-rejection feedback through the actual UI.
            state.evaluate("node => node.add(new Option('Invalid state', 'ZZ'))")
            state.select_option("ZZ")
            with a.expect_response(lambda r: r.url == origin + "/api/state-requests") as invalid:
                a.get_by_role("button", name="Request consideration").click()
            assert invalid.value.status == 400
            expect(a.locator("#request-note")).to_have_text("Select one of the 50 U.S. states.")
            expect(a.locator("#request-note")).to_have_attribute("role", "alert")
            expect(a.locator("#request-note")).to_have_attribute("aria-atomic", "true")
            expect(a.get_by_role("button", name="Request consideration")).to_be_enabled()
            match_counts(a)
            record("E", rejected_http=statuses + [400], native_empty_sent_no_request=True)

            before = len(post_calls)
            assert a.reload().status == 200
            expect(a.get_by_role("button", name="Request consideration")).to_be_enabled()
            a.get_by_label("Your state", exact=True).select_option("CA")
            display(a, "CA")
            assert len(post_calls) == before
            assert contexts[0].cookies()[0]["value"] == cookie_a["value"]
            match_counts(a)
            record("F", refresh_mutations=0)
            a.goto(origin + "/about.html")
            visit(a)
            submit(a, "CA", False)
            assert contexts[0].cookies()[0]["value"] == cookie_a["value"]
            record("G", normal_visit_recognition="unchanged")

            # Persisted browser storage in memory survives an actual browser context replacement.
            storage = contexts[0].storage_state()
            contexts[0].close()
            contexts[0] = browser.new_context(storage_state=storage)
            a = contexts[0].new_page()
            a.on("pageerror", lambda error: page_errors.append(type(error).__name__))
            visit(a)
            submit(a, "TX", False)
            assert contexts[0].cookies()[0]["value"] == cookie_a["value"]

            emit({"event": "restart", "counts": expected})
            restarted = json.loads(sys.stdin.readline())
            assert restarted["event"] == "restarted"
            visit(a)
            submit(a, "CA", False)
            submit(a, "TX", False)
            match_counts(a)
            assert contexts[0].cookies()[0]["value"] == cookie_a["value"]
            record("H", actual_process_restart=True, recognition="unchanged", counts=expected.copy())

            visit(c)
            # Eight live HTTP requests launched together from a third independent context.
            responses = c.evaluate("""async () => {
                const s = await (await fetch('/api/state-requests/session')).json();
                return await Promise.all(Array.from({length: 8}, async () => {
                    const r = await fetch('/api/state-requests', {method: 'POST',
                        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': s.csrf_token},
                        body: JSON.stringify({state: 'CA'})});
                    return {code: r.status, status: (await r.json()).status};
                }));
            }""")
            assert sum(r == {"code": 201, "status": "accepted"} for r in responses) == 1
            assert sum(r == {"code": 200, "status": "duplicate"} for r in responses) == 7
            expected["CA"] += 1
            match_counts(c)
            # Deliberate UI repeat also updates the displayed committed count.
            submit(c, "CA", False)
            record("I", submissions=8, accepted=1, duplicates=7, california=expected["CA"])

            expect(c.locator("#request-total")).to_have_attribute("role", "status")
            expect(c.locator("#request-total")).to_have_attribute("aria-live", "polite")
            expect(c.locator("#request-total")).to_have_attribute("aria-atomic", "true")
            c.set_viewport_size({"width": 390, "height": 900})
            assert c.locator("html").evaluate("node => node.scrollWidth <= window.innerWidth")
            assert not page_errors and not external
            record("J", keyboard_submission=True, success_duplicate_error_feedback=True,
                   live_counts=True, mobile_width=390, page_errors=0, external_requests=0)
            # The coordinator derives DB keys from these cookies without persisting their values.
            emit({"event": "complete", "evidence": evidence, "counts": expected,
                  "cookies": {name: context.cookies()[0]["value"]
                              for name, context in zip(("A", "B", "C"), contexts)},
                  "chromium": browser.version})
            for context in contexts:
                context.close()
        finally:
            browser.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Playwright exceptions can contain source/DOM/network values: do not dump them.
        emit({"event": "blocked", "reason": "Real browser assertion or operation failed",
              "exception_type": type(error).__name__})
        sys.exit(2)
