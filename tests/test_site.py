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
from engine.site_geometry import build_site_geometry


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
        self.assertIn('id="porch-1"', svg)
        self.assertIn('id="building-entrance-1"', svg)
        self.assertIn("Garden Suite", svg)
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

    def test_development_geometry_is_coherent_and_inside_lot(self):
        site = SiteSpec(lot_width_m=30.0, lot_depth_m=50.0, street_side="N")
        mix = {"garden_suite": 2, "three_bhk": 1}
        placements = place_units(mix, site)
        parking = [(1.2, 0.25, 2.55, 5.5), (3.9, 0.25, 2.55, 5.5), (20.7, 0.25, 2.55, 5.5)]
        geometry = build_site_geometry(placements, site, parking)

        self.assertTrue(geometry.lot_boundary.is_valid)
        self.assertTrue(geometry.buildable_envelope.within(geometry.lot_boundary))
        self.assertTrue(all(building.within(geometry.lot_boundary) for building in geometry.buildings))
        self.assertTrue(all(stall.within(geometry.lot_boundary) for stall in geometry.parking))
        self.assertIsNotNone(geometry.vehicle_access)
        self.assertGreaterEqual(len(geometry.trees), 2)
        self.assertTrue(all(geometry.shared_green.contains(tree) for tree in geometry.trees))
        self.assertTrue(geometry.rain_garden.within(geometry.shared_green))

    def test_walkway_never_crosses_a_building(self):
        site = SiteSpec(lot_width_m=30.0, lot_depth_m=50.0, street_side="N")
        placements = place_units({"garden_suite": 12}, site)
        geometry = build_site_geometry(placements, site, [])

        self.assertEqual(len(placements), 12)
        self.assertTrue(all(not geometry.pedestrian_spine.intersects(b.buffer(-0.01)) for b in geometry.buildings))

    def test_entrances_and_paths_avoid_parking_and_buildings(self):
        from engine.multi_site import _parking_spaces
        site = SiteSpec(lot_width_m=30.0, lot_depth_m=50.0, street_side="N")
        mix = {"garden_suite": 2, "three_bhk": 1}
        placements = place_units(mix, site)
        geometry = build_site_geometry(placements, site, _parking_spaces(3, site))

        self.assertTrue(geometry.parking)
        self.assertFalse(any(porch.intersects(stall) for porch in geometry.porches for stall in geometry.parking))
        self.assertTrue(geometry.entry_paths)
        self.assertFalse(any(path.intersects(b.buffer(-0.01)) for path in geometry.entry_paths for b in geometry.buildings))

    def test_townhouse_row_door_is_on_a_long_face(self):
        site = SiteSpec(lot_width_m=60.0, lot_depth_m=40.0, street_side="W")
        placements = place_units({"townhouse": 6}, site)
        geometry = build_site_geometry(placements, site, [])
        min_x, min_y, max_x, max_y = geometry.buildings[0].bounds
        door = geometry.entrances[0]

        self.assertGreater(max_x - min_x, max_y - min_y)
        self.assertTrue(abs(door.y - min_y) < 1e-6 or abs(door.y - max_y) < 1e-6)

    def test_shared_green_uses_the_rear_yard(self):
        site = SiteSpec(lot_width_m=30.0, lot_depth_m=50.0, street_side="N")
        geometry = build_site_geometry(place_units({"garden_suite": 2}, site), site, [])

        min_x, min_y, max_x, max_y = geometry.shared_green.bounds
        self.assertGreater(min_y, 50.0 - site.rear_setback_m)
        self.assertGreater(max_x - min_x, 20.0)
        self.assertEqual(len(geometry.entrances), len(geometry.buildings))
        self.assertEqual(len(geometry.porches), len(geometry.buildings))


if __name__ == "__main__":
    unittest.main()
