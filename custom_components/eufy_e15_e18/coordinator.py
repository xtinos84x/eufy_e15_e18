"""DataUpdateCoordinator for Eufy Robomow."""
from __future__ import annotations

import logging
import time
from datetime import timedelta

import tinytuya

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    TUYA_VERSION,
    POLL_INTERVAL,
    CLOUD_POLL_INTERVAL,
    CLOUD_EDGE_MM,
    CLOUD_PATH_MM,
    CLOUD_TRAVEL_SPEED,
    CLOUD_BLADE_SPEED,
    CLOUD_PAD_DIRECTION,
    DP_ROBOT_STATUS,
    DP_WIFI_SIGNAL_STRENGTH,
    DP_FAULT_TYPE,
    FAUL_TYPE_OPTIONS,
    DP_ADVANCED_SETTINGS,
    MOWER_STATE, 
)

_LOGGER = logging.getLogger(__name__)

# After this many consecutive local-poll errors we recreate the tinytuya
# Device object to flush any stale socket / connection state.
_MAX_CONSECUTIVE_ERRORS = 5

# Keys kept across polls even when a fresh cloud fetch fails
_CLOUD_KEYS = (
    CLOUD_EDGE_MM,
    CLOUD_PATH_MM,
    CLOUD_TRAVEL_SPEED,
    CLOUD_BLADE_SPEED,
    CLOUD_PAD_DIRECTION,
)


class EufyMowerCoordinator(DataUpdateCoordinator[dict]):
    """Polls the Eufy E15 via Tuya local protocol every POLL_INTERVAL seconds.

    If an EufyCloudClient is provided, cloud settings (DP155) are also polled,
    but only once every CLOUD_POLL_INTERVAL seconds to avoid hammering the API.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        device_id: str,
        local_key: str,
        cloud_client=None,   # EufyCloudClient | None  (avoid circular import)
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=POLL_INTERVAL),
        )
        self.host = host
        self.device_id = device_id
        self.local_key = local_key
        self.cloud_client = cloud_client

        self._device = self._make_device()
        # Use float('-inf') so the first poll always fetches cloud settings
        self._cloud_last_fetch: float = float("-inf")
        # Track consecutive local-poll failures to know when to recreate the device
        self._consecutive_errors: int = 0

    def _make_device(self) -> tinytuya.Device:
        d = tinytuya.Device(
            self.device_id,
            self.host,
            self.local_key,
            version=TUYA_VERSION,
        )
        d.set_socketTimeout(5)
        # Non-persistent: close the TCP socket after every request.
        # Persistent mode (the default in some tinytuya versions) keeps the
        # socket open between polls.  When that socket silently dies it is never
        # freed, causing file-descriptor leaks and eventually OOM / CPU spikes.
        d.set_socketPersistent(False)
        return d

    # ── polling ───────────────────────────────────────────────────────────────

    async def _async_update_data(self) -> dict:
        """Fetch DPS from device (and optionally cloud settings)."""
        # ── 1. Local DPS (every POLL_INTERVAL seconds) ────────────────────────
        
        try:
            result = await self.hass.async_add_executor_job(self._device.status)
        except Exception as exc:  # noqa: BLE001
            # A Python exception from tinytuya (e.g. socket error, SSL error).
            # Increment the error counter; recreate the device object when the
            # threshold is reached so stale socket state is fully flushed.
            self._consecutive_errors += 1
            if self._consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                _LOGGER.debug(
                    "Recreating tinytuya device after %d consecutive errors",
                    self._consecutive_errors,
                )
                self._device = self._make_device()
                self._consecutive_errors = 0
            raise UpdateFailed(f"Tuya connection error: {exc}") from exc

        if "Error" in result:
            err = result["Error"]
            _LOGGER.debug("Tuya poll error: %s (%s)", err, result.get("Err"))
            self._consecutive_errors += 1
            if self._consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                _LOGGER.debug(
                    "Recreating tinytuya device after %d consecutive errors",
                    self._consecutive_errors,
                )
                self._device = self._make_device()
                self._consecutive_errors = 0
            raise UpdateFailed(f"Tuya error: {err}")

        # Successful poll — reset the error counter
        self._consecutive_errors = 0

        dps: dict = result.get("dps", {}) 


        # ── 2. Cloud settings (every CLOUD_POLL_INTERVAL seconds) ─────────────
        #dps: dict[str, Any] = {}
        if self.cloud_client is not None:
            _LOGGER.debug("cloud_client ok")
            try:
                dps_raw = await self.hass.async_add_executor_job(
                    self.cloud_client.get_dps
                )

                robot_status_raw = dps_raw.get(DP_ROBOT_STATUS)
                baterie_status_raw = dps_raw.get("108")
                robot_data = self.cloud_client.get_robot_status(robot_status_raw)
                dps.update(robot_data.copy())
                
                eufy_status_int = self.cloud_client.decode_eufy_status(robot_status_raw, baterie_status_raw)
                #dps[DP_ROBOT_STATUS] = eufy_status_int
                dps[DP_ROBOT_STATUS] = MOWER_STATE.get(int(eufy_status_int), "Unknown")
                
                wifi_signal_strength = dps_raw.get(DP_WIFI_SIGNAL_STRENGTH)
                dps[DP_WIFI_SIGNAL_STRENGTH] = wifi_signal_strength
                fault_type_code = dps_raw.get(DP_FAULT_TYPE)
                dps[DP_FAULT_TYPE] = FAUL_TYPE_OPTIONS.get(int(fault_type_code), "None")
                advancedSettingsRaw = dps_raw.get(DP_ADVANCED_SETTINGS)
                
                _LOGGER.debug("robot status: %s \n Wifi signal strength: %s \n fault type: %s - %s", dps[DP_ROBOT_STATUS], dps[DP_WIFI_SIGNAL_STRENGTH], fault_type_code, dps[DP_FAULT_TYPE])

            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning("Cloud DPS fetch failed: %s", exc)
            _LOGGER.debug("Cloud DPS fetched: %s", dps)
            now = time.monotonic()
            if now - self._cloud_last_fetch >= CLOUD_POLL_INTERVAL:
                try:
                    cloud_settings = await self.hass.async_add_executor_job(
                        self.cloud_client.get_settings
                    )
                    dps[CLOUD_EDGE_MM]       = cloud_settings["edge_mm"]
                    dps[CLOUD_PATH_MM]       = cloud_settings["path_mm"]
                    dps[CLOUD_TRAVEL_SPEED]  = cloud_settings["travel_speed"]
                    dps[CLOUD_BLADE_SPEED]   = cloud_settings["blade_speed"]
                    dps[CLOUD_PAD_DIRECTION] = cloud_settings["pad_direction"]
                    self._cloud_last_fetch = now
                    _LOGGER.debug("Cloud settings refreshed: %s", cloud_settings)
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.warning("Cloud settings fetch failed: %s", exc)
                    # Preserve the previous values so entities don't go unavailable
                    if self.data:
                        for key in _CLOUD_KEYS:
                            if key in self.data:
                                dps[key] = self.data[key]
            else:
                # Not yet due for a cloud refresh — carry forward previous values
                if self.data:
                    for key in _CLOUD_KEYS:
                        if key in self.data:
                            dps[key] = self.data[key]
        else:
            dps["fail"] = true
        return dps

    # ── commands ──────────────────────────────────────────────────────────────

    async def async_send_command(self, dp: str, value) -> bool:
        """Write a single DPS value to the device. Returns True on success."""
        _LOGGER.debug("Sending command DP %s = %s", dp, value)
        try:
            result = await self.hass.async_add_executor_job(
                self._device.set_value, int(dp), value
            )
            _LOGGER.debug("Command result: %s", result)
            # Immediately refresh state
            await self.async_request_refresh()
            return True
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("Command DP %s = %s failed: %s", dp, value, exc)
            return False

    async def async_set_cloud_setting(self, **kwargs) -> bool:
        """Write one or more cloud settings via the Tuya mobile API.

        Keyword arguments: edge_mm, path_mm, travel_speed, blade_speed.
        Returns True on success.
        """
        if not self.cloud_client:
            _LOGGER.error("async_set_cloud_setting called but no cloud client configured")
            return False

        def _do_set() -> None:
            self.cloud_client.set_settings(**kwargs)

        try:
            await self.hass.async_add_executor_job(_do_set)
            # Force a cloud re-fetch on the next poll cycle
            self._cloud_last_fetch = float("-inf")
            await self.async_request_refresh()
            return True
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("Cloud setting update failed: %s", exc)
            return False
