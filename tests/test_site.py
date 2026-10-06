import unittest
from dataclasses import dataclass
from typing import Optional

from engine.site import (
    SiteSpec,
    place_building,
    solar_score_for_orientation,
    site_plan_svg,
)
from engine.multi_site import multi_site_plan_svg, place_units


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
        # Large enough in both axes that front+rear+2*side setbacks clear the
        # footprint regardless of which axis the street-facing setback lands on.
        spec = FakeSpec(orientation="S", footprint_length_m=12.0, footprint_width_m=8.0)
        for side in ("N", "S", "E", "W"):
            site = SiteSpec(lot_width_m=30.0, lot_depth_m=30.0, street_side=side)
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
        self.assertIn("Solar score", svg)

    def test_development_svg_includes_concept_site_layers(self):
        site = SiteSpec(lot_width_m=30.0, lot_depth_m=50.0, street_side="N")
        mix = {"garden_suite": 2}
        svg = multi_site_plan_svg(place_units(mix, site), site, mix)

        self.assertIn('id="pedestrian-walkway"', svg)
        self.assertIn('id="shared-green-space"', svg)
        self.assertIn('id="public-sidewalk"', svg)
        self.assertIn('id="vehicle-access"', svg)
        self.assertIn('id="rain-garden"', svg)
        self.assertIn('id="tree-1"', svg)
        self.assertIn("Shared green / amenity", svg)

    def test_development_layout_uses_a_shared_spine(self):
        site = SiteSpec(lot_width_m=30.0, lot_depth_m=50.0, street_side="N")
        placements = place_units({"garden_suite": 2, "three_bhk": 1}, site)

        self.assertEqual(len(placements), 3)
        # The central access spine remains open between the two building bands.
        for placement in placements:
            self.assertTrue(placement.x_m + placement.w_m <= 13.2 or placement.x_m >= 16.8)

    def test_development_layout_rotates_for_east_facing_scheme(self):
        south = SiteSpec(lot_width_m=30.0, lot_depth_m=50.0, street_side="N", solar_orientation="S")
        east = SiteSpec(lot_width_m=30.0, lot_depth_m=50.0, street_side="N", solar_orientation="E")

        south_unit = place_units({"garden_suite": 1}, south)[0]
        east_unit = place_units({"garden_suite": 1}, east)[0]

        self.assertAlmostEqual(south_unit.w_m, 7.0)
        self.assertAlmostEqual(east_unit.w_m, 6.5)

    def test_development_svg_reserves_concept_parking_when_frontage_allows(self):
        site = SiteSpec(lot_width_m=30.0, lot_depth_m=50.0, street_side="N")
        mix = {"garden_suite": 2, "three_bhk": 1}
        svg = multi_site_plan_svg(place_units(mix, site), site, mix)

        self.assertIn('id="parking-space-1"', svg)
        self.assertIn('id="parking-space-3"', svg)
        self.assertIn("3 concept stalls", svg)

    def test_development_svg_states_when_parking_cannot_fit(self):
        site = SiteSpec(lot_width_m=6.5, lot_depth_m=15.0, street_side="N")
        mix = {"garden_suite": 2}
        svg = multi_site_plan_svg(place_units(mix, site), site, mix)

        self.assertNotIn('id="parking-space-1"', svg)
        self.assertIn("Not allocated on supplied lot", svg)


if __name__ == "__main__":
    unittest.main()
