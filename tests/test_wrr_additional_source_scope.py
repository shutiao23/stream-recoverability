import importlib.util
from datetime import date
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("additional_source_scope", SCRIPTS / "423_wrr_additional_source_scope.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_html_download_redirect_and_denial_do_not_certify_absent_observations():
    assert module.access_state(200, "text/html; charset=utf-8") == "html_response_not_temperature_archive"
    assert module.access_state(403, "text/html") == "request_unsuccessful_not_a_zero_observation_count"
    assert module.access_state(200, "application/zip") == "possible_archive_headers_body_and_reference_quality_unverified"


def test_partial_endpoint_years_do_not_add_complete_prior_history():
    assert module.complete_prior_years_upper_bound(date(2018, 9, 6), date(2021, 9, 14)) == 2
    assert module.complete_prior_years_upper_bound(date(2018, 1, 1), date(2021, 12, 31)) == 3
    assert module.complete_prior_years_upper_bound(date(2020, 2, 1), date(2020, 8, 1)) == 0


def test_published_daily_links_distinguish_modeled_and_monthly_products():
    parser = module.DailyLinks()
    parser.feed('<a href="daily.zip">All Days <b>Daily</b> Summary</a><a href="monthly.zip">All Days Monthly Summary</a><a href="model.zip">Modeled Scenarios</a>')
    assert parser.links == {"daily.zip"}
