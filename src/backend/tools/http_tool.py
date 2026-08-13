import aiohttp
from typing import Dict, Any
from src.backend.tools.base import BaseTool


class AsyncHTTPTool(BaseTool):
    """
    Non-blocking HTTP Client Tool for web scraping and REST API integration.
    """

    def __init__(
        self,
        default_timeout_ms: int = 5000,
        default_max_retries: int = 3
    ):
        super().__init__(
            name="http_tool",
            description="Executes non-blocking HTTP requests for web fetch & API integrations",
            default_timeout_ms=default_timeout_ms,
            default_max_retries=default_max_retries
        )

    async def run(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes HTTP GET/POST request.
        Expected params: {"url": str, "method": "GET"|"POST", "headers": dict, "json": dict}
        """
        url = params.get("url")
        if not url:
            raise ValueError("Parameter 'url' is required for http_tool")

        method = params.get("method", "GET").upper()
        headers = params.get("headers", {"User-Agent": "AsyncAgentOrchestrator/1.0"})
        json_data = params.get("json")

        timeout = aiohttp.ClientTimeout(total=self.default_timeout_ms / 1000.0)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            if method == "GET":
                async with session.get(url, headers=headers) as response:
                    text = await response.text()
                    return {
                        "status_code": response.status,
                        "url": str(response.url),
                        "content_length": len(text),
                        "data": text[:2000]  # Truncate output for token efficiency
                    }
            elif method == "POST":
                async with session.post(url, headers=headers, json=json_data) as response:
                    text = await response.text()
                    return {
                        "status_code": response.status,
                        "url": str(response.url),
                        "content_length": len(text),
                        "data": text[:2000]
                    }
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
