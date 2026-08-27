import unittest

from live_splitter.models import ABSOLUTE_MAX_BYTES, SplitConfig
from live_splitter.utils import format_timestamp, safe_name


class UtilsTests(unittest.TestCase):
    def test_timestamp_supports_long_lives(self) -> None:
        self.assertEqual(format_timestamp(5538), "01:32:18")

    def test_safe_name_removes_windows_invalid_characters(self) -> None:
        self.assertEqual(safe_name('live: 1/"teste"'), "live_ 1__teste_")

    def test_size_limit_is_strictly_below_256_mb(self) -> None:
        with self.assertRaises(ValueError):
            SplitConfig(max_bytes=ABSOLUTE_MAX_BYTES).validate()


if __name__ == "__main__":
    unittest.main()
