"""Offline Chromium UI checks with intercepted API responses; no database.

Run from this repository using the existing shared Playwright interpreter:
  ..\GraManna\.venv\Scripts\python.exe -B tests/state_request_browser_check.py
Every browser request is intercepted; only explicit public source files are read.
"""

import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'https://website.example'


def main():
    files = {
        '/gramanna.html': ('text/html', (ROOT/'gramanna.html').read_bytes()),
        '/styles.css': ('text/css', (ROOT/'styles.css').read_bytes()),
        '/assets/state-requests.js': ('application/javascript', (ROOT/'assets/state-requests.js').read_bytes()),
        '/assets/images/gramanna-logo.png': ('image/png', (ROOT/'assets/images/gramanna-logo.png').read_bytes()),
    }
    errors, unexpected = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for width in [1280, 390]:
                context = browser.new_context(viewport={'width': width, 'height': 900})
                records = set()
                mode = {'submission': 'normal', 'totals': 'hold_initial'}
                calls = []
                held = {}

                def intercept(route):
                    request = route.request
                    path = urlsplit(request.url).path
                    if path in files:
                        content_type, body = files[path]
                        route.fulfill(status=200, content_type=content_type, body=body)
                    elif path == '/api/state-requests/session':
                        route.fulfill(status=200, content_type='application/json',
                                      headers={'Set-Cookie': '__Host-oaf-state-browser=offline-mock; Path=/; Secure; HttpOnly; SameSite=Lax'},
                                      body=json.dumps({'csrf_token': '0'*64}))
                    elif path == '/api/state-requests/totals':
                        if mode['totals'] == 'hold_initial':
                            held['initial_totals'] = route
                            mode['totals'] = 'normal'
                        elif mode['totals'] == 'failure':
                            route.fulfill(status=503, content_type='application/json',
                                          body=json.dumps({'message': 'State totals are temporarily unavailable.'}))
                        else:
                            states = "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
                            route.fulfill(status=200, content_type='application/json',
                                          body=json.dumps({'totals': {s: int(s in records) for s in states}}))
                    elif path == '/api/state-requests':
                        data = request.post_data_json
                        assert set(data) == {'state'}
                        assert request.headers['x-csrf-token'] == '0'*64
                        calls.append(data['state'])
                        if mode['submission'] == 'held':
                            held['submission'] = route
                        elif mode['submission'] == 'failure':
                            route.fulfill(status=503, content_type='application/json', body=json.dumps({
                                'status': 'error', 'message': 'We could not confirm your request. Please try again; a repeat will not add another count.'}))
                        elif mode['submission'] == 'html':
                            route.fulfill(status=502, content_type='text/html', body='<h1>Unavailable</h1>')
                        else:
                            duplicate = data['state'] in records
                            records.add(data['state'])
                            route.fulfill(status=200 if duplicate else 201, content_type='application/json', body=json.dumps({
                                'status': 'duplicate' if duplicate else 'accepted', 'state': data['state'],
                                'message': ('This browser has already requested this state. Your request is counted once.'
                                            if duplicate else 'Your state request has been counted. Thank you.')}))
                    else:
                        unexpected.append(request.url)
                        route.abort()

                context.route('**/*', intercept)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(ORIGIN + '/gramanna.html')
                state = page.get_by_label('Your state', exact=True)
                button = page.get_by_role('button', name='Request consideration')
                note = page.locator('#request-note')
                expect(button).to_be_enabled()
                assert state.locator('option').count() == 51
                # Native required-state validation makes no request.
                button.click()
                assert not calls
                state.select_option('CA')
                state.focus()
                page.keyboard.press('Tab')
                expect(button).to_be_focused()
                page.keyboard.press('Enter')
                expect(note).to_have_text('Your state request has been counted. Thank you.')
                expect(page.locator('#request-total')).to_have_text('1 counted request for California.')
                # A late response from the initial zero-count fetch must not
                # replace the newer committed-total response after submission.
                with page.expect_request_finished(lambda req: urlsplit(req.url).path == '/api/state-requests/totals'):
                    held['initial_totals'].fulfill(status=200, content_type='application/json', body=json.dumps({'totals': {'CA': 0}}))
                page.evaluate('() => new Promise(resolve => requestAnimationFrame(resolve))')
                expect(page.locator('#request-total')).to_have_text('1 counted request for California.')
                button.click()
                expect(note).to_contain_text('already requested')
                state.select_option('NY')
                button.click()
                expect(note).to_contain_text('counted. Thank you.')
                assert records == {'CA', 'NY'}
                mode['submission'] = 'failure'
                state.select_option('TX')
                button.click()
                expect(note).to_contain_text('could not confirm')
                expect(note).to_have_attribute('role', 'alert')
                expect(button).to_be_enabled()
                assert 'TX' not in records
                mode['submission'] = 'normal'
                mode['totals'] = 'failure'
                button.click()
                expect(note).to_contain_text('counted. Thank you.')
                expect(page.locator('#request-total')).to_contain_text('temporarily unavailable')
                mode['submission'] = 'html'
                button.click()
                expect(note).to_have_text('State requests are temporarily unavailable. Please try again.')
                expect(button).to_be_enabled()
                mode['submission'] = 'held'
                state.select_option('WA')
                button.click()
                expect(state).to_be_disabled()
                expect(button).to_be_disabled()
                expect(page.locator('#state-request-form')).to_have_attribute('aria-busy', 'true')
                held['submission'].fulfill(status=201, content_type='application/json', body=json.dumps({
                    'status': 'accepted', 'state': 'WA', 'message': 'Your state request has been counted. Thank you.'}))
                expect(note).to_contain_text('counted. Thank you.')
                expect(state).to_be_enabled()
                expect(button).to_be_enabled()
                assert page.locator('html').evaluate('(node) => node.scrollWidth <= window.innerWidth')
                assert page.get_by_role('button', name='Subscribe — coming later').is_disabled()
                context.close()
                print(f'PASS: {width}px card, 50 states, keyboard, acceptance, duplicate, multiple states, errors and totals failure')
        finally:
            browser.close()
    assert not errors, errors
    assert not unexpected, unexpected
    print('PASS: zero page errors and zero external browser requests; API mocked, PostgreSQL untested')


if __name__ == '__main__':
    main()
