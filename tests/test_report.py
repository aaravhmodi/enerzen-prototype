import base64
from io import BytesIO

import pytest
from fastapi import HTTPException

import api.main as api_main
from api.main import (DevOptimizeRequest, DevReportRequest, DevSpecIn, ProjectSpecIn, ReportRequest, SiteSpecIn,
                      run_dev_report, run_dev_scenarios, run_report)
from engine import feasibility as fz


def _checks(*statuses):
    return [fz.Check(f"check {i}", s, "detail") for i, s in enumerate(statuses)]


def test_every_check_passing_is_feasible():
    assert fz.assess(_checks(fz.PASS, fz.PASS)).status == fz.FEASIBLE


def test_a_relaxed_constraint_is_feasible_with_modifications_and_named():
    result = fz.assess(_checks(fz.PASS), relaxed=["budget raised to $520,000"])
    assert result.status == fz.FEASIBLE_WITH_MODIFICATIONS
    assert "budget raised to $520,000" in result.reasons[0]


def test_an_unchecked_or_failed_check_requires_further_study():
    assert fz.assess(_checks(fz.PASS, fz.NOT_CHECKED)).status == fz.FURTHER_STUDY
    assert fz.assess(_checks(fz.FAIL), relaxed=["anything"]).status == fz.FURTHER_STUDY


def test_zoning_is_never_claimed_as_checked():
    check = fz.zoning_check("Pickering (Dunbarton)")
    assert check.status == fz.NOT_CHECKED and "No Pickering parcel" in check.detail


def test_objective_ranks_share_ties_and_respect_direction():
    class R:
        def __init__(self, cost, homes):
            self.cost, self.homes = cost, homes
    feasible = [R(10, 5), R(20, 8), R(10, 3)]
    ranks = fz.objective_ranks(feasible[0], feasible, [("Cost", "cost", "cost", False, str),
                                                       ("Yield", "yield", "homes", True, str)])
    assert [r["rank"] for r in ranks] == [1, 2]


def _unit_spec(**overrides):
    base = dict(typology="single_family", floor_area_m2=150, storeys=2, orientation="S", window_to_wall_ratio=0.2,
                budget_per_unit=500_000, target_label="nzr", location="Pickering (Dunbarton)",
                footprint_length_m=12, footprint_width_m=8)
    base.update(overrides)
    return ProjectSpecIn(**base)


def _pdf_text(b64: str) -> str:
    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(BytesIO(base64.b64decode(b64)))
    return " ".join(page.extract_text() for page in reader.pages)


def test_unit_report_has_every_section_and_names_the_status():
    pdf = run_report(ReportRequest(spec=_unit_spec(), site=SiteSpecIn(lot_width_m=20, lot_depth_m=30,
                                                                       street_side="N")))["pdf_b64"]
    assert base64.b64decode(pdf).startswith(b"%PDF")
    text = _pdf_text(pdf)
    for n, section in enumerate(fz.SECTIONS, 1):
        assert f"{n}. {section}" in text
    assert fz.FURTHER_STUDY in text


def test_site_fit_failure_is_reported_not_refused(monkeypatch):
    captured = {}
    monkeypatch.setattr(api_main, "generate_unit_report", lambda **kw: captured.update(kw) or b"%PDF")
    run_report(ReportRequest(spec=_unit_spec(footprint_length_m=20, footprint_width_m=10),
                             site=SiteSpecIn(lot_width_m=12, lot_depth_m=15, street_side="N")))
    site = next(c for c in captured["assessment"].checks if c.name == "Site fit")
    assert site.status == fz.FAIL
    assert captured["assessment"].status == fz.FURTHER_STUDY
    assert any("site-fit failure" in step for step in captured["steps"])


def test_unit_report_without_a_site_marks_site_fit_not_checked(monkeypatch):
    captured = {}
    monkeypatch.setattr(api_main, "generate_unit_report", lambda **kw: captured.update(kw) or b"%PDF")
    run_report(ReportRequest(spec=_unit_spec()))
    site = next(c for c in captured["assessment"].checks if c.name == "Site fit")
    assert site.status == fz.NOT_CHECKED
    assert all(r["rank"] >= 1 for r in captured["ranks"])


DEV = dict(lot_width_m=30, lot_depth_m=50, total_budget_cad=1_500_000, location="Pickering (Dunbarton)",
           allowed_types=["garden_suite", "three_bhk"], weights={"yield": 100, "cost": 0, "energy": 0, "carbon": 0})


def test_development_report_has_every_section():
    spec = DevSpecIn(**DEV)
    mixes = [s["units"] for s in run_dev_scenarios(DevOptimizeRequest(spec=spec, top_n=3))["scenarios"]]
    text = _pdf_text(run_dev_report(DevReportRequest(spec=spec, mixes=mixes))["pdf_b64"])
    for n, section in enumerate(fz.SECTIONS, 1):
        assert f"{n}. {section}" in text
    assert "Green-space strategy" in text and fz.FURTHER_STUDY in text


def test_development_report_refuses_a_mix_outside_the_approved_set():
    spec = DevSpecIn(**DEV)
    with pytest.raises(HTTPException) as err:
        run_dev_report(DevReportRequest(spec=spec, mixes=[{"garden_suite": 1}], mix={"three_bhk": 1}))
    assert err.value.status_code == 422
