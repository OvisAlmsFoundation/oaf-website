"""Actual Chromium/Flask/PostgreSQL checks; no routes or responses are mocked.

Private values travel only through coordinator pipes and are never evidence.
No tracing, HARs, DOM dumps, request bodies or exception text are recorded.
"""

import json
import re
import sys
import traceback
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

PHASE = "startup"


def emit(value):
    print(json.dumps(value), flush=True)


def main():
    global PHASE
    settings = json.loads(sys.stdin.readline())
    origin = settings["origin"]
    expected_counts = dict(settings["baseline"])
    lifecycles, errors, requests, screenshots = [], [], [], []
    marker = uuid4().hex

    def record(test, **details):
        emit(dict(event="check", check=dict(test=test, status="PASS", **details)))

    def verify(test):
        emit(dict(event="verify", test=test, lifecycles=lifecycles))
        response = json.loads(sys.stdin.readline())
        assert response["event"] == "verified"
        return response["winners"]

    def choices(label, **changes):
        return dict(dict(label=label, email=f"oaf-{marker}-{label}@example.invalid",
            web_launch=True, android_launch=False, ios_launch=False, state=None,
            consent=True, token=uuid4().hex + uuid4().hex, active=True), **changes)

    def payload(item):
        return {key: item[key] for key in ("email", "web_launch", "android_launch",
                                         "ios_launch", "state", "consent", "token")}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            contexts = [browser.new_context(viewport=dict(width=1280, height=900)),
                        browser.new_context(viewport=dict(width=390, height=900))]
            pages = [context.new_page() for context in contexts]
            desktop, mobile = pages
            for context in contexts:
                context.on("request", lambda request: requests.append((request.method, request.url)))
            for page in pages:
                page.on("pageerror", lambda error: errors.append(type(error).__name__))

            def visit(page):
                assert page.goto(origin + "/gramanna.html").status == 200
                expect(page.get_by_role("button", name="Subscribe", exact=True)).to_be_enabled()
                expect(page.get_by_role("button", name="Request consideration")).to_be_enabled()

            def api(page, data, path="/api/notifications", *, raw=False,
                    content_type="application/json", csrf=True):
                return page.evaluate("""async p => {
                    const session = await (await fetch('/api/notifications/session')).json();
                    const headers = {'Content-Type': p.contentType};
                    if (p.csrf) headers['X-CSRF-Token'] = session.csrf_token;
                    const response = await fetch(p.path, {method: 'POST', headers,
                        body: p.raw ? p.data : JSON.stringify(p.data)});
                    return {code: response.status, data: await response.json(),
                        cache: response.headers.get('Cache-Control'),
                        nosniff: response.headers.get('X-Content-Type-Options')};
                }""", dict(data=data, path=path, raw=raw, contentType=content_type, csrf=csrf))

            def fill(page, item):
                page.get_by_label("Email address", exact=True).fill(item["email"])
                for key, selector in [("web_launch", "#notify-web"),
                    ("android_launch", "#notify-android"), ("ios_launch", "#notify-ios")]:
                    page.locator(selector).set_checked(item[key])
                page.locator("#notify-state").set_checked(item["state"] is not None)
                if item["state"] is not None:
                    page.get_by_label("State for availability updates").select_option(item["state"])
                page.locator("#notification-consent").check()

            def feedback(page, selector, error=False):
                note = page.locator(selector)
                expect(note).to_have_attribute("role", "alert" if error else "status")
                expect(note).to_have_attribute("aria-live", "polite")
                expect(note).to_have_attribute("aria-atomic", "true")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

            def screenshot(page, name):
                page.get_by_label("Email address", exact=True).fill("")
                assert "#unsubscribe=" not in page.url
                filename = settings["evidence_directory"] + "/" + name + ".png"
                # Keep the tested width. A tall capture viewport avoids Chromium's
                # offscreen sticky-header compositing artifacts on long forms.
                original = dict(page.viewport_size)
                form = page.locator("#notification-form")
                page.set_viewport_size(dict(width=original["width"],
                    height=max(original["height"], int(form.bounding_box()["height"]) + 200)))
                try:
                    form.screenshot(path=filename, style=".site-header { visibility: hidden !important; }")
                finally:
                    page.set_viewport_size(original)
                screenshots.append(filename)

            def subscribe_ui(page, item, keyboard=False, retain=True):
                fill(page, item)
                button = page.get_by_role("button", name="Subscribe", exact=True)
                with page.expect_response(lambda response: response.url == origin + "/api/notifications"
                                          and response.request.method == "POST") as pending:
                    if keyboard:
                        page.locator("#notification-consent").focus()
                        page.keyboard.press("Tab")
                        expect(button).to_be_focused()
                        page.keyboard.press("Enter")
                    else:
                        button.click()
                response = pending.value
                assert response.status == 200
                sent = response.request.post_data_json
                result = response.json()
                assert set(result) == {"status", "message", "unsubscribe_token"}
                assert result["status"] == "received"
                assert sent["email"].lower() not in result["message"].lower()
                assert response.headers["cache-control"] == "no-store"
                item["token"] = sent["token"]
                item["capability"] = result["unsubscribe_token"]
                assert re.fullmatch(r"[0-9a-f]{64}\.[0-9a-f]{64}", item["capability"])
                expect(page.locator("#notification-message")).to_contain_text("No email has been sent.")
                expect(page.get_by_label("Email address", exact=True)).to_have_value("")
                expect(button).to_be_enabled()
                expect(page.locator("#notification-form")).to_have_attribute("aria-busy", "false")
                feedback(page, "#notification-message")
                assert page.locator("#notification-unsubscribe-link").get_attribute("href") == (
                    "/gramanna.html#unsubscribe=" + item["capability"])
                if retain:
                    lifecycles.append(item)
                return result["message"]

            def rejection_ui(page, width):
                item = choices("invalid-state", web_launch=False, state="CA")
                fill(page, item)
                state = page.get_by_label("State for availability updates")
                assert state.locator("option").count() == 51
                state.evaluate("node => node.add(new Option('Invalid test state', 'ZZ'))")
                state.select_option("ZZ")
                with page.expect_response(lambda r: r.url == origin + "/api/notifications") as response:
                    page.get_by_role("button", name="Subscribe", exact=True).click()
                assert response.value.status == 400
                expect(page.locator("#notification-message")).to_contain_text("50 U.S. states")
                feedback(page, "#notification-message", error=True)
                screenshot(page, f"notification-{width}-error")
                state.evaluate("node => node.querySelector('option[value=ZZ]').remove()")

            if settings.get("evidence_only"):
                # Focused capture correction after a completed run. These are
                # active duplicates; the coordinator independently verifies no writes.
                for page, width in [(desktop, 1280), (mobile, 390)]:
                    visit(page)
                    rejection_ui(page, width)
                    subscribe_ui(page, choices("evidence-duplicate",
                        email=settings["synthetic_email"]), retain=False)
                    screenshot(page, f"notification-{width}-success")
                assert not errors
                assert all(urlsplit(url).netloc == urlsplit(origin).netloc for _, url in requests)
                emit(dict(event="complete", evidence_only=True, screenshots=screenshots,
                          page_errors=0, external_requests=0, chromium=browser.version))
                for context in contexts:
                    context.close()
                return

            PHASE = "A native consent and validation"
            visit(desktop)
            visit(mobile)
            button = desktop.get_by_role("button", name="Subscribe", exact=True)
            email = desktop.get_by_label("Email address", exact=True)
            before = sum(method == "POST" for method, _ in requests)
            button.click()
            expect(email).to_be_focused()
            email.fill("invalid")
            button.click()
            expect(email).to_be_focused()
            email.fill(choices("native")["email"])
            desktop.locator("#notify-web").check()
            button.click()
            expect(desktop.locator("#notification-consent")).to_be_focused()
            desktop.locator("#notification-consent").check()
            desktop.locator("#notify-web").uncheck()
            button.click()
            expect(desktop.locator("#notification-message")).to_have_text("Choose at least one notification preference.")
            expect(desktop.locator("#notify-web")).to_be_focused()
            feedback(desktop, "#notification-message", error=True)
            desktop.locator("#notify-state").check()
            button.click()
            expect(desktop.get_by_label("State for availability updates")).to_be_focused()
            assert sum(method == "POST" for method, _ in requests) == before
            verify("native_validation_no_writes")
            record("A", native_invalid_email_consent_preferences_state=True, mutation_requests=0)

            PHASE = "B desktop real server error and anonymous signup"
            rejection_ui(desktop, 1280)
            primary = choices("primary", android_launch=True, ios_launch=True, state="CA")
            new_message = subscribe_ui(desktop, primary, keyboard=True)
            screenshot(desktop, "notification-1280-success")
            verify("anonymous_combined_preferences")
            cookie = contexts[0].cookies()[0]
            assert cookie["httpOnly"] and cookie["sameSite"] == "Lax" and cookie["name"] == "oaf-state-browser"
            assert desktop.evaluate("document.cookie") == ""
            record("B", anonymous_signup_http=200, combined_platform_preferences=True,
                   state="CA", keyboard_submission=True, cookie_http_only=True)

            PHASE = "C individual preferences and mobile feedback"
            rejection_ui(mobile, 390)
            for label, page, changes in [
                ("web-only", desktop, {}),
                ("android-only", mobile, dict(web_launch=False, android_launch=True)),
                ("ios-only", desktop, dict(web_launch=False, ios_launch=True)),
                ("state-only", mobile, dict(web_launch=False, state="WA"))]:
                subscribe_ui(page, choices(label, **changes))
            screenshot(mobile, "notification-390-success")
            verify("individual_platform_and_state_preferences")
            record("C", web_only=True, android_only=True, ios_only=True, state_only="WA",
                   widths=[1280, 390], server_error_and_success_live_regions=True)

            PHASE = "D invalid and malformed live API requests"
            valid = payload(choices("rejected"))
            cases = []
            for value in [False, 1, "true", None]:
                cases.append(dict(valid, consent=value))
            cases.append({key: value for key, value in valid.items() if key != "consent"})
            for value in [None, 3, [], "", "bad", "a@@example.invalid", "a@localhost",
                          ".a@example.invalid", "a..b@example.invalid", "a@-example.invalid",
                          "a@example.123", "a\n@example.invalid", "a" * 65 + "@example.invalid"]:
                cases.append(dict(valid, email=value))
            for change in [dict(web_launch=1), dict(android_launch="true"), dict(ios_launch=None),
                dict(web_launch=False), dict(state="ZZ"), dict(state="ca"), dict(state="DC"),
                dict(state=42), dict(state=[]), dict(token="F" * 64), dict(token="f" * 63),
                dict(token=None), dict(token={})]:
                cases.append(dict(valid, **change))
            cases.extend([None, [], "text", {}, dict(valid, extra=True)])
            statuses = [api(desktop, case)["code"] for case in cases]
            assert statuses == [400] * len(cases)
            for data, mime, status in [("{", "application/json", 400),
                ("x" * 1025, "application/json", 413), ("bad", "text/plain", 415)]:
                assert api(desktop, data, raw=True, content_type=mime)["code"] == status
            assert api(desktop, valid, csrf=False)["code"] == 403
            verify("invalid_and_malformed_no_writes")
            record("D", strict_json_rejections=len(cases), malformed_http=400,
                   oversized_http=413, wrong_content_type_http=415, missing_csrf_http=403)

            PHASE = "E active duplicate from an independent browser"
            duplicate = choices("duplicate", email=primary["email"].upper(), web_launch=False, state="TX")
            assert subscribe_ui(mobile, duplicate, retain=False) == new_message
            assert duplicate["capability"] != primary["capability"]
            trimmed = payload(dict(duplicate, email=" " + primary["email"].upper() + " "))
            assert api(desktop, trimmed)["code"] == 200
            assert api(desktop, payload(primary))["code"] == 200
            verify("active_duplicates_preserve_original_preferences")
            record("E", separate_browser_duplicate=True, normalized_duplicate=True,
                   identical_receipt_retry=True, generic_response=True, original_preferences_unchanged=True)

            PHASE = "F private link security"
            bad_tokens = [None, 7, {}, "broken", primary["token"],
                          primary["capability"][:-1] + ("0" if primary["capability"][-1] != "0" else "1")]
            assert all(api(mobile, dict(token=token), "/api/notifications/unsubscribe")["code"] == 400
                       for token in bad_tokens)
            assert api(mobile, dict(token=primary["capability"], extra=True),
                       "/api/notifications/unsubscribe")["code"] == 400
            assert api(mobile, dict(token=primary["capability"]),
                       "/api/notifications/unsubscribe", csrf=False)["code"] == 403
            csrf = mobile.evaluate("async () => (await (await fetch('/api/notifications/session')).json()).csrf_token")
            response = contexts[1].request.post(origin + "/api/notifications/unsubscribe",
                headers={"Origin": "https://foreign.example.invalid", "X-CSRF-Token": csrf},
                data=dict(token=primary["capability"]))
            assert response.status == 403
            response = contexts[1].request.post(origin + "/api/notifications/unsubscribe",
                headers={"Origin": origin, "X-CSRF-Token": csrf, "Sec-Fetch-Site": "cross-site"},
                data=dict(token=primary["capability"]))
            assert response.status == 403
            other_csrf = desktop.evaluate("async () => (await (await fetch('/api/notifications/session')).json()).csrf_token")
            response = contexts[1].request.post(origin + "/api/notifications/unsubscribe",
                headers={"Origin": origin, "X-CSRF-Token": other_csrf}, data=dict(token=primary["capability"]))
            assert response.status == 403
            assert contexts[1].request.get(origin + "/api/notifications/unsubscribe").status == 405
            unknown = api(mobile, dict(token=duplicate["capability"]), "/api/notifications/unsubscribe")
            assert unknown["code"] == 200
            verify("tampered_csrf_origin_get_and_duplicate_link_no_withdrawal")
            record("F", invalid_capabilities=len(bad_tokens) + 1, signature_tampering_http=400,
                   cross_browser_csrf_http=403, foreign_origin_http=403, cross_site_http=403,
                   get_http=405, duplicate_receipt_cannot_withdraw_original=True)

            PHASE = "G explicit link withdrawal"
            navigation = mobile.goto(origin + "/gramanna.html#unsubscribe=" + primary["capability"])
            # A same-document fragment navigation has no HTTP response.
            assert navigation is None or navigation.status == 200
            expect(mobile.locator("#notification-unsubscribe")).to_be_visible()
            expect(mobile.locator("#unsubscribe-title")).to_be_focused()
            assert "#unsubscribe=" not in mobile.url
            verify("opening_link_does_not_withdraw")
            withdraw = mobile.get_by_role("button", name="Unsubscribe", exact=True)
            with mobile.expect_response(lambda r: r.url == origin + "/api/notifications/unsubscribe") as pending:
                withdraw.click()
            assert pending.value.status == 200 and pending.value.json() == unknown["data"]
            primary["active"] = False
            expect(mobile.locator("#notification-unsubscribe-message")).to_contain_text("has been unsubscribed")
            feedback(mobile, "#notification-unsubscribe-message")
            verify("explicit_withdrawal")
            record("G", link_removed_from_address_bar=True, navigation_mutations=0,
                   explicit_withdrawal_http=200, accessible_withdrawal_feedback=True)

            PHASE = "H repeated withdrawal and permanent withdrawn receipt"
            again = api(desktop, dict(token=primary["capability"]), "/api/notifications/unsubscribe")
            assert again["code"] == 200 and again["data"] == unknown["data"]
            assert api(desktop, payload(primary))["code"] == 200
            hijack = payload(dict(primary, email=choices("receipt-hijack")["email"]))
            assert api(desktop, hijack)["code"] == 200
            verify("repeated_withdrawal_and_receipt_replay")
            record("H", repeated_withdrawal_http=200, withdrawal_timestamp_unchanged=True,
                   withdrawn_receipt_cannot_reactivate=True, receipt_cannot_change_email=True)

            PHASE = "I fresh consent after withdrawal"
            visit(desktop)
            renewal = choices("renewal", email=primary["email"], web_launch=False, state="TX")
            subscribe_ui(desktop, renewal)
            assert api(mobile, dict(token=primary["capability"]), "/api/notifications/unsubscribe")["code"] == 200
            verify("fresh_consent_new_lifecycle_old_link_isolated")
            record("I", new_receipt_and_consent=True, new_state="TX", old_link_cannot_withdraw_new=True)

            PHASE = "J concurrent duplicate emails"
            concurrent = choices("concurrent-email", android_launch=True)
            candidates = [uuid4().hex + uuid4().hex for _ in range(16)]
            result = desktop.evaluate("""async p => {
                const s = await (await fetch('/api/notifications/session')).json();
                return await Promise.all(p.tokens.map(async token => {
                    const r = await fetch('/api/notifications', {method:'POST',
                        headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf_token},
                        body:JSON.stringify({...p.data, token})});
                    return {code:r.status,data:await r.json()};
                }));
            }""", dict(tokens=candidates, data=payload(concurrent)))
            assert all(item["code"] == 200 and item["data"]["status"] == "received" for item in result)
            concurrent.pop("token")
            concurrent["candidates"] = candidates
            lifecycles.append(concurrent)
            winner = verify("sixteen_concurrent_email_submissions")[concurrent["label"]]
            concurrent["token"] = candidates[winner]
            concurrent["capability"] = result[winner]["data"]["unsubscribe_token"]
            concurrent.pop("candidates")
            record("J", simultaneous_submissions=16, http_200=16, committed_lifecycles=1)

            PHASE = "K concurrent identical receipts"
            receipt = choices("concurrent-receipt", web_launch=False, ios_launch=True)
            result = desktop.evaluate("""async data => {
                const s = await (await fetch('/api/notifications/session')).json();
                return await Promise.all(Array.from({length:16}, async () => {
                    const r = await fetch('/api/notifications', {method:'POST',
                        headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf_token},
                        body:JSON.stringify(data)});
                    return {code:r.status,data:await r.json()};
                }));
            }""", payload(receipt))
            assert all(item["code"] == 200 for item in result)
            assert len({item["data"]["unsubscribe_token"] for item in result}) == 1
            receipt["capability"] = result[0]["data"]["unsubscribe_token"]
            lifecycles.append(receipt)
            verify("sixteen_concurrent_identical_receipts")
            record("K", simultaneous_submissions=16, http_200=16, committed_lifecycles=1)

            PHASE = "L actual Flask process restart"
            emit(dict(event="restart"))
            assert json.loads(sys.stdin.readline())["event"] == "restarted"
            visit(desktop)
            assert contexts[0].cookies()[0]["value"] == cookie["value"]
            assert api(desktop, payload(primary))["code"] == 200
            assert api(desktop, payload(concurrent))["code"] == 200
            verify("actual_restart_preserves_receipts_preferences_and_consent")
            record("L", actual_flask_restart=True, recognition_cookie_preserved=True,
                   active_and_withdrawn_receipts_persist=True, withdrawn_replay_safe=True)

            PHASE = "M original signed link works after restart"
            mobile.goto(origin + "/gramanna.html#unsubscribe=" + renewal["capability"])
            expect(mobile.locator("#unsubscribe-title")).to_be_focused()
            with mobile.expect_response(lambda r: r.url == origin + "/api/notifications/unsubscribe") as pending:
                mobile.get_by_role("button", name="Unsubscribe", exact=True).click()
            assert pending.value.status == 200
            renewal["active"] = False
            assert api(mobile, dict(token=renewal["capability"]), "/api/notifications/unsubscribe")["code"] == 200
            assert api(mobile, payload(renewal))["code"] == 200
            verify("pre_restart_signed_link_and_withdrawn_replay")
            record("M", saved_link_valid_after_restart=True, repeat_and_reactivation_safe=True)

            PHASE = "N focused State Request regression"
            visit(desktop)
            def state_submit(state, accepted):
                desktop.get_by_label("Your state", exact=True).select_option(state)
                with desktop.expect_response(lambda r: r.url == origin + "/api/state-requests"
                                             and r.request.method == "POST") as pending:
                    desktop.get_by_role("button", name="Request consideration").click()
                assert pending.value.status == (201 if accepted else 200)
                assert pending.value.json()["status"] == ("accepted" if accepted else "duplicate")
                if accepted:
                    expected_counts[state] += 1
                expect(desktop.locator("#request-note")).to_contain_text("counted. Thank you." if accepted else "already requested")
                expect(desktop.locator("#request-total")).to_contain_text(str(expected_counts[state]) + " counted request")
                feedback(desktop, "#request-note")
            state_submit("CA", True)
            state_submit("CA", False)
            state_submit("TX", True)
            statuses = desktop.evaluate("""async () => {
                const s = await (await fetch('/api/state-requests/session')).json();
                const results = [];
                for (const state of ['', 'ZZ', null]) {
                    const r = await fetch('/api/state-requests', {method:'POST',
                        headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf_token},
                        body:JSON.stringify({state})}); results.push(r.status);
                }
                const repeated = await Promise.all(Array.from({length:8}, async () => {
                    const r = await fetch('/api/state-requests', {method:'POST',
                        headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf_token},
                        body:JSON.stringify({state:'CA'})}); return r.status;
                }));
                return {invalid:results,repeated,
                    counts:(await (await fetch('/api/state-requests/totals')).json()).totals};
            }""")
            assert statuses["invalid"] == [400] * 3 and statuses["repeated"] == [200] * 8
            assert statuses["counts"] == expected_counts
            desktop.reload()
            expect(desktop.get_by_role("button", name="Request consideration")).to_be_enabled()
            state_submit("TX", False)
            record("N", state_requests_accepted=2, duplicate_and_refresh_safe=True,
                   concurrent_duplicates=8, malformed_rejections=3, count_deltas=dict(CA=1, TX=1))

            PHASE = "O responsive accessibility and privacy"
            for page, width in [(desktop, 1280), (mobile, 390)]:
                page.goto(origin + "/gramanna.html#unsubscribe=broken")
                expect(page.locator("#notification-unsubscribe")).to_be_visible()
                expect(page.get_by_role("button", name="Unsubscribe", exact=True)).to_be_disabled()
                expect(page.locator("#unsubscribe-title")).to_be_focused()
                feedback(page, "#notification-unsubscribe-message", error=True)
                assert page.get_by_label("Email address", exact=True).get_attribute("required") is not None
                assert page.locator("#notification-consent").get_attribute("required") is not None
                assert page.locator("#notification-form").get_attribute("aria-labelledby") == "notification-preview-title"
                assert page.viewport_size["width"] == width
            assert not errors
            assert all(urlsplit(url).netloc == urlsplit(origin).netloc and
                       not urlsplit(url).query and not urlsplit(url).fragment for _, url in requests)
            sensitive = [item["email"] for item in lifecycles] + [item["token"] for item in lifecycles]
            sensitive += [item["capability"] for item in lifecycles]
            assert all(not any(value in url for value in sensitive) for _, url in requests)
            for path in ["/api/notifications", "/api/notifications/subscribers", "/api/notifications/totals"]:
                assert contexts[0].request.get(origin + path).status in {404, 405}
            verify("final_accessibility_and_privacy")
            record("O", widths=[1280, 390], accessible_labels_keyboard_focus_live_feedback=True,
                   invalid_link_disabled=True, screenshots=len(screenshots), page_errors=0,
                   external_requests=0, private_values_in_http_urls=0, public_subscriber_listing=False)
            emit(dict(event="complete", lifecycles=lifecycles, state_counts=expected_counts,
                state_cookie=contexts[0].cookies()[0]["value"], chromium=browser.version,
                screenshots=screenshots))
            for context in contexts:
                context.close()
        finally:
            browser.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        emit(dict(event="blocked", phase=PHASE, exception_type=type(error).__name__,
                  assertion_line=traceback.extract_tb(error.__traceback__)[-1].lineno))
        sys.exit(2)
