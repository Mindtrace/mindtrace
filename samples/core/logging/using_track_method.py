import asyncio
from mindtrace.core.logging.logger import track_method

class APIClient:
    def __init__(self):
        self.logger = None  # Will be auto-created by track_method
    
    @track_method("api_request", include_args=["endpoint", "method", "data"])
    async def make_request(self, endpoint: str, method: str, data: dict):
        # Logs will include endpoint and method in context
        await asyncio.sleep(0.1)  # Simulate API call
        return {"status": "success", "data": data}
    
    @track_method()  # Uses default method name
    async def process_response(self, response: dict):
        # Basic tracking without specific args
        return response.get("status") == "success"

# Usage
async def main():
    client = APIClient()
    
    # This will log with endpoint and method in context
    result = await client.make_request("/api/users", "POST", {"name": "John"})
    print(result)
    
    # This will log with basic method tracking
    success = await client.process_response(result)
    print(f"Success: {success}")

if __name__ == "__main__":
    asyncio.run(main())