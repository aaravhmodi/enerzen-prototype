import pytest
import io
import json
import api.main as api_main

from fastapi import HTTPException

from api.main import OptimizeRequest, ProjectSpecIn, ReportRequest, SiteSpecIn, run_optimize, run_report, zoning_lookup
from engine import regulatory


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


def test_zoning_lookup_returns_municipal_attributes(monkeypatch):
    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    payload = {
        "features": [
            {
                "attributes": {
                    "ADDRESS_F": "123 Example St",
                    "ZN_STRING": "R 2.5",
                    "HT_STRING": "10.0",
                }
            }
        ]
    }
    monkeypatch.setattr(
        regulatory,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(json.dumps(payload).encode()),
    )

    result = zoning_lookup("Toronto", 43.65, -79.38)

    assert result["status"] == "available"
    assert result["parcel"]["address"] == "123 Example St"
    assert result["parcel"]["zoning"] == "R 2.5"


def test_zoning_lookup_does_not_call_unconfigured_municipality(monkeypatch):
    monkeypatch.setattr(regulatory, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))

    result = zoning_lookup("Ottawa", 45.42, -75.69)

    assert result["status"] == "not_available"


def test_optimize_can_lock_mechanical_system():
    spec = ProjectSpecIn(
        typology="single_family",
        floor_area_m2=150,
        storeys=2,
        orientation="S",
        window_to_wall_ratio=0.2,
        budget_per_unit=800000,
        target_label="nzr",
        location="Toronto",
        mechanical_option_id="M2",
    )

    result = run_optimize(OptimizeRequest(spec=spec, top_n=5))

    assert result["results"]
    assert {item["mechanical_id"] for item in result["results"]} == {"M2"}


def test_optimize_rejects_gas_selection_when_gas_is_disabled():
    spec = ProjectSpecIn(
        typology="single_family",
        floor_area_m2=150,
        storeys=2,
        orientation="S",
        window_to_wall_ratio=0.2,
        budget_per_unit=800000,
        target_label="nzr",
        location="Toronto",
        allow_gas=False,
        mechanical_option_id="M1",
    )

    try:
        run_optimize(OptimizeRequest(spec=spec))
    except HTTPException as error:
        assert error.status_code == 422
        assert "gas systems are disabled" in str(error.detail)
    else:
        raise AssertionError("Expected incompatible mechanical selection to be rejected")


def test_report_uses_selected_weights_and_site(monkeypatch):
    captured = {}
    spec = ProjectSpecIn(
        typology="single_family",
        floor_area_m2=150,
        storeys=2,
        orientation="S",
        window_to_wall_ratio=0.2,
        budget_per_unit=800000,
        target_label="nzr",
        location="Toronto",
        footprint_length_m=10,
        footprint_width_m=8,
    )
    site = SiteSpecIn(lot_width_m=20, lot_depth_m=30, street_side="N")
    weights = {"cost": 0.6, "speed": 0.1, "carbon": 0.2, "energy": 0.1}

    def fake_optimize(project_spec, selected_weights):
        captured["weights"] = selected_weights
        return [], {"evaluated": 0, "passed": 0, "over_budget": 0, "missed_target": 0}

    monkeypatch.setattr(api_main, "optimize_with_gate", fake_optimize)

    with pytest.raises(HTTPException):
        run_report(ReportRequest(spec=spec, site=site, weights=weights))
    # The report rescales weights to sum to 1, which can leave float noise.
    assert captured["weights"] == pytest.approx(weights)
