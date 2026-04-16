from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from src.app.domains.smart_home.payloads import build_smart_home_command


class SmartHomePayloadsTest(unittest.TestCase):
    def test_builds_aircon_temperature_content_from_action_template(self) -> None:
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
                        actions:
                          set_temperature:
                            template: "{device_id}:set_temperature:{temperature_c}"
                            label: "온도 설정"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            command = build_smart_home_command(
                "smarthome.aircon.set_temperature",
                payload={"temperature_c": 28},
                devices_path=str(config_path),
            )

        self.assertEqual(command.content, "aircon.living_room:set_temperature:28")
        self.assertEqual(command.action_label, "온도 설정")
        self.assertEqual(command.params["temperature_c"], 28)

    def test_missing_template_param_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "devices.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    devices:
                      aircon:
                        id: "aircon.living_room"
                        name: "에어컨"
                        actions:
                          set_temperature:
                            template: "{device_id}:set_temperature:{temperature_c}"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                build_smart_home_command(
                    "smarthome.aircon.set_temperature",
                    payload={},
                    devices_path=str(config_path),
                )


if __name__ == "__main__":
    unittest.main()
