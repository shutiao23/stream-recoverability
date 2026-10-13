from playwright.sync_api import sync_playwright
import pathlib
url = pathlib.Path('dist/companion/index.html').resolve().as_uri()
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width': 1280, 'height': 1000})
    pg.goto(url)
    pg.wait_for_timeout(400)
    pg.screenshot(path='scratch/p2_03/dash_full.png', full_page=True)
    pg.screenshot(path='scratch/p2_03/dash_top.png')
    # hover a number to capture the tooltip text
    el = pg.query_selector('span.num')
    print('first number:', el.inner_text(), '| title:', el.get_attribute('title')[:160])
    print('title:', pg.title())
    print('sections:', len(pg.query_selector_all('section')))
    print('number spans:', len(pg.query_selector_all('span.num')))
    b.close()
