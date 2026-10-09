"""Helpers for interpreting tinytuya status() replies from Tuya IR hubs."""

from tinytuya import ERR_JSON

# Some IR hubs (seen on the "wnykq" category, e.g. model IRC01_T1 speaking
# protocol 3.5) do not implement DP_QUERY at all. They answer every status()
# with the plain text below instead of a DPS dict, no matter how many SET
# commands were sent before. The reply is still a correctly decrypted frame
# from the device, so it proves that host, device id, local key and protocol
# version are right. A wrong key or version yields ERR_KEY_OR_VER / ERR_PAYLOAD
# instead, never this string.
DP_QUERY_UNSUPPORTED_PAYLOAD = "json obj data unvalid"


def dp_query_unsupported(status):
    """Return True if status() shows a reachable hub that lacks DP_QUERY."""
    if not isinstance(status, dict) or "Error" not in status:
        return False
    if str(status.get("Err", "")).strip() != str(ERR_JSON):
        return False
    payload = status.get("Payload") or status.get("invalid_json") or ""
    return DP_QUERY_UNSUPPORTED_PAYLOAD in str(payload)
