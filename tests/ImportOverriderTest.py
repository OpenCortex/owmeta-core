from .DataTestTemplate import _DataTest
try:
    from unittest.mock import patch, Mock
except ImportError:
    from mock import patch, Mock
from owmeta_core.import_override import Overrider
import pytest


class OverriderTest(_DataTest):
    def setUp(self):
        self.overrider_patch = patch('owmeta_core.Overrider.instance', None)
        self.overrider_patch.start()

    def tearDown(self):
        self.overrider_patch.stop()

    def test_overrider_reuse(self):
        m = Mock()
        Overrider(m)
        with self.assertRaises(Exception):
            Overrider(m)
