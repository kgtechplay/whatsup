import requests
from fastapi import HTTPException


class WhatsAppGatewayClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def _request(self, method: str, path: str, **kwargs):
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                timeout=15,
                **kwargs,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Baileys gateway request failed: {exc}",
            ) from exc

    def health(self):
        return self._request("GET", "/health")

    def status(self):
        return self._request("GET", "/status")

    def get_messages(self, limit: int = 20):
        payload = self._request("GET", f"/messages?limit={limit}")
        return payload.get("messages", [])

    def send_text(self, to: str, text: str):
        return self._request("POST", "/send", json={"to": to, "text": text})
