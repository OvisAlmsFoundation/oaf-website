"""Intercepted Chromium checks using the existing shared Playwright environment."""

import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'https://website.example'


def main():
    files = { '/'+name: (mime,(ROOT/name).read_bytes()) for name,mime in [
        ('gramanna.html','text/html'),('styles.css','text/css'),
        ('assets/state-requests.js','application/javascript'),('assets/notifications.js','application/javascript'),
        ('assets/images/gramanna-logo.png','image/png')] }
    errors,unexpected = [],[]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for width in [1280,390]:
                context = browser.new_context(viewport={'width':width,'height':900})
                submissions,withdrawals,urls = [],[],[]
                held = {}
                mode = {'subscribe':'normal','withdraw':'normal'}

                def intercept(route):
                    request = route.request
                    parts = urlsplit(request.url)
                    urls.append(request.url)
                    assert parts.netloc == 'website.example' and not parts.query and not parts.fragment
                    path = parts.path
                    if path in files:
                        mime,body=files[path]
                        route.fulfill(status=200,content_type=mime,body=body)
                    elif path.endswith('/session'):
                        route.fulfill(status=200,content_type='application/json',
                            headers={'Set-Cookie':'__Host-oaf-state-browser=offline; Path=/; Secure; HttpOnly; SameSite=Lax'},
                            body=json.dumps({'csrf_token':'0'*64}))
                    elif path == '/api/state-requests/totals':
                        route.fulfill(status=200,content_type='application/json',body=json.dumps({'totals':{'CA':0}}))
                    elif path in {'/api/notifications','/api/notifications/unsubscribe'}:
                        data=request.post_data_json
                        assert request.method=='POST' and request.headers['x-csrf-token']=='0'*64
                        withdrawal=path.endswith('unsubscribe')
                        assert len(data['token'])==(129 if withdrawal else 64)
                        key='withdraw' if withdrawal else 'subscribe'
                        (withdrawals if withdrawal else submissions).append(data)
                        if mode[key]=='hold':
                            held[key]=route
                        elif mode[key]=='html':
                            route.fulfill(status=502,content_type='text/html',body='<h1>Unavailable</h1>')
                        else:
                            failure=mode[key]=='failure'
                            route.fulfill(status=503 if failure else 200,content_type='application/json',body=json.dumps({
                                'status':'error' if failure else 'unsubscribed' if withdrawal else 'received',
                                'unsubscribe_token':data['token']+'.'+'0'*64 if not withdrawal else None,
                                'message':'Try again with the same form.' if failure else
                                    'Any active subscription created with this private link has been unsubscribed.' if withdrawal else
                                    'Your submission was processed. New subscriptions are saved; existing active preferences stay unchanged. No email has been sent.'}))
                    else:
                        unexpected.append(request.url)
                        route.abort()

                context.route('**/*',intercept)
                page=context.new_page()
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(ORIGIN+'/gramanna.html')
                button=page.get_by_role('button',name='Subscribe',exact=True)
                email=page.get_by_label('Email address',exact=True)
                consent=page.locator('#notification-consent')
                note=page.locator('#notification-message')
                expect(button).to_be_enabled()
                button.click()
                assert not submissions
                email.fill('invalid')
                button.click()
                assert not submissions
                email.fill('visitor@example.com')
                consent.check()
                button.click()
                expect(note).to_have_text('Choose at least one notification preference.')
                expect(page.locator('#notify-web')).to_be_focused()
                assert not submissions
                page.locator('#notify-state').check()
                state=page.get_by_label('State for availability updates')
                expect(state).to_be_visible()
                assert state.locator('option').count()==51
                button.click()
                assert not submissions
                state.select_option('CA')
                consent.uncheck()
                button.click()
                assert not submissions
                consent.check()
                consent.focus()
                page.keyboard.press('Tab')
                expect(button).to_be_focused()
                mode['subscribe']='hold'
                page.keyboard.press('Enter')
                expect(button).to_be_disabled()
                expect(email).to_be_disabled()
                expect(state).to_be_disabled()
                expect(page.locator('#notify-web')).to_be_disabled()
                page.wait_for_function("document.querySelector('#notification-form').getAttribute('aria-busy') === 'true'")
                page.wait_for_timeout(100)
                assert len(submissions)==1
                original_token=submissions[-1]['token']
                assert submissions[-1]['state']=='CA' and submissions[-1]['consent'] is True
                held.pop('subscribe').fulfill(status=503,content_type='application/json',body=json.dumps({'message':'Try again with the same form.'}))
                expect(note).to_have_text('Try again with the same form.')
                assert note.get_attribute('role')=='alert'
                expect(button).to_be_enabled()
                mode['subscribe']='normal'
                button.click()
                expect(note).to_contain_text('No email has been sent.')
                assert submissions[-1]['token']==original_token
                assert note.get_attribute('role')=='status'
                expect(email).to_have_value('')
                private_link=page.locator('#notification-unsubscribe-link').get_attribute('href')
                private_token=original_token+'.'+'0'*64
                assert private_link=='/gramanna.html#unsubscribe='+private_token
                assert all(original_token not in url for url in urls)
                page.goto(ORIGIN+private_link)
                expect(page.locator('#notification-unsubscribe')).to_be_visible()
                assert '#unsubscribe=' not in page.url and not withdrawals
                expect(page.locator('#unsubscribe-title')).to_be_focused()
                withdraw_button=page.get_by_role('button',name='Unsubscribe',exact=True)
                withdraw_note=page.locator('#notification-unsubscribe-message')
                mode['withdraw']='failure'
                withdraw_button.click()
                expect(withdraw_note).to_have_text('Try again with the same form.')
                assert withdrawals[-1]=={'token':private_token}
                mode['withdraw']='normal'
                withdraw_button.click()
                expect(withdraw_note).to_contain_text('has been unsubscribed.')
                assert len(withdrawals)==2
                page.goto(ORIGIN+'/gramanna.html#unsubscribe=broken')
                expect(withdraw_button).to_be_disabled()
                expect(withdraw_note).to_contain_text('complete private unsubscribe link')
                page.goto(ORIGIN+'/gramanna.html')
                email.fill('visitor@example.com')
                page.locator('#notify-web').check()
                consent.check()
                mode['subscribe']='html'
                button.click()
                expect(note).to_contain_text('We could not confirm this action.')
                expect(button).to_be_enabled()
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                context.close()
            assert not errors,errors
            assert not unexpected,unexpected
        finally:
            browser.close()
    print('PASS: notification Chromium checks at 1280px and 390px; consent, preferences, keyboard, retry, private link and unsubscribe; zero page errors/external requests.')


if __name__=='__main__':
    main()
