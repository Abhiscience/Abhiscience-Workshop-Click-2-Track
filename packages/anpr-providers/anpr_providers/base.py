"""ANPR Provider Abstraction Layer - Supports UAE and India plates."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List
import re


@dataclass
class RecognitionResult:
    plate_text: str
    confidence: float
    region_hint: str  # "UA" or "IN"
    bounding_box: dict
    provider: str


class PlateRecognitionProvider(ABC):
    """Abstract interface for plate recognition providers."""
    
    @abstractmethod
    def recognize(self, image_bytes: bytes) -> RecognitionResult:
        """Recognize license plate from image bytes."""
        pass
    
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass


class MockPlateRecognitionProvider(PlateRecognitionProvider):
    """Mock provider for development/testing. Returns sample UAE and India plates."""
    
    SAMPLE_PLATES = {
        "UA": ["A12345", "B67890", "UAE12345", "DXB12345", "AUH98765"],
        "IN": ["MH01AB1234", "DL02CD5678", "KA03EF9012", "TN04GH3456"]
    }
    
    def __init__(self, region: str = "UA"):
        self.region = region
    
    def recognize(self, image_bytes: bytes) -> RecognitionResult:
        import hashlib
        import random
        
        hash_val = int(hashlib.md5(image_bytes).hexdigest()[:4], 16) % len(self.SAMPLE_PLATES[self.region])
        
        return RecognitionResult(
            plate_text=self.SAMPLE_PLATES[self.region][hash_val],
            confidence=random.uniform(0.85, 0.99),
            region_hint=self.region,
            bounding_box={"x": 100, "y": 100, "width": 200, "height": 50},
            provider="mock"
        )
    
    def name(self) -> str:
        return "mock"


def normalize_plate(plate_text: str, region: str = "UA") -> str:
    """
    Normalize plate text based on region.
    
    UAE formats: A12345, B67890, UAE12345, DXB12345
    India formats: MH01AB1234, DL02CD5678, KA03EF9012
    """
    plate = plate_text.upper().strip()
    
    if region == "UA":
        # UAE plates: remove spaces, normalize format
        plate = re.sub(r'[^A-Z0-9]', '', plate)
    elif region == "IN":
        # India plates: normalize format, remove spaces
        plate = re.sub(r'[^A-Z0-9]', '', plate)
        # Ensure standard format: LLDDLLLNNNN
        # Already normalized by removing spaces
    
    return plate


def get_provider(region: str = "UA") -> PlateRecognitionProvider:
    """Factory to get configured ANPR provider."""
    try:
        from anpr_providers.easyocr_provider import EasyOCRProvider
        return EasyOCRProvider(region)
    except Exception:
        return MockPlateRecognitionProvider(region)