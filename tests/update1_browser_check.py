"""Focused hero/footer/CTA paint checks; intercepted public files, no services."""

from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
import argparse
import hashlib
import json
import sys

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from oaf_website.local_testing import PUBLIC_FILES

ORIGIN = 'https://website.example'
PAGES = ['index.html', 'about.html', 'gramanna.html', 'faq.html', 'contact.html',
         'support.html', 'confirm-email.html', 'manage-notifications.html',
         'privacy-policy.html', 'terms-of-use.html']
HERO_IMAGE = 'assets/images/oaf-homepage-hero-gift-cards8.png'
HERO_SHA256 = '6f7f814e9474a895c96713446b29a57bebcc8743f867d1ca1a438cb65d36d6f0'
COPYRIGHT = '\u00a9 2026 All Rights Reserved | Ovis Alms Foundation'
FOOTER_SNAPSHOT = '''() => [...document.querySelectorAll('footer, footer > div, .footer-links a')].map(n => {
    const s = getComputedStyle(n);
    return Object.fromEntries(['display', 'flexDirection', 'flexWrap', 'justifyContent', 'alignItems',
        'gap', 'padding', 'borderTop', 'font', 'color', 'background', 'textAlign'].map(k => [k, s[k]]));
})'''
CONTROLS = '.button, .site-header nav a, .footer-links a'
HERO_SNAPSHOT = '''() => [...document.querySelectorAll('.hero, .hero-overlay, .hero-content, .hero h1, .hero p, .hero-image, .hero-image img')].map(n => {
    const s = getComputedStyle(n), r = n.getBoundingClientRect();
    return {box: {x: r.x + scrollX, y: r.y + scrollY, width: r.width, height: r.height}, background: s.backgroundImage,
        mask: s.maskImage, fit: s.objectFit, crop: s.objectPosition,
        color: s.color, font: s.font, spacing: s.letterSpacing};
})'''
CONTROL_SNAPSHOT = '''nodes => nodes.map(n => {
    const s = getComputedStyle(n), r = n.getBoundingClientRect();
    return {text: n.textContent, box: {x: r.x + scrollX, y: r.y + scrollY, width: r.width, height: r.height},
        padding: s.padding, margin: s.margin, radius: s.borderRadius, font: s.font,
        lineHeight: s.lineHeight, color: s.color, outline: s.outline, cursor: s.cursor,
        href: n.getAttribute('href'), type: n.getAttribute('type'), disabled: n.disabled,
        aria: [...n.attributes].filter(a => a.name.startsWith('aria-')).map(a => [a.name, a.value])};
})'''


def assert_gradient(control, hover=False):
    expected = control.evaluate('''(n, hover) => {
        const root = getComputedStyle(document.documentElement);
        const color = root.getPropertyValue(hover ? '--brand-aubergine' : '--brand-green').trim();
        const light = `color-mix(in srgb, ${color} 80%, white)`;
        const probe = document.createElement('span');
        probe.style.backgroundImage = `linear-gradient(to right, ${hover ? light : color}, ${hover ? color : light})`;
        document.body.append(probe);
        const gradient = getComputedStyle(probe).backgroundImage;
        probe.remove();
        return gradient;
    }''', hover)
    assert control.evaluate('n => getComputedStyle(n).backgroundImage') == expected


def contrast(rgb):
    channels = [v / 255 for v in rgb]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
    return 1.05 / (.2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2] + .05)


def assert_controls_preserved(current, previous, width, filename):
    if filename == 'index.html':
        # Content below the resized hero moves vertically; control sizes,
        # styling, semantics and horizontal positions must remain unchanged.
        def without_y(controls):
            return [dict(c, box={k: v for k, v in c['box'].items() if k != 'y'}) for c in controls]
        current, previous = without_y(current), without_y(previous)
    assert current == previous, (width, filename, 'control geometry/semantics changed')


def assert_full_frame(page, hero, painted):
    image = page.locator('.hero-image img')
    frame = page.locator('.hero-image').bounding_box()
    box, banner = image.bounding_box(), hero.bounding_box()
    native = image.evaluate('''n => ({width: n.naturalWidth, height: n.naturalHeight,
        fit: getComputedStyle(n).objectFit, position: getComputedStyle(n).objectPosition,
        clip: getComputedStyle(n).clipPath})''')
    assert (native['width'], native['height']) == (1670, 941), native
    assert native['fit'] == 'contain' and native['position'] == '100% 50%' and native['clip'] == 'none', native
    scale = min(frame['width'] / native['width'], frame['height'] / native['height'])
    for dimension in ['width', 'height']:
        assert abs(box[dimension] - native[dimension] * scale) < .05, (box, frame, native)
    assert abs(box['height'] - frame['height']) < .05, ('visible image has vertical gaps', box, frame)
    assert abs(box['width'] / box['height'] - native['width'] / native['height']) < .001
    assert abs(box['x'] + box['width'] - frame['x'] - frame['width']) < .05, (box, frame)
    assert abs(box['y'] + box['height'] / 2 - frame['y'] - frame['height'] / 2) < .05, (box, frame)
    for outer in [frame, banner]:
        assert box['x'] >= outer['x'] - .05 and box['y'] >= outer['y'] - .05
        assert box['x'] + box['width'] <= outer['x'] + outer['width'] + .05
        assert box['y'] + box['height'] <= outer['y'] + outer['height'] + .05
    text = page.locator('.hero-content').bounding_box()
    if page.viewport_size['width'] > 900:
        assert abs(box['y'] - banner['y']) < .05
        assert abs(box['height'] - banner['height']) < .05, ('image must fill banner height', box, banner)
        assert text['x'] + text['width'] <= box['x'] + .05, ('image overlaps text', text, box)
        assert box['x'] >= banner['width'] / 2, ('image must stay on right', box, banner)
    else:
        assert box['y'] >= text['y'] + text['height'], ('stacked image overlaps text', text, box)
        assert abs(box['y'] + box['height'] - banner['y'] - banner['height']) < .05

    unmask = page.add_style_tag(content='.hero-image, .hero-image img { -webkit-mask-image: none !important; mask-image: none !important; }')
    full = Image.open(BytesIO(hero.screenshot())).convert('RGB')
    unmask.evaluate('n => n.remove()')
    hide = page.add_style_tag(content='.hero-image img { visibility: hidden; }')
    background = Image.open(BytesIO(hero.screenshot())).convert('RGB')
    hide.evaluate('n => n.remove()')
    left, top = box['x'] - banner['x'], box['y'] - banner['y']
    # This envelope encloses all six surrounding cards and the complete central
    # card in the approved PNG. Their rendered pixels must stay fully opaque.
    cards = (round(left + box['width'] * .142), round(top + box['height'] * .155),
             round(left + box['width'] * .849), round(top + box['height'] * .76))
    assert ImageChops.difference(painted.crop(cards), full.crop(cards)).getbbox() is None, 'A fade obscures the card composition'
    samples = []
    for fraction in [.02, .05, .08, .11, .14, .85, .88, .91, .94, .97]:
        x, y = round(left + box['width'] * fraction), round(top + box['height'] / 2)
        actual_fraction = (x + .5 - left) / box['width']
        alpha = min(1, max(0, actual_fraction / .14), max(0, (1 - actual_fraction) / .15))
        source, base, actual = full.getpixel((x, y)), background.getpixel((x, y)), painted.getpixel((x, y))
        expected = [a * alpha + b * (1 - alpha) for a, b in zip(source, base)]
        assert all(abs(a - b) <= 4 for a, b in zip(actual, expected)), (fraction, alpha, actual, expected)
        samples.append({'fraction': actual_fraction, 'alpha': alpha, 'actual': actual, 'expected': expected})
    return {'frame': frame, 'image': box, 'native': native, 'scale': scale, 'card_envelope': cards, 'fade_samples': samples}


def main(artifacts, baseline=None, widths=(1440, 901, 900, 768, 390, 320, 280), hero_only=False):
    artifacts.mkdir(parents=True, exist_ok=True)
    errors, unexpected, measurements, image_responses = [], [], [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for width in widths:
                context = browser.new_context(viewport={'width': width, 'height': 1000},
                                              reduced_motion='reduce', has_touch=width <= 390)
                baseline_active = False

                def intercept(route):
                    parts = urlsplit(route.request.url)
                    name = parts.path.lstrip('/')
                    if parts.scheme == 'https' and parts.netloc == 'website.example' and name in PUBLIC_FILES:
                        source = baseline / name if baseline_active and (baseline / name).is_file() else ROOT / name
                        route.fulfill(path=source)
                    elif parts.netloc == 'website.example' and parts.path.endswith('/session'):
                        route.fulfill(json={'csrf_token': '0' * 64})
                    elif parts.netloc == 'website.example' and parts.path == '/api/state-requests/totals':
                        route.fulfill(json={'totals': {'CA': 0}})
                    else:
                        unexpected.append(route.request.url)
                        route.abort()

                context.route('**/*', intercept)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('response', lambda response: image_responses.append(response.status) if response.url == ORIGIN + '/' + HERO_IMAGE else None)
                prior_controls, prior_footers = {}, {}
                if baseline:
                    baseline_active = True
                    for filename in PAGES:
                        page.goto(ORIGIN + '/' + filename)
                        page.mouse.move(0, 0)
                        prior_controls[filename] = page.locator(CONTROLS).evaluate_all(CONTROL_SNAPSHOT)
                        prior_footers[filename] = page.evaluate(FOOTER_SNAPSHOT)
                        if filename == 'index.html':
                            prior_hero = page.evaluate(HERO_SNAPSHOT)
                    baseline_active = False
                page.goto(ORIGIN + '/index.html')
                hero = page.locator('.hero')

                def snapshot():
                    return page.evaluate(HERO_SNAPSHOT)

                if baseline:
                    current_hero = snapshot()
                    # Height and vertical positions intentionally change. Preserve
                    # all text dimensions and hero/text colors, gradients and fonts.
                    for i in range(5):
                        assert {k: v for k, v in current_hero[i].items() if k != 'box'} == {k: v for k, v in prior_hero[i].items() if k != 'box'}
                        for dimension in ['x', 'width'] + ([] if i == 0 else ['height']):
                            assert current_hero[i]['box'][dimension] == prior_hero[i]['box'][dimension], (width, i, dimension)

                hide = page.add_style_tag(content='.hero::before, .hero::after, .hero-edge-accents { visibility: hidden; }')
                before = snapshot()
                plain = Image.open(BytesIO(hero.screenshot())).convert('RGB')
                hide.evaluate('n => n.sheet.disabled = true')
                after = snapshot()
                assert before == after, (width, 'hero composition changed')
                painted = Image.open(BytesIO(hero.screenshot(path=str(artifacts / f'hero-{width}.png')))).convert('RGB')
                # Every pixel outside the 20px decoration strips is unchanged.
                crop = (21, 0, painted.width - 21, painted.height)
                assert ImageChops.difference(plain.crop(crop), painted.crop(crop)).getbbox() is None
                decoration = hero.evaluate('''n => ['::before', '::after'].map(pseudo => {
                    const s = getComputedStyle(n, pseudo);
                    return {width: parseFloat(s.width), height: parseFloat(s.height), top: parseFloat(s.top),
                        radius: s.borderRadius, color: s.backgroundColor, z: s.zIndex,
                        left: s.left, right: s.right, pointer: s.pointerEvents};
                })''')
                depth = min(20, max(20, min(width * .0375, 24)) - 1)
                box = hero.bounding_box()
                for shape in decoration:
                    assert abs(shape['width'] - depth) < .03
                    assert abs(shape['height'] - depth * 8 / 3) < .03
                    assert abs(shape['top'] - box['height'] / 2) < .03
                    assert shape['color'] == 'rgb(255, 255, 255)'
                    assert shape['pointer'] == 'none' and shape['z'] == '3'
                assert decoration[0]['left'] == decoration[1]['right'] == '0px'
                assert decoration[0]['radius'] == '0px 100% 100% 0px / 0px 50% 50% 0px'
                assert decoration[1]['radius'] == '100% 0px 0px 100% / 50% 0px 0px 50%'
                assert page.locator('.hero-edge-accents').evaluate('n => getComputedStyle(n).borderInlineWidth') == '3px'
                for y in [2, painted.height // 2, painted.height - 3]:
                    for x in [0, 1, 2]:
                        assert painted.getpixel((x, y)) == painted.getpixel((painted.width - 1 - x, y)) == (255, 255, 255)
                for x in range(int(depth) - 1):
                    assert painted.getpixel((x, painted.height // 2)) == painted.getpixel((painted.width - 1 - x, painted.height // 2)) == (255, 255, 255)
                image = page.locator('.hero-image')
                assert image.evaluate('n => getComputedStyle(n).maskImage') == 'none'
                expect(page.locator('.hero-image img')).to_have_attribute('src', HERO_IMAGE)
                assert page.locator('.hero-image img').evaluate('n => n.complete && n.naturalWidth > 0 && n.naturalHeight > 0')
                expect(page.locator('.hero-image img')).to_have_css('mask-image', 'linear-gradient(to right, rgba(0, 0, 0, 0), rgb(0, 0, 0) 14%, rgb(0, 0, 0) 85%, rgba(0, 0, 0, 0))')
                composition = assert_full_frame(page, hero, painted)
                fetched = page.evaluate('''async url => {
                    const response = await fetch(url), body = await response.arrayBuffer();
                    const hash = await crypto.subtle.digest('SHA-256', body);
                    return {status: response.status, type: response.headers.get('content-type'),
                        sha256: [...new Uint8Array(hash)].map(v => v.toString(16).padStart(2, '0')).join('')};
                }''', '/' + HERO_IMAGE)
                assert fetched['status'] == 200 and fetched['type'] == 'image/png', fetched
                assert fetched['sha256'] == hashlib.sha256((ROOT / HERO_IMAGE).read_bytes()).hexdigest() == HERO_SHA256
                assert page.locator('.hero h1').bounding_box()['x'] > depth
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, 'homepage overflow')

                if hero_only:
                    for filename in PAGES:
                        page.goto(ORIGIN + '/' + filename)
                        page.evaluate('scrollTo(0, 0)')
                        page.mouse.move(0, 0)
                        expect(page.locator('footer > div').first).to_have_text(COPYRIGHT, use_inner_text=True)
                        links = page.locator('.footer-links a').evaluate_all('nodes => nodes.map(n => [n.textContent, n.getAttribute("href")])')
                        assert links == [['Privacy Policy', 'privacy-policy.html'], ['Terms of Use', 'terms-of-use.html']], (width, filename, links)
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, filename, 'overflow')
                        assert page.locator('footer').evaluate('n => {const r=n.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth;}')
                        if baseline:
                            assert page.evaluate(FOOTER_SNAPSHOT) == prior_footers[filename], (width, filename, 'footer styling changed')
                            current = page.locator(CONTROLS).evaluate_all(CONTROL_SNAPSHOT)
                            assert_controls_preserved(current, prior_controls[filename], width, filename)
                    measurements.append({'width': width, 'hero': box, 'decoration': decoration, 'composition': composition, 'footers': len(PAGES)})
                    page.goto(ORIGIN + '/index.html')
                    if width in {2560, 1440, 900, 390, 320}:
                        page.screenshot(path=str(artifacts / f'index.html-{width}.png'), full_page=True)
                    context.close()
                    print(f'PASS: {width}px exact v8 bytes, full-height/full-frame fit/right alignment, opaque cards, two-sided fade pixels, preserved text, notches/accents, {len(PAGES)} footers/links/styles and overflow.', flush=True)
                    continue

                count = 0
                for filename in PAGES:
                    page.goto(ORIGIN + '/' + filename)
                    page.mouse.move(0, 0)
                    if baseline:
                        current = page.locator(CONTROLS).evaluate_all(CONTROL_SNAPSHOT)
                        assert_controls_preserved(current, prior_controls[filename], width, filename)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, filename)
                    # Ordinary/current navigation and footer links keep their existing states.
                    for link in page.locator('.site-header nav a:not(.nav-support), .site-header nav a[aria-current="page"], .footer-links a').all():
                        assert link.evaluate('n => getComputedStyle(n).backgroundImage') == 'none'
                        link.hover()
                        assert link.evaluate('n => getComputedStyle(n).backgroundImage') == 'none'
                    page.mouse.move(0, 0)
                    for number, control in enumerate(page.locator('.button, .nav-support:not([aria-current="page"])').all()):
                        if not control.is_visible():
                            continue
                        skip_link = control.evaluate("n => n.matches('.legal-skip-link')")
                        if skip_link:
                            # Skip links intentionally stay offscreen until keyboard focus.
                            control.focus()
                        control.scroll_into_view_if_needed()
                        page.mouse.move(0, 0)
                        geometry = control.evaluate('''n => {
                            const s = getComputedStyle(n), p = getComputedStyle(n, '::before');
                            return {mask: s.maskImage, clip: s.clipPath, pseudoMask: p.maskImage, content: p.content,
                                border: s.borderWidth, background: s.backgroundColor, image: s.backgroundImage,
                                color: s.color, width: n.clientWidth, height: n.clientHeight, transition: s.transitionDuration};
                        }''')
                        assert geometry['mask'] == geometry['pseudoMask'] == geometry['clip'] == 'none'
                        assert geometry['content'] == 'none'
                        assert geometry['border'] == '0px'
                        assert geometry['transition'] == '0s'
                        disabled = not control.is_enabled()
                        web = control.evaluate("n => Boolean(n.closest('.web-access-card'))")
                        expected = ('rgb(220, 231, 226)' if web else 'rgb(237, 241, 238)') if disabled else 'rgb(29, 95, 49)'
                        assert geometry['background'] == expected, (width, filename, geometry)
                        if disabled:
                            assert geometry['image'] == 'none'
                            expect(control).to_have_css('cursor', 'not-allowed')
                        else:
                            assert_gradient(control)
                            assert geometry['color'] == 'rgb(255, 255, 255)'
                        colored = Image.open(BytesIO(control.screenshot())).convert('RGB')
                        clear = page.add_style_tag(content='.button, .site-header nav .nav-support { background: transparent !important; }')
                        bare = Image.open(BytesIO(control.screenshot())).convert('RGB')
                        clear.evaluate('n => n.remove()')
                        center = colored.height // 2
                        # Both mid-edges are now painted continuously, including disabled CTAs.
                        for x in [1, colored.width - 2]:
                            assert colored.getpixel((x, center)) != bare.getpixel((x, center)), (width, filename, number, 'edge not painted')
                        if not disabled:
                            # Pixel endpoints independently verify the exact sRGB mix and direction.
                            for x, rgb in [(2, (29, 95, 49)), (colored.width - 3, (74.2, 127, 90.2))]:
                                assert all(abs(a - b) < 3 for a, b in zip(colored.getpixel((x, center)), rgb)), (width, filename, number, 'normal gradient pixels')
                            assert contrast((74.2, 127, 90.2)) >= 4.5
                            assert contrast((143.8, 80.6, 143.8)) >= 4.5
                        if not disabled:
                            assert control.evaluate('''n => {
                                const r = n.getBoundingClientRect();
                                return n.contains(document.elementFromPoint(r.left + 1, r.top + r.height / 2));
                            }'''), (width, filename, 'left edge lost hit area')
                            assert control.evaluate('''n => {
                                const r = n.getBoundingClientRect();
                                return n.contains(document.elementFromPoint(r.right - 1, r.top + r.height / 2));
                            }'''), (width, filename, 'right edge lost hit area')
                            control.focus()
                            page.keyboard.press('Shift')
                            expect(control).to_have_css('outline-style', 'solid')
                            assert float(control.evaluate('n => getComputedStyle(n).outlineOffset').replace('px', '')) >= 2
                            assert_gradient(control, hover=control.evaluate("n => n.matches('.nav-support')"))
                            if not skip_link:
                                control.evaluate('n => n.blur()')
                            control.hover()
                            assert_gradient(control, hover=True)
                            hovered = Image.open(BytesIO(control.screenshot())).convert('RGB')
                            for x, rgb in [(2, (143.8, 80.6, 143.8)), (hovered.width - 3, (116, 37, 116))]:
                                assert all(abs(a - b) < 3 for a, b in zip(hovered.getpixel((x, hovered.height // 2)), rgb)), (width, filename, number, 'hover gradient pixels')
                            page.mouse.down()
                            expect(control).to_have_css('background-color', 'rgb(18, 59, 30)')
                            expect(control).to_have_css('background-image', 'none')
                            page.mouse.move(0, 0)
                            page.mouse.up()
                            control.evaluate('n => n.blur()')
                        else:
                            control.hover()
                            expect(control).to_have_css('background-color', expected)
                            expect(control).to_have_css('background-image', 'none')
                            expect(control).to_have_css('transform', 'none')
                        count += 1
                measurements.append({'width': width, 'hero': box, 'decoration': decoration, 'composition': composition, 'buttons': count})
                context.close()
                if width in {1440, 390, 320}:
                    # Full-page capture resets Chromium's coarse-pointer emulation.
                    # Keep artifacts in separate contexts so layout checks stay comparable.
                    for filename in ['index.html', 'gramanna.html', 'contact.html']:
                        capture = browser.new_context(viewport={'width': width, 'height': 1000},
                                                      reduced_motion='reduce', has_touch=width <= 390)
                        capture.route('**/*', intercept)
                        shot = capture.new_page()
                        shot.on('pageerror', lambda error: errors.append(str(error)))
                        shot.goto(ORIGIN + '/' + filename)
                        shot.screenshot(path=str(artifacts / f'{filename}-{width}.png'), full_page=True)
                        capture.close()
                print(f'PASS: {width}px exact hero image/geometry/composition/pixels, {len(PAGES)} pages, {count} CTA shapes/gradients/hit areas/states, focus and overflow.', flush=True)
            motion = []
            for width in ([] if hero_only else [1440, 390]):
                context = browser.new_context(viewport={'width': width, 'height': 1000}, reduced_motion='no-preference')
                context.route('**/*', intercept)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(ORIGIN + '/index.html')
                for selector in ['.hero ~ .contact-strip .button', '.site-header .nav-support']:
                    control = page.locator(selector)
                    control.scroll_into_view_if_needed()
                    page.mouse.move(0, 0)
                    assert_gradient(control)
                    control.hover()
                    animations = control.evaluate('''n => n.getAnimations().map(a => ({property: a.transitionProperty, duration: a.effect.getTiming().duration}))''')
                    for name in ['--cta-start', '--cta-end']:
                        assert {'property': name, 'duration': 160} in animations, (width, selector, animations)
                    control.evaluate('n => Promise.all(n.getAnimations().map(a => a.finished))')
                    assert_gradient(control, hover=True)
                    motion.append({'width': width, 'control': selector, 'animations': animations})
                context.close()
                print(f'PASS: {width}px normal-motion CTA gradient stops transition smoothly in 160ms.', flush=True)
            assert not errors, errors
            assert not unexpected, unexpected
            assert image_responses and set(image_responses) == {200}, image_responses
            (artifacts / 'measurements.json').write_text(json.dumps({'browser': browser.version, 'scenarios': measurements, 'motion': motion, 'image': fetched}, indent=2))
        finally:
            browser.close()
    print(f'PASS: {len(widths)} reduced-motion viewport scenarios' + (' (hero and all footers)' if hero_only else ' plus 2 normal-motion scenarios') + '; zero page errors/external requests; no database, credentials or provider operations. Owner visual acceptance pending.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifacts', type=Path, default=ROOT / '.pytest_cache/update1-final-hero-buttons-20261106/visuals')
    parser.add_argument('--baseline', type=Path, help='Optional pre-change source snapshot for layout/semantics comparison.')
    parser.add_argument('--widths', type=int, nargs='+', default=[1440, 901, 900, 768, 390, 320, 280])
    parser.add_argument('--hero-only', '--hero-footer-only', dest='hero_only', action='store_true', help='Run focused hero and all-footer checks; reuse accepted unrelated CTA evidence.')
    args = parser.parse_args()
    main(args.artifacts, args.baseline, args.widths, args.hero_only)
