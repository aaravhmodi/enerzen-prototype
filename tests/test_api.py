from fastapi import HTTPException

from api.main import OptimizeRequest, ProjectSpecIn, SiteSpecIn, run_optimize


def test_optimize_rejects_site_that_cannot_fit():
    spec = ProjectSpecIn(
        typology="single_family",
        floor_area_m2=150,
        storeys=2,
        orientation="S",
        window_to_wall_ratio=0.2,
        budget_per_unit=800000,
        target_label="nzr",
        location="Toronto",
        footprint_length_m=20,
        footprint_width_m=10,
    )
    site = SiteSpecIn(lot_width_m=12, lot_depth_m=15, street_side="N")

    try:
        run_optimize(OptimizeRequest(spec=spec, site=site))
    except HTTPException as error:
        assert error.status_code == 422
        assert "Site feasibility gate failed" in str(error.detail)
    else:
        raise AssertionError("Expected the site feasibility gate to reject the request")
