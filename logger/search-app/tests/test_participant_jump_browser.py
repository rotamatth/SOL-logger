"""ID jumps keep the full roster and export selection intact."""
import pytest
from .test_editor_browser import app, live  # noqa: F401
from .test_research_dashboard import add_history_rule, write_run


@pytest.mark.parametrize('language,width', [('en', 1365), ('it', 390)])
def test_jump_focuses_exact_id_without_filtering_or_changing_selection(live, language, width):
    write_run(live.app, uid='1', suffix='jump')
    page = live.login()
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(live.base + f'/dashboard?collection=study&grade=4&lang={language}')
    before = page.locator('tbody tr').count()
    page.locator('input[name=participant]').check()
    page.fill('#participant-jump-id', '20')
    page.locator('[data-participant-jump] button').click()
    link = page.locator('.participant-link[data-participant-id="20"]')
    assert link.evaluate('(node) => document.activeElement === node')
    assert page.locator('tbody tr').count() == before == 20
    assert page.locator('input[name=participant]').is_checked()
    assert page.locator('[data-jump-result]').inner_text().endswith('20 · 1 / 1')
    page.fill('#participant-jump-id', '2')
    page.locator('[data-participant-jump] button').click()
    assert page.locator('.participant-link[data-participant-id="2"]').evaluate('(node) => document.activeElement === node')
    page.fill('#participant-jump-id', '02')
    page.keyboard.press('Enter')
    assert page.locator('#participant-jump-id').evaluate('(node) => document.activeElement === node')
    assert '02' not in page.locator('[data-jump-result]').inner_text()
    assert page.locator('tbody tr').count() == before
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_duplicate_id_jumps_cycle_through_separate_collections(live):
    add_history_rule(live.app.extensions['research']['state'], grade='4', school_year='2026/2027',
                     date_from='2026-09-01', date_to='2027-08-31')
    write_run(live.app, uid='1', collection='legacy', suffix='legacy-jump')
    page = live.login()
    page.goto(live.base + '/dashboard?collection=study&grade=all&lang=en')
    assert page.locator('.participant-link[data-participant-id="1"]').count() == 2
    page.fill('#participant-jump-id', '1')
    button = page.locator('[data-participant-jump] button')
    button.click()
    first = page.locator('.participant-jump-target .participant-link').get_attribute('href')
    assert page.locator('[data-jump-result]').inner_text().endswith('1 / 2')
    button.click()
    assert page.locator('[data-jump-result]').inner_text().endswith('2 / 2')
    second = page.locator('.participant-jump-target .participant-link').get_attribute('href')
    assert first != second


def test_overview_column_labels_stay_visible_in_keyboard_scroll_region(live):
    page = live.login()
    page.goto(live.base + '/dashboard?collection=study&grade=all&lang=en')
    region = page.locator('.dashboard-table-scroll')
    assert region.get_attribute('role') == 'region' and region.get_attribute('tabindex') == '0'
    assert region.evaluate('(node) => node.scrollHeight > node.clientHeight')
    region.evaluate('(node) => node.scrollTop = 400')
    assert page.locator('thead th').first.evaluate('(node) => getComputedStyle(node).position') == 'sticky'
    assert abs(page.locator('thead th').first.bounding_box()['y'] - region.bounding_box()['y']) < 2
