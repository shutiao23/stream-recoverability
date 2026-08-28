from stream_recoverability.data.ccg_temperature import parse_embedded_daily


def test_ccg_parser_retains_provider_unvalidated_status() -> None:
    html = '<script>let data = [{"date":"2020-05-01","t":7.5},{"date":"2020-05-02","t":null}];</script>'
    result = parse_embedded_daily(html, "mtl_b")
    assert len(result) == 1
    assert result.iloc[0]["qualifier"] == "P"
    assert result.iloc[0]["provider_quality_status"] == "not_validated_or_checked"
