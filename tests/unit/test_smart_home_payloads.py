from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from src.app.domains.smart_home.payloads import build_smart_home_command


class SmartHomePayloadsTest(unittest.TestCase):
    def test_builds_aircon_on_content_from_device_template(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "devices.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    devices:
                      aircon:
                        id: "aircon.living_room"
                        name: "에어컨"
                        template: "{device_id}:{action}"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            command = build_smart_home_command(
                "smarthome.aircon.on",
                payload={},
                devices_path=str(config_path),
            )

        self.assertEqual(command.content, "aircon.living_room:on")
        self.assertEqual(command.display_name, "에어컨")

    def test_missing_template_param_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "devices.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    devices:
                      tv:
                        id: "tv.living_room"
                        name: "TV"
                        template: "{device_id}:{action}:{missing}"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                build_smart_home_command(
                    "smarthome.tv.on",
                    payload={},
                    devices_path=str(config_path),
                )


if __name__ == "__main__":
    unittest.main()
