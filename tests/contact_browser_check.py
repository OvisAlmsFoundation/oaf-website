"""Chromium + real Flask request handling, with intercepted HTTP and mocked mail.

Run from the Website root with the existing shared Playwright interpreter.
No listener, database, credentials, external HTTP or SMTP connection is used.
"""

from pathlib import Path
import sys
from urllib.parse import urlsplit
from unittest.mock import Mock

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flask import send_file
from oaf_website.contact_mail import DeliveryUnavailable, RECIPIENT
from oaf_website.local_testing import PUBLIC_FILES
from oaf_website.state_requests import _build_app, BrowserRecognition

ORIGIN = 'https://website.example'
PAGES = ['index.html','about.html','gramanna.html','faq.html','support.html','contact.html']
NAV = ['Home','About','GraManna','FAQ','Contact','Support']
SUCCESS = 'Your message has been accepted for sending. Thank you.'


def main():
    errors, unexpected = [], []
    screenshot_dir = ROOT/'.pytest_cache'/'contact-checkpoint5a'
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for width in [1280,390,320]:
                mode = {'mail':'success','http':'normal'}
                held, posts = [], []
                state, subscriptions = Mock(), Mock()
                state.totals.return_value = {'CA':0}

                def accept(email, message):
                    assert email == 'visitor@example.com'
                    if mode['mail'] == 'failure':
                        raise DeliveryUnavailable('synthetic-private-transport-error')
                sender = Mock(side_effect=accept)
                app = _build_app(state, BrowserRecognition(b'offline-browser-contact-secret-at-least-32'),
                                 ORIGIN, subscription_store=subscriptions, contact_sender=sender)
                for number, name in enumerate(PUBLIC_FILES):
                    app.add_url_rule('/'+name, f'public_{number}', lambda filename=name:send_file(ROOT/filename))
                client = app.test_client(use_cookies=False)
                now = [0]
                app.extensions['contact_guard'].clock = lambda:now[0]

                def respond(route):
                    req = route.request
                    response = client.open(urlsplit(req.url).path, method=req.method, base_url=ORIGIN,
                                           headers=req.all_headers(), data=req.post_data_buffer)
                    route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.get_data())

                def intercept(route):
                    req = route.request
                    parts = urlsplit(req.url)
                    if parts.scheme != 'https' or parts.netloc != 'website.example':
                        unexpected.append(req.url)
                        route.abort()
                        return
                    if parts.path == '/api/contact' and req.method == 'POST':
                        posts.append(req.post_data_json)
                        if mode['http'] == 'hold':
                            held.append(route)
                            return
                        if mode['http'] == 'html':
                            route.fulfill(status=502,content_type='text/html',body='<h1>Unavailable</h1>')
                            return
                        if mode['http'] == 'unsafe-text':
                            route.fulfill(status=503,json={'message':'<img src=x onerror="window.injected=true">'})
                            return
                        if mode['http'] == 'network':
                            route.abort()
                            return
                    if parts.path not in {'/'+name for name in PUBLIC_FILES} | {
                        '/api/contact','/api/contact/session','/api/state-requests/totals'}:
                        unexpected.append(req.url)
                        route.abort()
                        return
                    respond(route)

                context = browser.new_context(viewport={'width':width,'height':900})
                context.route('**/*',intercept)
                page = context.new_page()
                page.on('pageerror',lambda error:errors.append(str(error)))
                for name in PAGES:
                    page.goto(ORIGIN+'/'+name)
                    expect(page.locator('header nav a')).to_have_text(NAV)
                    assert page.locator('.foundation-name a').count() == 0
                    support = page.locator('header nav a').last
                    assert support.get_attribute('class') == 'nav-support'
                    assert support.evaluate("el => getComputedStyle(el).backgroundColor") == 'rgb(49, 94, 80)'
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width,name)
                    if name == 'gramanna.html':
                        assert page.locator('.pilot-state-card').count() == 11
                    if name == 'support.html':
                        assert page.get_by_role('link',name='Donate Through Donorbox').get_attribute('href') == 'https://donorbox.org/foundation-startup-and-operating-expenses-support-fund'
                    page.get_by_role('link',name='Contact',exact=True).click()
                    expect(page).to_have_url(ORIGIN+'/contact.html')
                    expect(page.get_by_role('heading',name='Contact Us',exact=True)).to_be_visible()
                page.goto(ORIGIN+'/index.html')
                expect(page.locator('.how-it-works-heading')).to_contain_text('an overview')
                page.get_by_role('link',name='Contact Us',exact=True).click()
                expect(page).to_have_url(ORIGIN+'/contact.html')

                email = page.get_by_label('Email Address',exact=True)
                message = page.get_by_label('Message',exact=True)
                button = page.get_by_role('button',name='Send Message',exact=True)
                note = page.locator('#contact-feedback')
                expect(email).to_have_attribute('type','email')
                expect(email).to_have_attribute('required','')
                expect(message).to_have_attribute('required','')
                expect(message).to_have_attribute('aria-describedby','contact-limit')
                expect(page.locator('#contact-limit')).to_contain_text('200 words')
                assert RECIPIENT not in page.content()
                page.screenshot(path=str(screenshot_dir/f'contact-{width}.png'),full_page=True)
                button.click()
                assert not posts
                email.fill('invalid')
                message.fill('A question about the Foundation.')
                button.click()
                assert not posts
                email.fill('visitor@example.com')
                message.fill('word '*201)
                button.click()
                expect(note).to_have_text('Keep your message within 200 words.')
                expect(message).to_be_focused()
                assert not posts

                def direct(data, extra_headers=None):
                    return page.evaluate('''async ({data,extra}) => {
                      const {csrf_token} = await (await fetch('/api/contact/session')).json();
                      const response = await fetch('/api/contact',{method:'POST',
                        headers:{'Content-Type':'application/json','X-CSRF-Token':csrf_token,...extra},
                        body:JSON.stringify(data)});
                      return {status:response.status, data:await response.json()};
                    }''', {'data':data,'extra':extra_headers or {}})
                assert direct({'email':'visitor@example.com','message':'word '*201})['status'] == 400
                assert sender.call_count == 0
                assert len(posts) == 1
                message.fill('A question about the Foundation.')
                email.focus()
                page.keyboard.press('Tab')
                expect(message).to_be_focused()
                page.keyboard.press('Tab')
                expect(button).to_be_focused()
                assert button.evaluate("el => getComputedStyle(el).outlineStyle") != 'none'
                mode['http'] = 'hold'
                page.keyboard.press('Enter')
                expect(button).to_be_disabled()
                expect(email).to_be_disabled()
                expect(message).to_be_disabled()
                expect(note).to_have_text('Sending your message...')
                assert sender.call_count == 0
                page.evaluate("document.querySelector('#contact-form').requestSubmit()")
                page.wait_for_timeout(100)
                assert len(posts) == 2 and len(held) == 1
                respond(held.pop())
                mode['http'] = 'normal'
                expect(note).to_have_text(SUCCESS)
                expect(note).to_be_focused()
                expect(email).to_have_value('')
                expect(message).to_have_value('')
                assert note.get_attribute('role') == 'status'
                assert sender.call_count == 1

                # Reload/repeat uses real browser cookies and backend suppression.
                page.reload()
                email.fill('visitor@example.com')
                message.fill('A question about the Foundation.')
                button.click()
                expect(note).to_have_text(SUCCESS)
                assert sender.call_count == 1
                mode['mail'] = 'failure'
                email.fill('visitor@example.com')
                message.fill('A different question.')
                button.click()
                expect(note).to_have_text('We could not send your message. Please try again later.')
                expect(note).to_be_focused()
                expect(message).to_have_value('A different question.')
                assert note.get_attribute('role') == 'alert'
                assert sender.call_count == 2
                mode['mail'] = 'success'
                button.click()
                expect(note).to_have_text(SUCCESS)
                assert sender.call_count == 3
                assert direct({'email':'visitor@example.com','message':'Too fast.'})['status'] == 429
                now[0] += 601
                assert direct({'email':'visitor@example.com','message':'Hello','recipient':'attacker@example.com'})['status'] == 400
                assert direct({'email':'visitor@example.com','message':'Hello'}, {'X-CSRF-Token':'bad'})['status'] == 403

                for http_mode in ['unsafe-text','html','network']:
                    mode['http'] = http_mode
                    email.fill('visitor@example.com')
                    message.fill('Please keep this message after failure.')
                    button.click()
                    if http_mode == 'unsafe-text':
                        expect(note).to_have_text('<img src=x onerror="window.injected=true">')
                        assert note.locator('img').count() == 0
                        assert page.evaluate('window.injected === undefined')
                    else:
                        expect(note).to_contain_text('We could not confirm whether your message was accepted.')
                    expect(button).to_be_enabled()
                    expect(message).to_have_value('Please keep this message after failure.')
                    assert sender.call_count == 3
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not state.submit.called and not subscriptions.mock_calls
                context.close()
            assert not errors, errors
            assert not unexpected, unexpected
        finally:
            browser.close()
    print('PASS: Contact Chromium + Flask checks at 1280, 390 and 320px; all six pages, both entry points, keyboard/focus, validation, real CSRF/cookies, limits, duplicates, mocked mail success/failure, safe errors, service isolation and no overflow. Zero page errors or external HTTP requests; no real SMTP, credentials or database access.')


if __name__ == '__main__':
    main()
