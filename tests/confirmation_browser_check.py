"""R41-F1 intercepted Chromium checks; synthetic capabilities, no live services."""
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'https://website.example'
TOKEN = 'a' * 64
UNAVAILABLE = 'This link is unavailable. Request a new confirmation link.'
GENERIC = "If confirmation is needed and permitted, we'll email a link."


def main():
    evidence_dir = ROOT / '.pytest_cache/notification-management-v2/confirmation-browser'
    evidence_dir.mkdir(parents=True, exist_ok=True)
    files = {'/' + name: (mime, (ROOT / name).read_bytes()) for name, mime in [
        ('confirm-email.html', 'text/html'), ('assets/email-confirmation.js', 'application/javascript'),
        ('gramanna.html', 'text/html'), ('styles.css', 'text/css'),
        ('assets/notifications.js', 'application/javascript'),
        ('assets/state-requests.js', 'application/javascript'),
        ('assets/images/gramanna-logo.png', 'image/png')]}
    errors, unexpected, console_errors = [], [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for width in (1280, 390):
                print(f'START: R41 intercepted Chromium {width}px', flush=True)
                context = browser.new_context(viewport={'width': width, 'height': 900}, reduced_motion='reduce')
                context.add_init_script("""(() => {
                  window.fragmentEvidence = [];
                  const original = window.fetch;
                  window.fetch = (...args) => {
                    window.fragmentEvidence.push({path: args[0], hash: location.hash});
                    return original(...args);
                  };
                })();""")
                calls, held, urls = [], {}, []
                mode = {'enabled': True, 'session': 'normal', 'confirm': 'normal', 'request': 'normal'}

                def reply(route, http_status=200, **fields):
                    route.fulfill(status=http_status, content_type='application/json', body=json.dumps(fields))

                def intercept(route):
                    request = route.request
                    parts = urlsplit(request.url)
                    urls.append(request.url)
                    if parts.netloc != 'website.example':
                        unexpected.append(request.url)
                        route.abort()
                        return
                    assert not parts.query and not parts.fragment
                    path = parts.path
                    if path in files:
                        mime, body = files[path]
                        route.fulfill(status=200, content_type=mime, body=body)
                    elif path == '/api/notifications/session':
                        if mode['session'] == 'failure': reply(route, 503, message='Private diagnostic must not appear')
                        elif mode['session'] == 'malformed': reply(route, csrf_token='bad', confirmation_enabled=True)
                        elif mode['session'] == 'missing_flag': reply(route, csrf_token='0' * 64)
                        else: reply(route, csrf_token='0' * 64, confirmation_enabled=mode['enabled'])
                    elif path == '/api/state-requests/totals':
                        reply(route, totals={'CA': 0})
                    elif path in {'/api/notifications/confirm', '/api/notifications/confirmation', '/api/notifications/unsubscribe'}:
                        assert request.method == 'POST' and request.headers['x-csrf-token'] == '0' * 64
                        data = request.post_data_json
                        action = 'request' if path.endswith('/confirmation') else 'confirm' if path.endswith('/confirm') else 'withdraw'
                        assert set(data) == ({'email'} if action == 'request' else {'token'})
                        if action == 'confirm':
                            assert data == {'token': TOKEN} and request.headers.get('referer') is None
                        calls.append((action, data))
                        outcome = mode.get(action, 'normal')
                        if outcome == 'hold': held[action] = route
                        elif outcome == 'network': route.abort('failed')
                        elif outcome == 'html': route.fulfill(status=502, content_type='text/html', body='<h1>Private diagnostic</h1>')
                        elif outcome in {'invalid', 'expired'}: reply(route, 400, status='error', message=UNAVAILABLE)
                        elif outcome == 'csrf': reply(route, 403, status='error', message='Private diagnostic must not appear')
                        elif outcome == 'server': reply(route, 503, status='error', message='Private diagnostic must not appear')
                        elif outcome == 'wrong_success': reply(route, status='received', message='Private diagnostic must not appear')
                        elif outcome == 'null': route.fulfill(status=200, content_type='application/json', body='null')
                        elif outcome == 'malformed_repeat': reply(route, status='confirmed', already_confirmed='true')
                        elif outcome == 'legacy_success': reply(route, status='confirmed', message='Your email is confirmed.')
                        elif outcome == 'already': reply(route, status='confirmed', already_confirmed=True,
                                                       message='Your email is already confirmed.')
                        else: reply(route, status='confirmed' if action == 'confirm' else 'received',
                                    already_confirmed=False,
                                    message=GENERIC if action == 'request' else 'Your email is confirmed.')
                    else:
                        unexpected.append(request.url)
                        route.abort()

                context.route('**/*', intercept)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                # Deliberately injected HTTP/network failures produce expected Chromium diagnostics.
                page.on('console', lambda event: console_errors.append(event.text) if event.type == 'error' and
                        not event.text.startswith('Failed to load resource:') else None)

                def navigate(fragment='#confirm-email=' + TOKEN, path='/confirm-email.html'):
                    page.goto('about:blank')
                    page.goto(ORIGIN + path + fragment)

                def private_and_responsive():
                    assert page.url == ORIGIN + '/confirm-email.html'
                    rows = page.evaluate('window.fragmentEvidence')
                    assert all(row['hash'] == '' for row in rows), rows
                    assert TOKEN not in page.content()
                    assert page.evaluate('localStorage.length === 0 && sessionStorage.length === 0')
                    assert all(TOKEN not in url for url in urls)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    bounds = page.locator('#email-confirmation').bounding_box()
                    assert bounds and bounds['x'] >= 12 and bounds['x'] + bounds['width'] <= width - 12

                navigate()
                button = page.get_by_role('button', name='Confirm email', exact=True)
                raw_button = page.locator('#email-confirmation-button')
                title = page.locator('#email-confirmation-title')
                status = page.locator('#email-confirmation-status')
                error = page.locator('#email-confirmation-error')
                help_link = page.get_by_role('link', name='Request a new confirmation link', exact=True)
                card = page.locator('#email-confirmation')
                expect(button).to_be_enabled()
                expect(title).to_be_focused()
                assert title.evaluate("element => getComputedStyle(element).position") == 'absolute'
                assert title.bounding_box()['width'] == 1  # Owner-approved accessible hidden landing heading.
                assert not calls and page.get_by_role('button').count() == 1
                assert page.get_by_role('form').count() == 0
                assert page.evaluate("getComputedStyle(document.querySelector('.button')).transitionDuration") == '0s'
                private_and_responsive()
                page.screenshot(path=str(evidence_dir / f'landing-{width}.png'), full_page=True)
                page.keyboard.press('Tab')
                expect(button).to_be_focused()
                mode['confirm'] = 'hold'
                page.keyboard.press('Enter')
                expect(card).to_have_attribute('aria-busy', 'true')
                expect(status).to_have_text('Confirming your email…')
                expect(raw_button).to_be_disabled()
                raw_button.dispatch_event('click')
                page.wait_for_timeout(50)
                assert calls == [('confirm', {'token': TOKEN})]
                reply(held.pop('confirm'), status='confirmed', already_confirmed=False, message='Your email is confirmed.')
                expect(title).to_have_text('Your email is confirmed!')
                expect(title).to_be_focused()
                expect(status).to_have_text('Email verification complete')
                expect(page.locator('#email-confirmation-check')).to_be_visible()
                expect(raw_button).to_be_hidden()
                expect(help_link).to_be_hidden()
                expect(error).to_be_empty()
                expect(card).to_have_attribute('aria-busy', 'false')
                assert page.get_by_role('button').count() == 0
                raw_button.dispatch_event('click')
                assert len(calls) == 1
                private_and_responsive()
                page.screenshot(path=str(evidence_dir / f'success-{width}.png'), full_page=True)
                print(f'PASS: {width}px landing, keyboard, no automatic POST, privacy, busy/duplicate guard and same-page success', flush=True)

                mode['confirm'] = 'already'
                count = len(calls)
                navigate()  # Reopen the same original link in a fresh document, without stored state.
                expect(button).to_be_enabled()
                assert len(calls) == count
                button.click()
                expect(title).to_have_text('Your email is already confirmed!')
                expect(title).to_be_focused()
                expect(page.locator('#email-confirmation-explanation')).to_have_text(
                    'Your email address has already been verified. No further action is needed.')
                expect(status).to_have_text('Email verification complete')
                expect(page.locator('#email-confirmation-check')).to_be_visible()
                expect(raw_button).to_be_hidden()
                expect(raw_button).to_be_disabled()
                expect(help_link).to_be_hidden()
                expect(error).to_be_empty()
                assert page.get_by_role('button').count() == 0
                raw_button.dispatch_event('click')
                page.wait_for_timeout(100)
                assert len(calls) == count + 1
                private_and_responsive()
                page.screenshot(path=str(evidence_dir / f'already-confirmed-{width}.png'), full_page=True)
                print(f'PASS: {width}px same-link repeat follows backend result, terminal wording, focus and no submission loop', flush=True)

                mode['confirm'] = 'legacy_success'
                count = len(calls)
                navigate(path='/gramanna.html')
                expect(button).to_be_enabled()
                assert len(calls) == count
                private_and_responsive()
                button.click()
                expect(title).to_have_text('Your email is confirmed!')
                assert calls[-1] == ('confirm', {'token': TOKEN})

                for fragment in ('', '#confirm-email=broken', '#confirm-email=' + 'A' * 64,
                                 '#unsubscribe=' + 'b' * 64 + '.' + 'c' * 64):
                    count = len(calls)
                    navigate(fragment)
                    expect(error).to_have_text(UNAVAILABLE)
                    expect(raw_button).to_be_hidden()
                    expect(help_link).to_be_visible()
                    assert len(calls) == count and page.url == ORIGIN + '/confirm-email.html'

                for outcome in ('invalid', 'expired'):
                    mode['confirm'] = outcome
                    navigate()
                    expect(button).to_be_enabled()
                    button.click()
                    expect(error).to_have_text(UNAVAILABLE)
                    expect(title).to_be_focused()
                    expect(raw_button).to_be_hidden()
                    expect(help_link).to_be_visible()
                    private_and_responsive()
                page.screenshot(path=str(evidence_dir / f'unavailable-{width}.png'), full_page=True)

                for outcome in ('csrf', 'html', 'network', 'server', 'wrong_success', 'null', 'malformed_repeat'):
                    mode['confirm'] = outcome
                    navigate()
                    expect(button).to_be_enabled()
                    button.click()
                    expect(error).to_contain_text('Enable cookies' if outcome == 'csrf' else 'We could not confirm your email.')
                    expect(button).to_be_enabled()
                    expect(button).to_be_focused()
                    expect(card).to_have_attribute('aria-busy', 'false')
                    assert 'Private diagnostic' not in page.content()
                    mode['confirm'] = 'normal'
                    button.click()
                    expect(title).to_have_text('Your email is confirmed!')

                for outcome in ('failure', 'malformed', 'missing_flag'):
                    mode['session'] = outcome
                    navigate()
                    expect(error).to_contain_text('We could not prepare confirmation.')
                    expect(button).to_be_enabled()
                    mode['session'] = 'normal'
                    button.click()
                    expect(title).to_have_text('Your email is confirmed!')

                mode['enabled'] = False
                count = len(calls)
                navigate()
                expect(error).to_contain_text('Email confirmation is currently unavailable.')
                expect(button).to_be_disabled()
                raw_button.dispatch_event('click')
                assert len(calls) == count
                private_and_responsive()
                print(f'PASS: {width}px legacy, invalid/expired, API/network/session failures, retries and default OFF', flush=True)

                mode['enabled'] = True
                navigate('', '/gramanna.html')
                request_email = page.get_by_label('Email address for confirmation', exact=True)
                request_button = page.get_by_role('button', name='Request or resend confirmation', exact=True)
                request_note = page.locator('#notification-confirmation-message')
                expect(request_button).to_be_enabled()
                request_email.fill('visitor@example.invalid')
                request_email.focus()
                page.keyboard.press('Tab')
                expect(request_button).to_be_focused()
                mode['request'] = 'hold'
                page.keyboard.press('Enter')
                expect(request_button).to_be_disabled()
                expect(request_email).to_be_disabled()
                expect(page.get_by_role('button', name='Subscribe', exact=True)).to_be_disabled()
                page.wait_for_timeout(50)
                assert calls[-1] == ('request', {'email': 'visitor@example.invalid'})
                reply(held.pop('request'), status='received', message=GENERIC)
                expect(request_note).to_have_text(GENERIC)
                mode['request'] = 'html'
                request_button.click()
                expect(request_note).to_contain_text('We could not confirm this action.')
                expect(request_button).to_be_enabled()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                context.close()
                print(f'PASS: {width}px preserved request/resend and error behavior', flush=True)
            assert not errors, errors
            assert not console_errors, console_errors
            assert not unexpected, unexpected
        finally:
            browser.close()
    print('PASS: R41 Chromium 1280px and 390px; zero page errors, unexpected console errors or external requests.', flush=True)


if __name__ == '__main__':
    main()
