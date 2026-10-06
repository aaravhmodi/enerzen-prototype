import base64
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from engine.ai import generate_development_concept_render


class _FakeImages:
    def edit(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(b"rendered").decode("ascii"))])


class _FakeClient:
    def __init__(self):
        self.images = _FakeImages()


class DevelopmentConceptRenderTests(unittest.TestCase):
    def test_render_uses_verified_svg_as_reference(self):
        client = _FakeClient()
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><rect width="20" height="20"/></svg>'

        with patch("engine.ai._get_client", return_value=client):
            result = generate_development_concept_render(svg, {"garden_suite": 2})

        self.assertEqual(result, b"rendered")
        self.assertEqual(client.images.kwargs["image"][0], "verified-site-plan.png")
        self.assertEqual(client.images.kwargs["image"][2], "image/png")
        self.assertIn("strict spatial blueprint", client.images.kwargs["prompt"])


if __name__ == "__main__":
    unittest.main()
