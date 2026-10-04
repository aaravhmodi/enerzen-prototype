import io
import json

from fastapi import HTTPException

from api.main import OptimizeRequest, ProjectSpecIn, SiteSpecIn, run_optimize, zoning_lookup
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
