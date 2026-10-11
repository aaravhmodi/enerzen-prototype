from api.main import (DevOptimizeRequest, DevReportRequest, DevSitePlanRequest, DevSpecIn, ProjectSpecIn,
                      ReportRequest, SitePlanRequest, SiteSpecIn, run_dev_report, run_dev_scenarios,
                      run_dev_site_plan, run_report, run_site_plan)
from engine.units import IMPERIAL, Units
from tests.test_report import DEV, _pdf_text, _unit_spec

SITE = dict(lot_width_m=20, lot_depth_m=30, street_side="N")


def test_metric_is_the_default_and_keeps_si_values():
    u = Units()
    assert u.dims(20, 30) == "20 x 30 m"
    assert u.area(150) == "150 m2"
    assert u.eui(62.4) == "62.4 kWh/m2/yr"
    assert u.pressure(1.1) == "1.1 kPa"


def test_imperial_converts_lengths_areas_loads_and_intensities():
    u = Units(IMPERIAL)
    assert u.dims(20, 30) == "65.6 x 98.4 ft"
    assert u.area(150) == "1,615 sq ft"
    assert u.eui(62.4) == "5.8 kWh/sq ft/yr"
    assert u.pressure(1.1) == "23 psf"
    assert u.volume(10) == "13.1 cu yd"


def test_site_plan_dimensions_follow_the_requested_units():
    spec, site = ProjectSpecIn(**_unit_spec().model_dump()), SiteSpecIn(**SITE)
    metric = run_site_plan(SitePlanRequest(spec=spec, site=site))["svg"]
    imperial = run_site_plan(SitePlanRequest(spec=spec, site=site, units="imperial"))["svg"]
    assert "20 × 30 m" in metric and " ft" not in metric
    assert "65.6 × 98.4 ft" in imperial and "20 × 30 m" not in imperial


def test_development_site_plan_dimensions_follow_the_requested_units():
    spec = DevSpecIn(**DEV)
    mix = run_dev_scenarios(DevOptimizeRequest(spec=spec, top_n=1))["scenarios"][0]["units"]
    svg = run_dev_site_plan(DevSitePlanRequest(spec=spec, mix=mix, units="imperial"))["svg"]
    assert f"{Units(IMPERIAL).dims(spec.lot_width_m, spec.lot_depth_m, sep=' × ')}" in svg


def test_reports_follow_the_requested_units():
    metric = _pdf_text(run_report(ReportRequest(spec=_unit_spec(), site=SiteSpecIn(**SITE)))["pdf_b64"])
    imperial = _pdf_text(run_report(ReportRequest(spec=_unit_spec(), site=SiteSpecIn(**SITE),
                                                  units="imperial"))["pdf_b64"])
    assert "150 m2 conditioned" in metric and "kWh/m2/yr" in metric and "sq ft" not in metric
    assert "1,615 sq ft conditioned" in imperial and "kWh/sq ft/yr" in imperial
    # The one kPa left is the catalog's own name for the snow tier, "Option 1 (ground Ss <= 2.5 kPa)".
    assert "m2" not in imperial and "psf bearing" in imperial and imperial.count("kPa") == 1

    spec = DevSpecIn(**DEV)
    mixes = [s["units"] for s in run_dev_scenarios(DevOptimizeRequest(spec=spec, top_n=2))["scenarios"]]
    dev = _pdf_text(run_dev_report(DevReportRequest(spec=spec, mixes=mixes, units="imperial"))["pdf_b64"])
    assert "sq ft" in dev and "m2" not in dev and "kPa" not in dev
