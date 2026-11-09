"""Focused action sizing and unavailable store badges; intercepted files only."""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

from navigation_browser_check import PAGES, ROOT, geometry, settle
from update1_browser_check import assert_gradient

ORIGIN = 'https://website.example'
WIDTHS = [1440, 1024, 900, 750, 551, 550, 390, 320]
BUTTONS = '.button:not(.legal-skip-link)'
SNAPSHOT = '''() => {
  const box = n => {
    const r = n.getBoundingClientRect();
    return {x:r.x, y:r.y, width:r.width, height:r.height};
  };
  const style = n => {
    const s = getComputedStyle(n);
    return Object.fromEntries(['fontSize','fontFamily','borderRadius','color',
      'backgroundColor','backgroundImage','minWidth','maxWidth'].map(k=>[k,s[k]]));
  };
  const footer = document.querySelector('footer'), fr = footer.getBoundingClientRect();
  const grid = document.querySelector('.gramanna-access-grid');
  return {
    header: [...document.querySelectorAll('.site-header, .foundation-name, .site-header nav a')]
      .map(n=>({box:box(n), style:style(n)})),
    footer: [footer, ...footer.querySelectorAll('div, a')].map(n=>{
      const b=box(n); b.y-=fr.y; return {box:b, style:style(n),
        padding:getComputedStyle(n).padding, gap:getComputedStyle(n).gap};
    }),
    cards: grid ? {columns:getComputedStyle(grid).gridTemplateColumns,
      gap:getComputedStyle(grid).gap, items:[...grid.children].map(n=>({
        x:box(n).x, width:box(n).width, padding:getComputedStyle(n).padding,
        labels:[...n.querySelectorAll('h3,p,.availability-badge')].map(n=>n.textContent)
      }))} : null,
    buttons: [...document.querySelectorAll('.button:not(.legal-skip-link)')]
      .filter(n=>box(n).height).map(n=>({box:box(n), style:style(n),
        label:n.textContent.trim(), href:n.getAttribute('href'), type:n.getAttribute('type'),
        disabled:!!n.disabled, describedby:n.getAttribute('aria-describedby')})),
    overflow:document.documentElement.scrollWidth>innerWidth
  };
}'''


def capture(page, filename):
    page.goto(ORIGIN + '/' + filename)
    # Include conditional confirmation/management controls without API calls.
    page.locator('[hidden]').evaluate_all('nodes=>nodes.forEach(n=>n.hidden=false)')
    page.mouse.move(0, 0)
    return page.evaluate(SNAPSHOT)


def check_labels(page):
    assert page.locator(BUTTONS).evaluate_all('''nodes=>nodes.every(n=>{
      const b=n.getBoundingClientRect(); if(!b.height) return true;
      const walker=document.createTreeWalker(n,NodeFilter.SHOW_TEXT);
      for(let t; t=walker.nextNode();) {
        if(!t.textContent.trim()) continue;
        const range=document.createRange(); range.selectNodeContents(t);
        if(![...range.getClientRects()].every(r=>r.left>=b.left-.1 &&
          r.right<=b.right+.1 && r.top>=b.top-.1 && r.bottom<=b.bottom+.1)) return false;
      }
      return n.scrollWidth<=n.clientWidth && n.scrollHeight<=n.clientHeight;
    })''')


def check_badges(page, coarse):
    for title, provider in [('android', 'Google Play'), ('ios', 'App Store')]:
        card = page.locator(f'article[aria-labelledby="{title}-access-title"]')
        button = card.get_by_role('button')
        expect(button).to_be_disabled()
        expect(button).to_have_attribute('aria-describedby', f'{title}-access-note')
        expect(button).to_have_accessible_name(re.compile(provider))
        assert button.get_attribute('href') is None
        assert card.locator('a').count() == 0
        expect(card.locator('.availability-badge')).to_have_text('Forthcoming')
        expect(card.locator('.interface-note')).to_have_text('Not yet available for download.')
        img = button.locator('img')
        dimensions = img.evaluate('''n=>({natural:[n.naturalWidth,n.naturalHeight],
          width:n.getBoundingClientRect().width,height:n.getBoundingClientRect().height,
          fit:getComputedStyle(n).objectFit,clip:getComputedStyle(n).clipPath})''')
        nw, nh = dimensions['natural']
        assert nw > 0 and nh > 0, dimensions
        assert abs(dimensions['width'] / dimensions['height'] - nw / nh) < .002, dimensions
        assert dimensions['fit'] == 'contain' and dimensions['clip'] == 'none', dimensions
        assert dimensions['width'] <= button.bounding_box()['width'], dimensions
        button.hover(force=True)
        expect(button).to_have_css('transform', 'none')
        expect(button).to_have_css('cursor', 'not-allowed')
        page.mouse.move(0, 0)
        assert button.bounding_box()['height'] == 40


def main(out, baseline, badges, widths=WIDTHS):
    out.mkdir(parents=True, exist_ok=True)
    measurements, errors, unexpected = [], [], []
    baseline_active = False

    def route_files(route):
        parts = urlsplit(route.request.url)
        name = parts.path.lstrip('/') or 'index.html'
        if parts.netloc != 'website.example':
            unexpected.append(route.request.url)
            route.abort()
        elif name.startswith('api/') or name == 'favicon.ico':
            route.fulfill(status=503, json={'message': 'Offline appearance check'})
        else:
            source = ROOT / name
            if baseline_active and name in ['styles.css', 'gramanna.html']:
                source = baseline / name
            if source.is_file() and (source.is_relative_to(ROOT / 'assets') or name in PAGES + ['styles.css']):
                route.fulfill(path=str(source))
            else:
                unexpected.append(route.request.url)
                route.abort()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for coarse in [False, True]:
            context = browser.new_context(viewport={'width':1440, 'height':900},
                has_touch=coarse, reduced_motion='reduce')
            context.route('**/*', route_files)
            page = context.new_page()
            page.on('pageerror', lambda e: errors.append(str(e)))
            for width in widths:
                page.set_viewport_size({'width':width, 'height':900})
                for filename in PAGES:
                    baseline_active = True
                    prior = capture(page, filename)
                    assert page.evaluate("matchMedia('(pointer: coarse)').matches") == coarse
                    # Compare compact navbar geometry independently of shorter content.
                    page.add_style_tag(content='body::after {content:"";display:block;height:1200px;flex-shrink:0}')
                    settle(page, 300)
                    old_compact = geometry(page, coarse, validate=False)
                    baseline_active = False
                    current = capture(page, filename)
                    assert not current['overflow'], (width, coarse, filename, 'overflow')
                    for field in ['header', 'footer', 'cards']:
                        assert current[field] == prior[field], (width, coarse, filename, field)
                    assert len(current['buttons']) == len(prior['buttons'])
                    for actual, old in zip(current['buttons'], prior['buttons']):
                        for field in ['href', 'type', 'disabled', 'describedby', 'style']:
                            assert actual[field] == old[field], (width, filename, field, actual, old)
                        for field in ['x', 'width']:
                            assert actual['box'][field] == old['box'][field], (width, filename, field, actual, old)
                        store = actual['describedby'] in ['android-access-note', 'ios-access-note']
                        if not store or not badges:
                            assert actual['label'] == old['label']
                        minimum = 40 if store and badges else (44 if coarse else 36)
                        # Wrapping and enlarged text may grow controls naturally.
                        assert actual['box']['height'] >= minimum, (width, filename, actual)
                        if actual['label'] and width >= 551:
                            assert actual['box']['height'] == minimum, (width, filename, actual)
                    check_labels(page)
                    if filename == 'gramanna.html':
                        expect(page.get_by_role('button', name='Launch GraManna')).to_be_disabled()
                        if badges:
                            check_badges(page, coarse)
                        for control in page.locator('#access-gramanna button').all():
                            assert not control.evaluate('n=>{n.focus();return document.activeElement===n}')
                    if filename in ['index.html', 'support.html', 'contact.html', 'manage-notifications.html']:
                        control = page.locator(BUTTONS).filter(visible=True).first
                        if control.count() and control.is_enabled():
                            control.focus()
                            expect(control).to_have_css('outline-style', 'solid')
                            page.mouse.move(0, 0)
                            assert_gradient(control)
                            control.hover()
                            assert_gradient(control, hover=True)
                            page.mouse.move(0, 0)
                    page.add_style_tag(content='body::after {content:"";display:block;height:1200px;flex-shrink:0}')
                    settle(page, 300)
                    compact = geometry(page, coarse, validate=False)
                    for field in ['height', 'brand', 'links', 'fonts', 'outerBottom', 'outerVisibleTop']:
                        assert compact[field] == old_compact[field], (width, coarse, filename, field, old_compact[field], compact[field])
                    measurements.append({'width':width, 'coarse':coarse, 'page':filename,
                        'support':current['header'][-1]['box'], 'buttons':current['buttons']})
                # A viewport taller than this section avoids Chromium's screenshot
                # resize resetting touch emulation for oversized element captures.
                shots = browser.new_context(viewport={'width':width, 'height':2600}, has_touch=coarse)
                shots.route('**/*', route_files)
                shot = shots.new_page()
                shot.goto(ORIGIN + '/gramanna.html')
                shot.locator('#access-gramanna').screenshot(path=str(out / f'access-{width}-{"touch" if coarse else "mouse"}.png'))
                assert shot.evaluate("matchMedia('(pointer: coarse)').matches") == coarse
                shots.close()
                print(f'PASS: {width}px {"coarse" if coarse else "fine"}, all ten pages; buttons, cards, navbar and footer.', flush=True)
            # Deliberately wrapped and enlarged ordinary text must grow without clipping.
            for width in [390, 320]:
                for scale in [1, 2]:
                    page.set_viewport_size({'width':width, 'height':1200})
                    capture(page, 'contact.html')
                    control = page.locator('#contact-form button[type="submit"]')
                    control.evaluate('n=>n.textContent="Send a message to Ovis Alms Foundation"')
                    page.add_style_tag(content=f'html {{font-size:{100*scale}%;}} #contact-form button {{width:min(100%, 180px);}}')
                    check_labels(page)
                    assert control.bounding_box()['height'] > (44 if coarse else 36)
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            context.close()
        version = browser.version
        browser.close()
    assert not errors and not unexpected, (errors, unexpected)
    (out / 'measurements.json').write_text(json.dumps(measurements, indent=2), encoding='utf-8')
    result = {'status':'PASS', 'browser':version, 'page_scenarios':len(measurements),
        'enlargement_scenarios':8, 'badges_checked':badges, 'page_errors':errors,
        'unexpected_requests':unexpected}
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifacts', required=True, type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--badges', action='store_true')
    parser.add_argument('--widths', nargs='+', type=int, default=WIDTHS)
    args = parser.parse_args()
    main(args.artifacts, args.baseline, args.badges, args.widths)
