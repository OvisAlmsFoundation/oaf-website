"""Intercepted V2 Chromium checks: no server, provider, database or real mailbox."""
import json
from datetime import datetime
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
ORIGIN='https://website.example'
TOKEN='m2.testing.'+'a'*64+'.0.1792368000.1794960000.'+'b'*64+'.'+'c'*64
LEGACY='d'*64+'.'+'e'*64


def main():
    evidence=ROOT/'.pytest_cache/r47-step3-consolidated-20261020/browser'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    evidence.mkdir(parents=True,exist_ok=False)
    files={'/'+name:(mime,(ROOT/name).read_bytes()) for name,mime in (
        ('manage-notifications.html','text/html'),('assets/notification-management.js','application/javascript'),
        ('styles.css','text/css'),('gramanna.html','text/html'),('assets/email-confirmation.js','application/javascript'),
        ('assets/notifications.js','application/javascript'),('assets/state-requests.js','application/javascript'),
        ('assets/images/gramanna-logo.png','image/png'))}
    errors,unexpected,console_errors=[],[],[]
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        try:
            for width in (1280,390):
                print(f'START V2 intercepted browser {width}px',flush=True)
                context=browser.new_context(viewport={'width':width,'height':900},reduced_motion='reduce')
                context.add_init_script("""window.fetchEvidence=[]; const oldFetch=window.fetch;
                    window.fetch=(...args)=>{window.fetchEvidence.push({hash:location.hash,path:args[0]});return oldFetch(...args);};""")
                mode={'session':'normal','view':'normal','save':'normal','enabled':True}
                writes,reads,recoveries,held=[],[],[],{}
                receipts,acknowledgments={},[]
                current={'revision':0,'preferences':dict(web_launch=True,android_launch=False,ios_launch=True,state='CA')}
                results={}
                authority={'clock':0,'expires':0,'active':False}
                cookie_name='__Host-oaf-notification-management'
                cookie_value='synthetic-browser-management-session'

                def reply(route,http=200,headers=None,**data):
                    route.fulfill(status=http,content_type='application/json',body=json.dumps(data),headers=headers)

                def intercept(route):
                    request=route.request; parts=urlsplit(request.url)
                    if parts.netloc!='website.example' or parts.query or parts.fragment:
                        unexpected.append(request.url); route.abort(); return
                    if parts.path in files:
                        mime,body=files[parts.path]; route.fulfill(status=200,content_type=mime,body=body); return
                    if parts.path=='/api/notifications/session':
                        if mode['session']=='failure': reply(route,503,message='Private diagnostic')
                        else: reply(route,csrf_token='0'*64,management_enabled=mode['enabled'])
                        return
                    if parts.path=='/api/state-requests/totals': reply(route,totals={}); return
                    assert request.method=='POST' and request.headers['x-csrf-token']=='0'*64
                    assert request.headers.get('referer') is None
                    data=request.post_data_json
                    if parts.path=='/api/notifications/manage':
                        reads.append(data); assert set(data) in ({'token'},set())
                        if mode['view']=='unavailable': reply(route,400,message='Private diagnostic')
                        elif mode['view']=='server': reply(route,503,message='Private diagnostic')
                        else:
                            cookies=SimpleCookie(request.headers.get('cookie',''))
                            if data.get('token')==TOKEN:
                                authority.update(active=True,expires=authority['clock']+1800)
                                reply(route,headers={'Set-Cookie':cookie_name+'='+cookie_value+
                                    '; Max-Age=1800; Path=/; Secure; HttpOnly; SameSite=Lax'},status='preferences',**current)
                            elif not data and authority['active'] and authority['clock']<authority['expires'] and \
                                    cookie_name in cookies and cookies[cookie_name].value==cookie_value:
                                reply(route,status='preferences',**current)
                            else: reply(route,400,message='Private diagnostic')
                    elif parts.path=='/api/notifications/manage/withdrawal-receipt':
                        assert 'token' not in data and authority['active']
                        receipt='synthetic-ack-only-'+data['action']
                        receipts[receipt]=dict(body=data,expires=min(authority['clock']+600,authority['expires']))
                        reply(route,receipt=receipt)
                    elif parts.path=='/api/notifications/manage/withdrawal-ack':
                        acknowledgments.append(data)
                        receipt=receipts.get(data['receipt'])
                        original={k:v for k,v in data.items() if k!='receipt'}
                        if not receipt or receipt['body']!=original or authority['clock']>=receipt['expires'] or \
                                results.get(data['action'],{}).get('status')!='unsubscribed':
                            reply(route,400,message='Private diagnostic')
                        else:
                            reply(route,headers={'Set-Cookie':cookie_name+'=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax'},
                                  **results[data['action']])
                    elif parts.path=='/api/notifications/manage/save':
                        writes.append(data); assert 'token' not in data
                        if mode['save']=='hold': held['save']=route; return
                        if mode['save']=='csrf': reply(route,403,message='Private diagnostic'); return
                        if mode['save']=='conflict': reply(route,409,message='Private diagnostic'); return
                        if mode['save']=='network': route.abort('failed'); return
                        if mode['save']=='html': route.fulfill(status=502,content_type='text/html',body='Private diagnostic'); return
                        if mode['save']=='server': reply(route,503,message='Private diagnostic'); return
                        preferences=data.get('preferences')
                        key=data['action']
                        if key not in results:
                            current['revision']=data['revision']+1
                            if preferences and any(preferences[n] for n in ('web_launch','android_launch','ios_launch','state')):
                                current['preferences']={k:v for k,v in preferences.items() if k!='consent'}
                                results[key]=dict(status='saved',revision=current['revision'])
                            else:
                                results[key]=dict(status='unsubscribed',revision=current['revision'])
                                authority['active']=False
                        if mode['save']=='lost_commit': reply(route,503,message='Private diagnostic')
                        elif mode['save'] in {'lost_body_cookie_retained','lost_body_cookie_deleted'}:
                            assert results[key]['status']=='unsubscribed'
                            headers={'Set-Cookie':cookie_name+'=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax'} \
                                if mode['save']=='lost_body_cookie_deleted' else None
                            # The browser applies headers, then receives no usable body.
                            route.fulfill(status=200,content_type='application/json',body='',headers=headers)
                        else:
                            headers={'Set-Cookie':cookie_name+'=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax'} \
                                if results[key]['status']=='unsubscribed' else None
                            reply(route,headers=headers,**results[key])
                    elif parts.path=='/api/notifications/manage/recovery':
                        recoveries.append(data); assert set(data)=={'email'}
                        reply(route,status='received')
                    elif parts.path=='/api/notifications/unsubscribe':
                        writes.append(data); assert data=={'token':LEGACY}; reply(route,status='unsubscribed',
                            message='Any active subscription created with this private link has been unsubscribed.')
                    else: unexpected.append(request.url); route.abort()

                context.route('**/*',intercept)
                page=context.new_page(); page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('console',lambda message:console_errors.append(message.text) if message.type=='error' and
                        'Failed to load resource' not in message.text else None)

                def navigate(token=TOKEN):
                    page.goto(ORIGIN+'/manage-notifications.html'+('#manage='+token if token else ''))

                def private():
                    assert page.evaluate('location.hash')==''
                    assert page.evaluate('history.state') is None
                    assert TOKEN not in page.content() and LEGACY not in page.content()
                    assert all(receipt not in page.content() for receipt in receipts)
                    assert page.evaluate('localStorage.length===0 && sessionStorage.length===0')
                    assert cookie_name not in page.evaluate('document.cookie')
                    assert page.evaluate('window.fetchEvidence.every(e=>e.hash==="")')
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    assert 'Private diagnostic' not in page.content()

                navigate(''); form=page.locator('#management-form'); status=page.locator('#management-status'); error=page.locator('#management-error')
                expect(page.locator('#notification-management')).to_have_attribute('aria-busy','false')
                expect(form).to_be_hidden(); expect(page.locator('#management-recovery')).to_be_visible()
                expect(error).to_have_text(''); assert reads[-1]=={} and not writes
                initial_reads=len(reads); navigate()
                expect(form).to_be_visible(); expect(page.locator('#management-web')).to_be_checked()
                expect(page.locator('#management-android')).not_to_be_checked()
                expect(page.locator('#management-state')).to_have_value('CA')
                assert len(reads)==initial_reads+1 and not writes
                assert page.locator('#management-state option').count()==51
                private(); page.screenshot(path=str(evidence/f'preferences-{width}.png'),full_page=True)
                cookie=next(c for c in context.cookies(ORIGIN) if c['name']==cookie_name)
                assert cookie['secure'] and cookie['httpOnly'] and cookie['sameSite']=='Lax' and cookie['path']=='/'
                deadline=authority['expires']
                page.get_by_role('link',name='GraManna',exact=True).click()
                page.get_by_role('link',name='Manage your notification preferences or unsubscribe',exact=True).click()
                expect(form).to_be_visible(); assert reads[-1]=={} and not writes
                page.go_back(); page.go_back(); expect(form).to_be_visible(); assert reads[-1]=={}
                page.reload(); expect(form).to_be_visible(); assert reads[-1]=={}
                # Exercise the BFCache lifecycle hook as well as actual Back/reload.
                page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted:true}))")
                expect(form).to_be_hidden()
                page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted:true}))")
                expect(form).to_be_visible(); assert reads[-1]=={} and authority['expires']==deadline
                authority['clock']=deadline; page.reload()
                expect(page.locator('#notification-management')).to_have_attribute('aria-busy','false')
                expect(form).to_be_hidden(); expect(page.locator('#management-recovery')).to_be_visible()
                assert not writes
                navigate(); expect(form).to_be_visible()
                context.add_cookies([dict(name=cookie_name,value='tampered',url=ORIGIN,secure=True,httpOnly=True,sameSite='Lax')])
                page.reload(); expect(page.locator('#notification-management')).to_have_attribute('aria-busy','false')
                expect(form).to_be_hidden(); assert not writes
                navigate(); expect(form).to_be_visible(); private()
                page.locator('#management-android').check(); page.locator('#management-ios').uncheck()
                page.locator('#management-state').select_option('TX')
                save=page.get_by_role('button',name='Save preferences',exact=True)
                save.click(); expect(error).to_contain_text('Consent is required'); assert not writes
                page.locator('#management-consent').check()
                page.locator('#management-consent').focus(); page.keyboard.press('Tab'); expect(save).to_be_focused()
                mode['save']='hold'; page.keyboard.press('Enter'); expect(save).to_be_disabled()
                expect(page.locator('#management-web')).to_be_disabled(); assert len(writes)==1
                save.dispatch_event('click'); assert len(writes)==1
                first=writes[-1]; assert first['preferences']==dict(web_launch=True,android_launch=True,ios_launch=False,state='TX',consent=True)
                held.pop('save').fulfill(status=503,content_type='application/json',body='{"message":"Private diagnostic"}')
                expect(error).to_contain_text('We could not confirm this action.')
                mode['save']='lost_commit'; save.click(); expect(error).to_contain_text('We could not confirm this action.')
                assert writes[-1]==first
                mode['save']='normal'; save.click(); expect(status).to_have_text('Your notification preferences have been saved.')
                assert writes[-1]==first; expect(page.locator('#management-title')).to_be_focused()
                expect(page.locator('#management-consent')).not_to_be_checked(); private()
                page.screenshot(path=str(evidence/f'saved-{width}.png'),full_page=True)
                deadline=authority['expires']; page.reload(); expect(form).to_be_visible()
                expect(page.locator('#management-android')).to_be_checked()
                expect(page.locator('#management-ios')).not_to_be_checked()
                expect(page.locator('#management-state')).to_have_value('TX')
                assert reads[-1]=={} and authority['expires']==deadline

                for outcome in ('csrf','html','network','server','conflict'):
                    mode['save']=outcome; page.locator('#management-consent').check(); save.click()
                    expect(error).to_contain_text('Preferences changed.' if outcome=='conflict' else 'We could not confirm this action.')
                    if outcome=='conflict':
                        expect(form).to_be_hidden()
                        expect(page.locator('#management-unsubscribe')).to_be_hidden()
                        page.reload(); expect(form).to_be_visible()
                    else: expect(save).to_be_enabled()
                    private()
                mode['save']='normal'
                page.locator('#management-web').uncheck(); page.locator('#management-android').uncheck()
                page.locator('#management-ios').uncheck(); page.locator('#management-state-enabled').uncheck()
                page.locator('#management-consent').uncheck(); save.click()
                expect(status).to_contain_text('unsubscribed from all notifications')
                expect(form).to_be_hidden(); expect(page.locator('#management-unsubscribe')).to_be_hidden(); private()
                page.screenshot(path=str(evidence/f'unsubscribed-{width}.png'),full_page=True)

                for lost_body in ('lost_body_cookie_retained','lost_body_cookie_deleted'):
                    # Independent synthetic lifecycle fixture for each transport loss.
                    current.update(revision=0,preferences=dict(web_launch=True,android_launch=False,ios_launch=True,state='CA'))
                    results.clear(); receipts.clear(); mode['save']=lost_body
                    navigate(); expect(form).to_be_visible()
                    previous_writes=len(writes); previous_acks=len(acknowledgments)
                    page.get_by_role('button',name='Unsubscribe from everything').click()
                    expect(error).to_contain_text('We could not confirm this action.')
                    assert len(writes)==previous_writes+1 and len(receipts)==1 and len(results)==1
                    retained=any(c['name']==cookie_name for c in context.cookies(ORIGIN))
                    assert retained==(lost_body=='lost_body_cookie_retained')
                    original=writes[-1]; issued=next(iter(receipts))
                    assert receipts[issued]['body']==original
                    private()
                    mode['save']='normal'
                    page.get_by_role('button',name='Unsubscribe from everything').click()
                    expect(status).to_contain_text('unsubscribed from all notifications')
                    assert len(writes)==previous_writes+1 and len(acknowledgments)==previous_acks+1
                    assert acknowledgments[-1]==dict(original,receipt=issued)
                    assert not any(c['name']==cookie_name for c in context.cookies(ORIGIN))
                    expect(form).to_be_hidden(); private()
                    page.reload(); expect(page.locator('#notification-management')).to_have_attribute('aria-busy','false')
                    expect(form).to_be_hidden(); assert reads[-1]=={}
                    assert len(writes)==previous_writes+1

                count=len(writes); page.goto(ORIGIN+'/gramanna.html#unsubscribe='+LEGACY)
                expect(page.locator('#management-legacy-note')).to_be_visible(); expect(form).to_be_hidden()
                assert len(writes)==count
                page.get_by_role('button',name='Unsubscribe from everything').click()
                expect(status).to_have_text('Any active subscription created with this private link has been unsubscribed.')
                expect(page.locator('#management-title')).to_have_text('Request processed')
                expect(status).to_have_attribute('data-status','information'); assert writes[-1]=={'token':LEGACY}
                navigate('broken'); expect(error).to_contain_text('This link is unavailable.'); expect(form).to_be_hidden(); private()
                navigate(''); email=page.get_by_label('Email address',exact=True); email.fill('visitor@example.invalid')
                page.get_by_role('button',name='Email me a link').click()
                expect(status).to_contain_text("If a link is needed and permitted, we'll email it.")
                assert recoveries[-1]=={'email':'visitor@example.invalid'}
                for outcome in ('server','unavailable'):
                    mode['view']=outcome; navigate()
                    expect(error).to_contain_text('This link is unavailable.' if outcome=='unavailable' else 'We could not confirm this action.')
                    expect(form).to_be_hidden(); private()
                mode['view']='normal'; mode['session']='failure'; navigate()
                expect(error).to_contain_text('We could not confirm this action.')
                mode['session']='normal'; current['revision']=0
                page.get_by_role('button',name='View preferences').click(); expect(form).to_be_visible()
                page.screenshot(path=str(evidence/f'navigation-session-{width}.png'),full_page=True)
                mode['enabled']=False; count=len(reads); navigate()
                expect(error).to_contain_text('currently unavailable'); expect(form).to_be_hidden(); assert len(reads)==count
                private(); context.close()
                print(f'PASS V2 {width}px: HttpOnly cookie, navigation, Back/reload, BFCache, fixed expiry, tamper denial, save/retry, both withdrawal body-loss paths, acknowledgment without another mutation, revoked access, legacy, privacy, recovery and OFF.',flush=True)
            assert not errors,errors
            assert not unexpected,unexpected
            assert not console_errors,console_errors
        finally: browser.close()
    print('PASS V2 browser: zero page errors, unexpected console errors or external requests.',flush=True)


if __name__=='__main__': main()
