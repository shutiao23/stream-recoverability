from playwright.sync_api import sync_playwright
import pathlib
url = pathlib.Path('dist/companion/index.html').resolve().as_uri()
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width': 1280, 'height': 1100})
    pg.goto(url)
    pg.wait_for_timeout(300)
    secs = pg.query_selector_all('section')
    names = ['classes','panel','contrasts','admission','providers','not_established','artifacts']
    for name, sec in zip(names, secs):
        sec.screenshot(path=f'scratch/p2_03/sec_{name}.png')
    b.close()
