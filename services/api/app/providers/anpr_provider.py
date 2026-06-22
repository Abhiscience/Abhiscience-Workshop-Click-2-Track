from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class ANPRProvider(ABC):
    """Abstract base class for ANPR providers"""
    
    @abstractmethod
    async def recognize_plate(self, image_url: str) -> Dict[str, Any]:
        """
        Recognize license plate from image.
        
        Returns:
            {
                "plate_text_raw": str,
                "plate_text_normalized": str,
                "confidence": float,
                "success": bool,
                "error": Optional[str]
            }
        """
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        pass


class MockANPRProvider(ANPRProvider):
    """Mock ANPR provider for testing"""
    
    def __init__(self):
        self._counter = 0
    
    async def recognize_plate(self, image_url: str) -> Dict[str, Any]:
        self._counter += 1
        # Simulate a recognized plate
        return {
            "plate_text_raw": f"ABC{self._counter:03d}",
            "plate_text_normalized": f"ABC{self._counter:03d}",
            "confidence": 0.95,
            "success": True,
            "error": None
        }
    
    def get_provider_name(self) -> str:
        return "mock"


class OpenALPRProvider(ANPRProvider):
    """OpenALPR integration provider"""
    
    def __init__(self, api_key: str, api_url: str = "https://api.openalpr.com/v2"):
        self.api_key = api_key
        self.api_url = api_url.rstrip("/")
    
    async def recognize_plate(self, image_url: str) -> Dict[str, Any]:
        import httpx
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/recognize",
                    params={"recognize_image": image_url, "secret_key": self.api_key},
                    timeout=30.0
                )
                data = response.json()
                
                if data.get("results"):
                    best_result = data["results"][0]
                    plate = best_result.get("plate", "")
                    confidence = best_result.get("confidence", 0) / 100.0
                    
                    return {
                        "plate_text_raw": plate,
                        "plate_text_normalized": plate,
                        "confidence": confidence,
                        "success": True,
                        "error": None
                    }
                
                return {
                    "plate_text_raw": None,
                    "plate_text_normalized": None,
                    "confidence": 0,
                    "success": False,
                    "error": "No plate detected"
                }
        except Exception as e:
            return {
                "plate_text_raw": None,
                "plate_text_normalized": None,
                "confidence": 0,
                "success": False,
                "error": str(e)
            }
    
    def get_provider_name(self) -> str:
        return "openalpr"


class PlateRecognizerProvider(ANPRProvider):
    """PlateRecognizer.com integration provider"""
    
    def __init__(self, api_key: str, api_url: str = "https://platerecognizer.com/api/v1"):
        self.api_key = api_key
        self.api_url = api_url.rstrip("/")
    
    async def recognize_plate(self, image_url: str) -> Dict[str, Any]:
        import httpx
        
        try:
            async with httpx.AsyncClient() as client:
                # Download image first
                async with client.get(image_url) as img_resp:
                    image_data = img_resp.content
                
                files = {"upload": ("image.jpg", image_data, "image/jpeg")}
                headers = {"Authorization": f"Token {self.api_key}"}
                
                response = await client.post(
                    f"{self.api_url}/plate-reader/",
                    files=files,
                    headers=headers,
                    timeout=30.0
                )
                data = response.json()
                
                if data.get("results"):
                    best_result = data["results"][0]
                    plate = best_result.get("plate", "")
                    confidence = best_result.get("score", 0)
                    
                    return {
                        "plate_text_raw": plate,
                        "plate_text_normalized": plate.upper().replace("-", ""),
                        "confidence": confidence / 100.0,
                        "success": True,
                        "error": None
                    }
                
                return {
                    "plate_text_raw": None,
                    "plate_text_normalized": None,
                    "confidence": 0,
                    "success": False,
                    "error": "No plate detected"
                }
        except Exception as e:
            return {
                "plate_text_raw": None,
                "plate_text_normalized": None,
                "confidence": 0,
                "success": False,
                "error": str(e)
            }
    
    def get_provider_name(self) -> str:
        return "platerecognizer"


def get_anpr_provider(provider_name: str = "mock", **kwargs) -> ANPRProvider:
    """Factory function to get ANPR provider instance"""
    providers = {
        "mock": MockANPRProvider,
        "openalpr": OpenALPRProvider,
        "platerecognizer": PlateRecognizerProvider,
    }
    
    if provider_name not in providers:
        raise ValueError(f"Unknown provider: {provider_name}")
    
    return providers[provider_name](**kwargs)


# Global provider instance
_current_provider: ANPRProvider = MockANPRProvider()


def set_anpr_provider(provider: ANPRProvider):
    """Set the current ANPR provider"""
    global _current_provider
    _current_provider = provider


async def recognize_plate(image_url: str) -> Dict[str, Any]:
    """Singleton access to ANPR recognition"""
    return await _current_provider.recognize_plate(image_url)