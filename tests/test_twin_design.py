from __future__ import annotations

from stream_recoverability.experiments.synthetic_river import (
    catalog,
    twin_a_interior_dam_chain,
    twin_a_interior_dam_confluence,
    twin_b_ordinary_endpoint_chain,
    twin_b_ordinary_endpoint_confluence,
    twin_c_endpoint_dam_chain,
    twin_catalog,
    twin_d_ordinary_interior_chain,
)
from stream_recoverability.experiments.twin_design import (
    graph_neighbors,
    multi_graph_suite,
    score_twin_nodes,
    uniqueness_margin,
)


CATALOG_NAMES = {
    "memory_dominant",
    "donor_dominant",
    "high_donor_and_high_memory",
    "endpoint_upstream_origin",
    "endpoint_downstream_terminus",
    "donor_count_redundant",
    "advection_chain",
}


def test_catalog_excludes_twins_and_keeps_e0_names() -> None:
    names = set(catalog())
    assert names == CATALOG_NAMES
    assert not any(name.startswith("twin_") for name in names)
    assert set(twin_catalog()) >= {
        "twin_a_interior_dam_chain_n6",
        "twin_b_ordinary_endpoint_chain_n6",
        "twin_a_interior_dam_confluence_n6",
        "twin_b_ordinary_endpoint_confluence_n6",
        "twin_c_endpoint_dam_chain_n6",
        "twin_d_ordinary_interior_chain_n6",
    }


def test_twin_a_interior_dam_is_not_endpoint_and_has_both_directions() -> None:
    river = twin_a_interior_dam_chain()
    dam = int(river.dam_like_index)
    assert river.n_stations >= 5
    assert 0 < dam < river.n_stations - 1
    neighbors = graph_neighbors(river, dam)
    assert len(neighbors) >= 2
    assert min(neighbors) < dam < max(neighbors)


def test_suite_includes_a_confluence_tree() -> None:
    rivers = multi_graph_suite()
    assert any("confluence" in river.name for river in rivers)
    tree = twin_a_interior_dam_confluence()
    dam = int(tree.dam_like_index)
    assert len(graph_neighbors(tree, dam)) >= 3
    endpoint = twin_b_ordinary_endpoint_confluence()
    assert endpoint.dam_like_index is None
    assert endpoint.ordinary_endpoint == 0


def test_twin_a_dam_has_higher_operator_risk_than_bidirectional_neighbors() -> None:
    river = twin_a_interior_dam_chain()
    scores = score_twin_nodes(river)
    dam = int(river.dam_like_index)
    neighbors = graph_neighbors(river, dam)
    dam_risk = float(scores.loc[scores["node"].eq(dam), "operator_risk"].iloc[0])
    dam_r = float(scores.loc[scores["node"].eq(dam), "recoverability_r"].iloc[0])
    for neighbor in neighbors:
        neighbor_risk = float(
            scores.loc[scores["node"].eq(neighbor), "operator_risk"].iloc[0]
        )
        neighbor_r = float(
            scores.loc[scores["node"].eq(neighbor), "recoverability_r"].iloc[0]
        )
        assert dam_risk > neighbor_risk
        assert dam_r < neighbor_r
    assert bool(scores.loc[scores["node"].eq(dam), "is_dam_like"].iloc[0])
    assert not bool(scores.loc[scores["node"].eq(dam), "one_sided_donors"].iloc[0])


def test_twin_b_endpoint_not_uniquely_selected_the_way_donor_r2_selects_it() -> None:
    river = twin_b_ordinary_endpoint_chain()
    scores = score_twin_nodes(river)
    endpoint = int(river.ordinary_endpoint)
    donor_r2 = scores["donor_r2"].to_numpy(dtype=float)
    operator_risk = scores["operator_risk"].to_numpy(dtype=float)
    assert int(scores.loc[scores["donor_r2"].idxmin(), "node"]) == endpoint
    assert uniqueness_margin(donor_r2, endpoint, higher=False) > 0.0
    operator_margin = uniqueness_margin(operator_risk, endpoint, higher=True)
    donor_margin = uniqueness_margin(donor_r2, endpoint, higher=False)
    assert operator_margin < donor_margin
    twin_a = score_twin_nodes(twin_a_interior_dam_chain())
    dam_risk = float(
        twin_a.loc[twin_a["is_dam_like"], "operator_risk"].iloc[0]
    )
    endpoint_risk = float(
        scores.loc[scores["node"].eq(endpoint), "operator_risk"].iloc[0]
    )
    assert endpoint_risk < dam_risk
    assert bool(scores.loc[scores["node"].eq(endpoint), "one_sided_donors"].iloc[0])
    assert not bool(scores.loc[scores["node"].eq(endpoint), "is_dam_like"].iloc[0])


def test_two_by_two_cells_exist() -> None:
    dam_endpoint = twin_c_endpoint_dam_chain()
    ordinary_interior = twin_d_ordinary_interior_chain()
    assert dam_endpoint.dam_like_index == 0
    assert ordinary_interior.dam_like_index is None
    assert ordinary_interior.ordinary_interior == ordinary_interior.n_stations // 2
    assert 0 < ordinary_interior.ordinary_interior < ordinary_interior.n_stations - 1
    families = {river.name.split("_")[1] for river in multi_graph_suite()}
    assert families >= {"a", "b", "c", "d"}
