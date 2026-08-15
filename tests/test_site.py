import unittest
from dataclasses import dataclass
from typing import Optional

from engine.site import (
    SiteSpec,
    place_building,
    solar_score_for_orientation,
    site_plan_svg,
)


@dataclass
class FakeSpec:
    orientation: str
    footprint_length_m: Optional[float] = None
    footprint_width_m: Optional[float] = None
    floor_area_m2: float = 150.0


class SolarScoreTests(unittest.TestCase):
    def test_south_is_perfect(self):
        self.assertEqual(solar_score_for_orientation("S"), 1.0)

    def test_north_is_worst(self):
        self.assertEqual(solar_score_for_orientation("N"), 0.0)

    def test_east_west_are_midpoint(self):
        self.assertEqual(solar_score_for_orientation("E"), 0.5)
        self.assertEqual(solar_score_for_orientation("W"), 0.5)

    def test_invalid_orientation_raises(self):
        with self.assertRaises(ValueError):
            solar_score_for_orientation("NE")


class PlaceBuildingTests(unittest.TestCase):
    def test_ample_lot_fits_and_centers(self):
        spec = FakeSpec(orientation="S", footprint_length_m=12.0, footprint_width_m=8.0)
        site = SiteSpec(lot_width_m=20.0, lot_depth_m=30.0, street_side="N")
        layout = place_building(spec, site)

        self.assertTrue(layout.fits_on_lot)
        self.assertTrue(layout.setbacks_ok)
        self.assertEqual(layout.orientation, "S")
        self.assertAlmostEqual(layout.solar_score, 1.0)
        # South orientation -> long dimension (12m) runs east-west
        self.assertAlmostEqual(layout.building_w_m, 12.0)
        self.assertAlmostEqual(layout.building_h_m, 8.0)

        envelope_x0, envelope_x1 = site.side_setback_m, site.lot_width_m - site.side_setback_m
        self.assertGreaterEqual(layout.building_x_m, envelope_x0)
        self.assertLessEqual(layout.building_x_m + layout.building_w_m, envelope_x1)

    def test_narrow_lot_flags_overflow(self):
        spec = FakeSpec(orientation="S", footprint_length_m=20.0, footprint_width_m=10.0)
        site = SiteSpec(lot_width_m=12.0, lot_depth_m=15.0, street_side="N")
        layout = place_building(spec, site)

        self.assertFalse(layout.fits_on_lot)
        self.assertFalse(layout.setbacks_ok)
        self.assertTrue(layout.notes)

    def test_east_orientation_swaps_axes(self):
        spec = FakeSpec(orientation="E", footprint_length_m=12.0, footprint_width_m=8.0)
        site = SiteSpec(lot_width_m=20.0, lot_depth_m=30.0, street_side="N")
        layout = place_building(spec, site)

        # East orientation -> long dimension (12m) runs north-south
        self.assertAlmostEqual(layout.building_w_m, 8.0)
        self.assertAlmostEqual(layout.building_h_m, 12.0)
        self.assertAlmostEqual(layout.solar_score, 0.5)

    def test_derives_footprint_from_floor_area_when_missing(self):
        spec = FakeSpec(orientation="S", floor_area_m2=100.0)
        site = SiteSpec(lot_width_m=20.0, lot_depth_m=30.0, street_side="N")
        layout = place_building(spec, site)
        self.assertTrue(layout.fits_on_lot)
        self.assertAlmostEqual(layout.building_w_m, 10.0)
        self.assertAlmostEqual(layout.building_h_m, 10.0)

    def test_driveway_stays_within_lot_bounds(self):
        spec = FakeSpec(orientation="S", footprint_length_m=12.0, footprint_width_m=8.0)
        site = SiteSpec(lot_width_m=20.0, lot_depth_m=30.0, street_side="N")
        layout = place_building(spec, site)
        for x, y in layout.driveway_points_m:
            self.assertGreaterEqual(x, 0.0)
            self.assertLessEqual(x, site.lot_width_m)
            self.assertGreaterEqual(y, 0.0)
            self.assertLessEqual(y, site.lot_depth_m)

    def test_all_street_sides_produce_valid_layout(self):
        spec = FakeSpec(orientation="S", footprint_length_m=12.0, footprint_width_m=8.0)
        for side in ("N", "S", "E", "W"):
            site = SiteSpec(lot_width_m=20.0, lot_depth_m=30.0, street_side=side)
            layout = place_building(spec, site)
            self.assertTrue(layout.fits_on_lot, f"street_side={side}")


class SitePlanSvgTests(unittest.TestCase):
    def test_svg_is_well_formed_and_contains_key_elements(self):
        spec = FakeSpec(orientation="S", footprint_length_m=12.0, footprint_width_m=8.0)
        site = SiteSpec(lot_width_m=20.0, lot_depth_m=30.0, street_side="N")
        layout = place_building(spec, site)
        svg = site_plan_svg(layout, spec, site)

        self.assertTrue(svg.startswith("<svg"))
        self.assertTrue(svg.endswith("</svg>"))
        self.assertIn("<polygon", svg)  # driveway
        self.assertIn("solar score", svg)


if __name__ == "__main__":
    unittest.main()
