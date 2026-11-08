"""Chromium + real Flask request handling, with intercepted HTTP and mocked mail.

Run from the Website root with the existing shared Playwright interpreter.
No listener, database, credentials, external HTTP or SMTP connection is used.
"""

from pathlib import Path
import argparse
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
SUCCESS = 'Message Sent Successfully'
SUCCESS_BODY = "Thank you for contacting Ovis Alms Foundation. We've received your message and will respond as soon as possible."


def expect_background(link, color, *, painted=False):
    expect(link).to_have_css('background-color', 'rgba(0, 0, 0, 0)' if painted else color)
    if painted:
        assert link.evaluate("n => getComputedStyle(n, '::before').backgroundColor") == color


def check_navigation_presentation(page, filename, coarse):
    links = page.locator('.site-header nav a')
    minimum = 44 if coarse else 36
    assert page.evaluate("matchMedia('(pointer: coarse)').matches") == coarse
    mobile = page.viewport_size['width'] <= 900
    narrow = page.viewport_size['width'] <= 550
    if mobile:
        minimum = (32 if coarse else 26) if narrow else (34 if coarse else 28)
    width = page.viewport_size['width']
    gap = ('0.5px' if width <= 300 else '4px' if width <= 350 else '6px') if narrow else '18px' if mobile else '28px'
    column_gap = ('0.5px' if width <= 300 else '6.25px' if width <= 350 else '8.625px') if narrow else '12.96px' if mobile else '20.16px'
    expect(page.locator('.site-header')).to_have_css('flex-direction', 'column' if mobile else 'row')
    expect(page.locator('.site-header nav')).to_have_css('column-gap', column_gap)
    expect(page.locator('.site-header nav')).to_have_css('row-gap', gap)
    expect(page.locator('.site-header nav')).to_have_css('flex-wrap', 'wrap' if mobile else 'nowrap')
    assert links.evaluate_all("nodes => nodes.map(n => n.getAttribute('href'))") == [
        'index.html', 'about.html', 'gramanna.html', 'faq.html', 'contact.html', 'support.html',
    ]
    current = page.locator('.site-header nav a[aria-current="page"]')
    expect(current).to_have_count(1)
    expect(current).to_have_attribute('href', filename)
    boxes = links.evaluate_all('nodes => nodes.map(n => n.getBoundingClientRect().toJSON())')
    for index, box in enumerate(boxes):
        assert abs(box['height'] - minimum) < 0.01
        assert box['width'] >= 24
        assert box['height'] >= 24
        if mobile and index:
            assert abs(box['top'] + box['height'] / 2 - boxes[0]['top'] - boxes[0]['height'] / 2) < .1
            # All six mobile regions meet, including Contact and Support.
            expected_gap = 0 if narrow else float(column_gap[:-2])
            assert abs(box['left'] - boxes[index - 1]['right'] - expected_gap) < .01
        for other in boxes[index + 1:]:
            assert (box['right'] <= other['left'] or other['right'] <= box['left']
                    or box['bottom'] <= other['top'] or other['bottom'] <= box['top']), (box, other)
    for link in links.all():
        support = link.get_attribute('class') == 'nav-support'
        active = link.get_attribute('aria-current') == 'page'
        expect(link).to_have_css('min-height', f'{minimum}px')
        padding = ('2px 6px' if support else '2px 0px') if mobile else '6px 14px' if support else '6px 8px'
        if narrow:
            inset = float(column_gap[:-2]) / 2
            padding = f'{1 if support else 2}px {inset:g}px'
        if mobile and not narrow and not support:
            padding = '1px 0px'
        expect(link).to_have_css('padding', padding)
        expect(link).to_have_css('border-radius', '3px' if support else '6px')
        margin = '0px' if mobile else '-6px 0px' if support else '-6px -8px'
        if narrow:
            margin = f'0px {-inset:g}px {3.21 if coarse else 2.61}px' if support else f'0px {-inset:g}px'
        expect(link).to_have_css('margin', margin)
        ratio = link.evaluate('n => parseFloat(getComputedStyle(n).lineHeight) / parseFloat(getComputedStyle(n).fontSize)')
        assert abs(ratio - 1.5) < 0.001
        link.hover()
        background = ('rgba(0, 0, 0, 0)' if active else
                      'rgb(116, 37, 116)' if support else 'rgb(239, 245, 240)')
        expect_background(link, background)
        if support and not active:
            # The approved shared CTA paints its gradient on the link itself.
            gradient = link.evaluate('''n => {
                const probe = document.createElement('span');
                probe.style.backgroundImage = 'linear-gradient(to right, color-mix(in srgb, var(--brand-aubergine) 80%, white), var(--brand-aubergine))';
                n.append(probe);
                const value = getComputedStyle(probe).backgroundImage;
                probe.remove();
                return value;
            }''')
            expect(link).to_have_css('background-image', gradient)
        expect(link).to_have_css('color', 'rgb(29, 95, 49)' if active else 'rgb(255, 255, 255)' if support else 'rgb(34, 34, 34)')
        expect(link).to_have_css('font-weight', '700' if active else '400')
        page.mouse.down()
        expect_background(link, 'rgb(18, 59, 30)' if support and not active else background)
        if support and not active:
            expect(link).to_have_css('background-image', 'none')
        page.mouse.move(0, 0)
        page.mouse.up()
    links.first.focus()
    page.keyboard.press('Tab')
    page.keyboard.press('Shift+Tab')
    for index, link in enumerate(links.all()):
        expect(link).to_be_focused()
        expect(link).to_have_css('outline-style', 'solid')
        expect(link).to_have_css('outline-width', '2px')
        expect(link).to_have_css('outline-color', 'rgb(29, 95, 49)')
        if index + 1 < links.count():
            page.keyboard.press('Tab')
    page.locator(':focus').evaluate('n => n.blur()')


def main(navigation_only=False, artifacts=None):
    errors, unexpected = [], []
    screenshot_dir = Path(artifacts) if artifacts else ROOT/'.pytest_cache'/('navbar-dimensions-20261102' if navigation_only else 'contact-checkpoint5a')
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            scenarios = ([(width, False) for width in [1280, 901, 900, 768, 390, 320]] +
                         [(width, True) for width in [1280, 390, 320]]) if navigation_only else [(1280, False), (390, False), (320, False)]
            for width, coarse in scenarios:
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
                        '/api/contact','/api/contact/session','/api/state-requests/totals',
                        '/api/notifications/session'}:
                        unexpected.append(req.url)
                        route.abort()
                        return
                    respond(route)

                context = browser.new_context(viewport={'width':width,'height':900}, has_touch=coarse)
                context.route('**/*',intercept)
                page = context.new_page()
                page.on('pageerror',lambda error:errors.append(str(error)))
                for name in PAGES:
                    page.mouse.move(0, 0)
                    page.goto(ORIGIN+'/'+name)
                    expect(page.locator('header nav a')).to_have_text(NAV)
                    assert page.locator('.foundation-name a').count() == 0
                    support = page.locator('header nav a').last
                    assert support.get_attribute('class') == 'nav-support'
                    support_background = 'rgba(0, 0, 0, 0)' if name == 'support.html' else 'rgb(29, 95, 49)'
                    expect_background(support, support_background)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width,name)
                    check_navigation_presentation(page, name, coarse)
                    if name == 'gramanna.html':
                        assert page.locator('.pilot-state-card').count() == 11
                    if name == 'support.html':
                        assert page.get_by_role('link',name='Donate Through Donorbox').get_attribute('href') == 'https://donorbox.org/foundation-startup-and-operating-expenses-support-fund'
                    page.get_by_role('link',name='Contact',exact=True).click()
                    expect(page).to_have_url(ORIGIN+'/contact.html')
                    expect(page.get_by_role('heading',name='Contact Us',exact=True)).to_be_visible()
                if navigation_only:
                    for target in ['index.html', 'about.html', 'gramanna.html', 'faq.html', 'contact.html', 'support.html']:
                        page.locator(f'.site-header nav a[href="{target}"]').click()
                        expect(page).to_have_url(ORIGIN + '/' + target)
                        expect(page.locator('.site-header nav a[aria-current="page"]')).to_have_attribute('href', target)
                    page.mouse.move(0, 0)
                    page.screenshot(path=str(screenshot_dir / f'navigation-{width}-{"coarse" if coarse else "fine"}.png'))
                    assert not sender.called and not state.submit.called and not subscriptions.mock_calls
                    context.close()
                    print(f'PASS: Navigation {width}px, {"coarse" if coarse else "fine"} pointer; dimensions, all six pages/routes, hover/current/pressed states, focus and overflow.', flush=True)
                    continue
                page.goto(ORIGIN+'/index.html')
                expect(page.locator('.how-it-works-heading')).to_contain_text('an overview')
                page.get_by_role('link',name='Contact Us',exact=True).click()
                expect(page).to_have_url(ORIGIN+'/contact.html')

                email = page.get_by_label('Email Address',exact=True)
                message = page.get_by_label('Message',exact=True)
                button = page.get_by_role('button',name='Send Message',exact=True)
                note = page.locator('#contact-feedback')
                dialog = page.get_by_role('dialog', name=SUCCESS)
                close = page.get_by_role('button', name='Close', exact=True)
                expect(dialog).to_be_hidden()
                navigation_entries = page.evaluate("performance.getEntriesByType('navigation').length")
                navigations = []
                page.on('framenavigated', lambda frame: navigations.append(frame.url) if frame == page.main_frame else None)

                def success_modal(dismiss='Escape'):
                    expect(dialog).to_be_visible()
                    expect(dialog).to_contain_text(SUCCESS_BODY)
                    assert not navigations, navigations
                    expect(close).to_be_focused()
                    assert page.evaluate("performance.getEntriesByType('navigation').length") == navigation_entries
                    assert page.locator('#contact-success').evaluate("n => n.matches(':modal')")
                    expect(note).to_have_text('')
                    # The native modal keeps Tab and Shift+Tab inside its one control.
                    page.keyboard.press('Tab')
                    page.keyboard.press('Tab')
                    expect(close).to_be_focused()
                    page.keyboard.press('Shift+Tab')
                    page.keyboard.press('Shift+Tab')
                    expect(close).to_be_focused()
                    page.screenshot(path=str(screenshot_dir / f'contact-success-{width}.png'))
                    if dismiss == 'Escape':
                        page.keyboard.press('Escape')
                    else:
                        close.click()
                    expect(dialog).to_be_hidden()
                    expect(button).to_be_focused()
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
                expect(dialog).to_be_hidden()
                assert sender.call_count == 0
                page.evaluate("document.querySelector('#contact-form').requestSubmit()")
                page.wait_for_timeout(100)
                assert len(posts) == 2 and len(held) == 1
                respond(held.pop())
                mode['http'] = 'normal'
                success_modal()
                expect(email).to_have_value('')
                expect(message).to_have_value('')
                assert note.get_attribute('role') == 'status'
                assert sender.call_count == 1

                # Reload/repeat uses real browser cookies and backend suppression.
                page.reload()
                navigations.clear()
                email.fill('visitor@example.com')
                message.fill('A question about the Foundation.')
                button.click()
                success_modal('Close')
                assert sender.call_count == 1
                mode['mail'] = 'failure'
                email.fill('visitor@example.com')
                message.fill('A different question.')
                button.click()
                expect(note).to_have_text('We could not send your message. Please try again later.')
                expect(dialog).to_be_hidden()
                expect(note).to_be_focused()
                expect(message).to_have_value('A different question.')
                assert note.get_attribute('role') == 'alert'
                assert sender.call_count == 2
                mode['mail'] = 'success'
                button.click()
                success_modal('Close')
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
                    expect(dialog).to_be_hidden()
                    expect(message).to_have_value('Please keep this message after failure.')
                    assert sender.call_count == 3
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not state.submit.called and not subscriptions.mock_calls
                context.close()
            assert not errors, errors
            assert not unexpected, unexpected
        finally:
            browser.close()
    if navigation_only:
        print('PASS: Focused navigation Chromium checks; zero page errors or external requests; no SMTP, credentials or database access. Owner visual acceptance pending.')
    else:
        print('PASS: Contact Chromium + Flask checks at 1280, 390 and 320px; all six pages, both entry points, keyboard/focus, validation, real CSRF/cookies, limits, duplicates, mocked mail success/failure, safe errors, service isolation and no overflow. Zero page errors or external HTTP requests; no real SMTP, credentials or database access.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--navigation-only', action='store_true')
    parser.add_argument('--artifacts', type=Path)
    args = parser.parse_args()
    main(navigation_only=args.navigation_only, artifacts=args.artifacts)
