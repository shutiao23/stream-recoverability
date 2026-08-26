from stream_recoverability.data.nwis_temperature import read_rdb
from stream_recoverability.data.public_river_inventory import river_name_from_site_name


def test_river_name_from_common_usgs_titles() -> None:
    assert river_name_from_site_name("Delaware River at Trenton NJ") == "Delaware River"
    assert (
        river_name_from_site_name("Colorado River below Glen Canyon Dam, AZ")
        == "Colorado River"
    )
    assert (
        river_name_from_site_name("Willamette River at Portland, OR")
        == "Willamette River"
    )
    assert river_name_from_site_name("Suwannee River near Wilcox, FL") == "Suwannee River"


def test_read_rdb_skips_comment_and_width_rows() -> None:
    text = """# comment
agency_cd\tsite_no
5s\t15s
USGS\t14152000
"""
    frame = read_rdb(text)
    assert list(frame["site_no"]) == ["14152000"]
