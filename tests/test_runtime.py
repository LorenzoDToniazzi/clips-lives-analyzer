import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from live_splitter.runtime import data_directory


class RuntimeTests(unittest.TestCase):
    def test_uses_configured_data_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "dados"
            with patch.dict(
                "os.environ",
                {"LIVE_SPLITTER_DATA_DIR": str(target)},
                clear=False,
            ):
                self.assertEqual(data_directory(), target)
                self.assertTrue(target.is_dir())


if __name__ == "__main__":
    unittest.main()
