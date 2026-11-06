"""Focused adaptive navigation checks using intercepted public files only.

Run with the existing Playwright interpreter and -B; no API, mail or database.
"""

import argparse
from io import BytesIO
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from oaf_website.local_testing import PUBLIC_FILES
from contact_browser_check import check_navigation_presentation

ORIGIN = 'https://website.example'
PAGES = [name for name in PUBLIC_FILES if name.endswith('.html')]
WIDTHS = [2560, 1440, 1024, 1000, 980, 960, 940, 920, 901, 900, 899,
          768, 600, 551, 550, 500, 480, 460, 440, 430, 420, 414, 412,
          351, 350,
          400, 390, 375, 360, 320, 280]
SNAPSHOT = '''() => {
  const header = document.querySelector('.site-header');
  const main = document.querySelector('main');
  const brand = header.querySelector('.foundation-name');
  const links = [...header.querySelectorAll('nav a')];
  const rect = n => n.getBoundingClientRect().toJSON();
  const text = n => {const r = document.createRange(); r.selectNodeContents(n);
    return r.getBoundingClientRect().toJSON();};
  const centers = links.map(n => Math.round(rect(n).top + rect(n).height / 2));
  const rows = centers.map(y => [...new Set(centers)].indexOf(y));
  const linkText = links.map(text), brandText = text(brand);
  return {height: rect(header).height, top: rect(header).top,
    layout: innerWidth > 900 ? 'desktop' :
      `${1 + new Set(centers).size}-row`, rows,
    brand: rect(brand), links: links.map(rect), linkText,
    navGap: parseFloat(getComputedStyle(header.querySelector('nav')).columnGap),
    outerTop: rect(brand).top - rect(header).top,
    outerBottom: rect(header).bottom - rect(links[5]).bottom,
    titleToLinksText: linkText[0].top - brandText.bottom,
    linksToSupport: rows[5] === 0 ? null : rect(links[5]).top -
      Math.max(...linkText.filter((r, i) => rows[i] === 0).map(r => r.bottom)),
    fonts: [brand, ...links].map(n => getComputedStyle(n).fontSize),
    flowTop: main ? main.getBoundingClientRect().top + scrollY : null,
    scrollY, scrollHeight: document.documentElement.scrollHeight,
    overflow: document.documentElement.scrollWidth > innerWidth,
    compact: header.classList.contains('is-compact')};
}'''


def rendered_gaps(page, state):
    """Locate painted glyphs in a screenshot; Range rectangles include font leading."""
    pixels = Image.open(BytesIO(page.screenshot(clip={
        'x': 0, 'y': 0, 'width': page.viewport_size['width'], 'height': state['height'],
    }))).convert('RGB')

    def ink_rows(box):
        return [y for y in range(max(0, int(box['top'])), min(pixels.height, int(box['bottom']) + 1))
                if any(min(pixels.getpixel((x, y))) < 180
                       for x in range(max(0, int(box['left'])), min(pixels.width, int(box['right']) + 1)))]

    brand = ink_rows(state['brand'])
    link = ink_rows(state['linkText'][0])
    return {'outerVisibleTop': min(brand) - state['top'],
            'visibleNameToLinks': min(link) - (max(brand) + 1)}


def geometry(page, coarse, validate=True):
    state = page.evaluate(SNAPSHOT)
    state.update(rendered_gaps(page, state))
    if not validate:
        return state
    assert not state['overflow'], state
    assert abs(state['top']) < .1, state
    width = page.viewport_size['width']
    mobile, narrow = width <= 900, width <= 550
    expected_fonts = ([21.12] + [13.376] * 5 + [12.16] if narrow else
                      [26.4] + [16.72] * 5 + [15.2] if mobile else
                      [24] + [15.2] * 6)
    assert all(abs(float(actual[:-2]) - expected) < .001
               for actual, expected in zip(state['fonts'], expected_fonts)), state
    if mobile:
        assert state['rows'] == [0] * 6 and state['layout'] == '2-row', state
        assert abs(state['outerVisibleTop'] - 4) < .1, state
        assert abs(state['outerBottom'] - 4) < .1, state
        assert 0 <= state['visibleNameToLinks'] <= 16, state
        assert state['height'] <= (68 if coarse else 62), state
        for before, after in zip(state['links'], state['links'][1:]):
            assert abs(after['left'] - before['right'] - state['navGap']) < .1, state
    header_bottom = state['height']
    boxes = [state['brand'], *state['links']]
    for i, box in enumerate(boxes):
        assert box['left'] >= 0 and box['right'] <= page.viewport_size['width'], state
        assert box['top'] >= 0 and box['bottom'] <= header_bottom + .1, state
        if i:
            minimum = ((32 if coarse else 26) if narrow else (34 if coarse else 28)) if mobile else (44 if coarse else 36)
            assert abs(box['height'] - minimum) < .1, state
            assert box['width'] >= 24 and box['height'] >= 24, state
        for other in boxes[i + 1:]:
            assert (box['right'] <= other['left'] + .1 or other['right'] <= box['left'] + .1
                    or box['bottom'] <= other['top'] + .1 or other['bottom'] <= box['top'] + .1), (box, other)
    # Text ranges and edge hit tests catch clipping or blocked target areas.
    assert page.locator('.site-header nav a').evaluate_all('''nodes => nodes.every(n => {
      const b = n.getBoundingClientRect();
      const range = document.createRange(); range.selectNodeContents(n);
      return [...range.getClientRects()].every(r => r.top >= b.top && r.bottom <= b.bottom &&
        r.left >= b.left && r.right <= b.right) &&
        [1, b.width / 2, b.width - 1].every(x =>
          n.contains(document.elementFromPoint(b.left + x, b.top + b.height / 2)));
    })''')
    return state


def settle(page, y):
    page.evaluate('''async y => {
      scrollTo(0, y);
      await new Promise(requestAnimationFrame);
      await new Promise(requestAnimationFrame);
    }''', y)
    if y > 64 or y == 0:
        page.wait_for_function('''compact =>
          document.querySelector('.site-header').classList.contains('is-compact') === compact''',
          arg=y > 64)
    page.wait_for_function('''() => document.querySelector('.site-header').getAnimations()
      .every(animation => animation.playState !== 'running')''')


def states(page, coarse, validate=True):
    top = geometry(page, coarse, validate)
    assert not top['compact'], top
    if page.viewport_size['width'] > 900:
        assert top['height'] == 76, top
    settle(page, 300)
    scrolled = geometry(page, coarse, validate)
    assert scrolled['compact'], scrolled
    if page.viewport_size['width'] > 900:
        assert scrolled['height'] == (52 if coarse else 44), scrolled
    else:
        assert scrolled['height'] == top['height'], (top, scrolled)
    assert abs(scrolled['flowTop'] - top['flowTop']) < .1, (top, scrolled)
    assert scrolled['scrollHeight'] == top['scrollHeight'], (top, scrolled)
    assert abs(scrolled['scrollY'] - 300) < .1, scrolled
    settle(page, 0)
    returned = geometry(page, coarse, validate)
    assert not returned['compact'] and returned['height'] == top['height'], returned
    return {'top': top, 'scrolled': scrolled, 'returned': returned}


def main(artifacts, baseline=None, typography=False):
    out = Path(artifacts).resolve()
    out.mkdir(parents=True, exist_ok=True)
    errors, unexpected, measurements, comparisons = [], [], [], []
    baseline_active = False

    def route_files(route):
        url = urlsplit(route.request.url)
        name = url.path.lstrip('/') or 'index.html'
        if url.netloc != 'website.example':
            unexpected.append(route.request.url)
            route.abort()
        elif name in PUBLIC_FILES:
            source = baseline / name if baseline_active and (baseline / name).is_file() else ROOT / name
            route.fulfill(path=str(source))
        elif name.startswith('api/') or name == 'favicon.ico':
            route.fulfill(status=503, json={'message': 'Offline navigation check'})
        else:
            unexpected.append(route.request.url)
            route.abort()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for coarse in [False, True]:
            context = browser.new_context(viewport={'width': 1440, 'height': 900}, has_touch=coarse)
            context.route('**/*', route_files)
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            widths = [1440, 901, 900, 551, 550, 390, 320, 280] if typography else WIDTHS
            for width in widths:
                page.set_viewport_size({'width': width, 'height': 900})
                if baseline:
                    baseline_active = True
                    page.goto(ORIGIN + '/index.html')
                    previous = states(page, coarse, validate=False)
                    baseline_active = False
                page.goto(ORIGIN + '/index.html')
                result = states(page, coarse)
                if baseline:
                    current = result['top']
                    if width > 900:
                        assert result == previous, (width, coarse, 'desktop top/scroll/return changed', previous, result)
                    else:
                        assert current['outerVisibleTop'] == previous['top']['outerVisibleTop'], (width, previous, current)
                        assert current['outerBottom'] == previous['top']['outerBottom'], (width, previous, current)
                        assert all(abs(float(after[:-2]) / float(before[:-2]) - 1.1) < .0001
                                   for before, after in zip(previous['top']['fonts'][:6], current['fonts'][:6])), (width, previous, current)
                        assert current['fonts'][6] == previous['top']['fonts'][6], (width, previous, current)
                        for dimension in ['width', 'height']:
                            assert current['links'][5][dimension] == previous['top']['links'][5][dimension], (width, previous, current)
                    comparisons.append({'width': width, 'coarse': coarse, 'before': previous['top'], 'after': current})
                measurements.append({'page': 'index.html', 'width': width, 'coarse': coarse, **result})
            context.close()
        print(f'PASS: {len(measurements)} viewport/pointer scenarios: top, scrolled, returned; geometry, text, hit areas, fonts and stable flow.', flush=True)

        page_scenarios = [(1440, False), (900, False), (551, True), (550, True),
                          (390, True), (320, True), (280, False), (280, True)]
        if typography:
            page_scenarios = [(900, False), (550, True), (280, False), (280, True)]
        for width, coarse in page_scenarios:
            context = browser.new_context(viewport={'width': width, 'height': 600}, has_touch=coarse)
            context.route('**/*', route_files)
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            for filename in PAGES:
                page.goto(ORIGIN + '/' + filename)
                # Short pages may not scroll: extend only the test document.
                page.add_style_tag(content='body::after { content: ""; display: block; height: 800px; flex-shrink: 0; }')
                states(page, coarse)
                if filename in ['index.html', 'about.html', 'gramanna.html', 'faq.html', 'support.html', 'contact.html'] and (not typography or filename == 'index.html'):
                    check_navigation_presentation(page, filename, coarse)
                for link in page.locator('.site-header nav a').all():
                    link.focus()
                    page.keyboard.press('Tab')
                    page.keyboard.press('Shift+Tab')
                    expect(link).to_be_focused()
                    expect(link).to_have_css('outline-style', 'solid')
                if filename == 'index.html':
                    for label, y in [('top', 0), ('scrolled', 300), ('returned', 0)]:
                        settle(page, y)
                        page.screenshot(path=str(out / f'{width}-{label}.png'))
            # Activate the existing links through the keyboard, preserving order/current state.
            for target in ['about.html', 'gramanna.html', 'faq.html', 'contact.html', 'support.html', 'index.html']:
                link = page.locator(f'.site-header nav a[href="{target}"]')
                link.focus()
                page.keyboard.press('Enter')
                expect(page).to_have_url(ORIGIN + '/' + target)
                expect(page.locator('.site-header nav a[aria-current="page"]')).to_have_attribute('href', target)
            context.close()
        print('PASS: all ten public pages at selected widths; two-row geometry, navigation presentation, keyboard focus and link activation.', flush=True)

        if typography:
            enlarged = check_enlargement(browser, route_files, out)
            version = browser.version
            browser.close()
            assert not errors and not unexpected, (errors, unexpected)
            (out / 'measurements.json').write_text(json.dumps(measurements, indent=2), encoding='utf-8')
            (out / 'before-after.json').write_text(json.dumps(comparisons, indent=2), encoding='utf-8')
            (out / 'result.json').write_text(json.dumps({
                'status': 'PASS', 'browser': version, 'viewport_scenarios': len(measurements),
                'public_page_scenarios': len(PAGES) * len(page_scenarios),
                'enlargement_scenarios': len(enlarged), 'page_errors': errors,
                'unexpected_requests': unexpected,
            }, indent=2), encoding='utf-8')
            print('PASS: focused typography checks; accepted unrelated motion/anchor/hero evidence reused.', flush=True)
            return

        for motion in ['no-preference', 'reduce']:
            context = browser.new_context(viewport={'width': 1440, 'height': 900}, reduced_motion=motion)
            context.route('**/*', route_files)
            page = context.new_page()
            page.goto(ORIGIN + '/index.html')
            header = page.locator('.site-header')
            expect(header).to_have_css('transition-duration', '0s' if motion == 'reduce' else '0.18s, 0.18s')
            # Sample animation frames: intermediate heights prove a smooth transition.
            samples = page.evaluate('''async () => {
              const h = document.querySelector('.site-header'), frames = [];
              scrollTo(0, 300);
              for (let i = 0; i < 24; i++) {
                await new Promise(requestAnimationFrame);
                frames.push({height: h.getBoundingClientRect().height, y: scrollY,
                  flow: document.querySelector('main').getBoundingClientRect().top + scrollY});
              }
              return frames;
            }''')
            assert all(abs(s['y'] - 300) < .1 and abs(s['flow'] - 76) < .2 for s in samples), samples
            assert abs(samples[-1]['height'] - 44) < .1, samples
            if motion == 'no-preference':
                assert any(44.1 < s['height'] < 75.9 for s in samples), samples
            else:
                assert all(s['height'] in [44, 76] for s in samples), samples
            for y, compact in [(65, True), (64, True), (63, True), (1, True), (0, False),
                               (1, False), (63, False), (64, False), (65, True), (64, True), (0, False)]:
                settle(page, y)
                assert page.evaluate(SNAPSHOT)['compact'] == compact, (motion, y)
            settle(page, 300)
            page.reload()
            page.wait_for_timeout(250)
            assert page.evaluate(SNAPSHOT)['compact']
            # Native back navigation restores scroll/header state via pageshow.
            page.goto(ORIGIN + '/about.html')
            page.go_back()
            page.wait_for_timeout(250)
            assert page.evaluate(SNAPSHOT)['compact']
            context.close()
        print('PASS: smooth/reduced motion, stable thresholds, reload/back scroll restoration.', flush=True)

        for width in [1440, 900, 390, 320, 280]:
            context = browser.new_context(viewport={'width': width, 'height': 900}, has_touch=width <= 390)
            context.route('**/*', route_files)
            page = context.new_page()
            page.goto(ORIGIN + '/privacy-policy.html')
            skip = page.locator('.legal-skip-link')
            skip.focus()
            page.keyboard.press('Enter')
            page.wait_for_timeout(250)
            main = page.locator('main').bounding_box()
            header = page.locator('.site-header').bounding_box()
            assert main['y'] >= header['height'] - .1, (width, main, header)
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
            page.goto(ORIGIN + '/gramanna.html#notification-form')
            page.wait_for_timeout(250)
            target = page.locator('#notification-form').bounding_box()
            header = page.locator('.site-header').bounding_box()
            assert target['y'] >= header['height'] - .1, (width, target, header)
            context.close()
        print('PASS: legal keyboard skip link and existing notification anchor clear the sticky header.', flush=True)

        # Enlarged default text must remain readable; preserve the approved row controls.
        context = browser.new_context(viewport={'width': 900, 'height': 900})
        context.route('**/*', route_files)
        page = context.new_page()
        page.goto(ORIGIN + '/index.html')
        page.add_style_tag(content='html { font-size: 200%; }')
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
        assert page.locator('.site-header nav a').evaluate_all('nodes => nodes.every(n => n.clientHeight >= 36)')
        context.close()
        browser.close()
    assert not errors, errors
    assert not unexpected, unexpected
    (out / 'measurements.json').write_text(json.dumps(measurements, indent=2), encoding='utf-8')
    if baseline:
        (out / 'before-after.json').write_text(json.dumps(comparisons, indent=2), encoding='utf-8')
    (out / 'result.json').write_text(json.dumps({'status': 'PASS', 'browser': browser.version,
        'viewport_scenarios': len(measurements), 'public_page_scenarios': len(PAGES) * len(page_scenarios),
        'page_errors': errors, 'unexpected_requests': unexpected}, indent=2), encoding='utf-8')
    print('PASS: focused adaptive navigation Chromium checks; no external requests, services or repository writes by browser.', flush=True)


def check_enlargement(browser, route_files, out):
    """Exercise only the shared header so unrelated page content cannot mask reflow."""
    results = []
    for width in [900, 550, 390, 320, 280]:
        for mode, scale in [('text', 1.25), ('text', 2), ('text', 4), ('zoom', 2)]:
            context = browser.new_context(viewport={'width': width, 'height': 1600}, has_touch=True)
            context.route('**/*', route_files)
            page = context.new_page()
            page.goto(ORIGIN + '/index.html')
            # Keep the actual header and styles; remove unrelated body content.
            page.evaluate('''() => [...document.body.children].forEach(n => {
                if (!n.matches('.site-header')) n.remove();
            })''')
            page.add_style_tag(content=(f'html {{ font-size: {scale * 100}%; }}' if mode == 'text'
                                        else f'body {{ zoom: {scale}; }}'))
            state = page.evaluate(SNAPSHOT)
            assert not state['overflow'], (width, mode, scale, state)
            boxes = [state['brand'], *state['links']]
            assert state['brand']['bottom'] <= state['links'][0]['top'] + .1, state
            assert page.locator('.site-header nav a').all_text_contents() == [
                'Home', 'About', 'GraManna', 'FAQ', 'Contact', 'Support']
            for i, box in enumerate(boxes):
                assert box['left'] >= -.1 and box['right'] <= width + .1, state
                assert box['top'] >= -.1 and box['bottom'] <= state['height'] + .1, state
                for other in boxes[i + 1:]:
                    assert (box['right'] <= other['left'] + .1 or other['right'] <= box['left'] + .1
                            or box['bottom'] <= other['top'] + .1 or other['bottom'] <= box['top'] + .1), state
            assert page.locator('.site-header nav a').evaluate_all('''nodes => nodes.every(n => {
                const b = n.getBoundingClientRect(), range = document.createRange();
                range.selectNodeContents(n);
                return [...range.getClientRects()].every(r => r.left >= b.left - .1 &&
                    r.right <= b.right + .1 && r.top >= b.top - .1 && r.bottom <= b.bottom + .1);
            })'''), state
            if mode == 'text':
                expected = ([26.4] + [16.72] * 5 + [15.2]) if width > 550 else ([21.12] + [13.376] * 5 + [12.16])
                assert all(abs(float(font[:-2]) - size * scale) < .001
                           for font, size in zip(state['fonts'], expected)), state
            if width in [320, 280] and scale == 2:
                page.screenshot(path=str(out / f'{width}-{mode}-200.png'))
            results.append({'width': width, 'mode': mode, 'scale': scale, **state})
            context.close()
    (out / 'enlargement.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(f'PASS: {len(results)} header-only scenarios: 125/200/400% text and CSS zoom 200%; readable fonts, safe wrapping, no overlap/clipping/overflow.', flush=True)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifacts', required=True)
    parser.add_argument('--baseline', type=Path, help='Pre-change files for exact desktop top/scroll/return and responsive typography comparisons.')
    parser.add_argument('--typography', action='store_true', help='Focused typography matrix; reuse prior accepted unrelated evidence.')
    args = parser.parse_args()
    main(args.artifacts, args.baseline, args.typography)
