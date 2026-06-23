"""EasyOCR-based plate recognition provider - better for UAE/India plates."""
from .base import PlateRecognitionProvider, RecognitionResult
import re

class EasyOCRProvider(PlateRecognitionProvider):
    """EasyOCR provider optimized for UAE and India license plates."""
    
    def __init__(self, region: str = "UA"):
        self.region = region
        self._reader = None
    
    def _get_reader(self):
        """Lazy load EasyOCR reader."""
        if self._reader is None:
            try:
                import easyocr
                # Use English model for plates
                self._reader = easyocr.Reader(['en'], gpu=False)
            except ImportError:
                raise ImportError("easyocr not installed. Run: pip install easyocr")
        return self._reader
    
    def recognize(self, image_bytes: bytes) -> RecognitionResult:
        """Recognize license plate from image bytes using EasyOCR."""
        import io
        from PIL import Image
        import numpy as np
        
        reader = self._get_reader()
        
        # Load image
        image = Image.open(io.BytesIO(image_bytes))
        
        # Convert to RGB if needed
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Run OCR with focused settings for license plates
        results = reader.readtext(
            np.array(image),
            detail=1,
            paragraph=False,
            min_size=20,  # Smaller text threshold for plates
        )
        
        best_text = ""
        best_confidence = 0
        
        for bbox, text, confidence in results:
            # Clean and normalize detected text
            cleaned = re.sub(r'[^A-Z0-9]', '', text.upper())
            
            # For UAE plates, prioritize numbers (most common format)
            if self.region == "UA":
                numbers = re.sub(r'[^0-9]', '', cleaned)
                # UAE plates are typically 4-8 digits
                if len(numbers) >= 4 and len(numbers) <= 8:
                    if confidence > best_confidence:
                        best_text = numbers
                        best_confidence = confidence
                # Also check for letter+number format (like AD12345)
                if re.match(r'^[A-Z]{1,2}[0-9]{4,8}$', cleaned):
                    if confidence > best_confidence:
                        best_text = cleaned
                        best_confidence = confidence
            else:
                # Indian plates
                if re.match(r'^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{1,4}$', cleaned):
                    if confidence > best_confidence:
                        best_text = cleaned
                        best_confidence = confidence
        
        return RecognitionResult(
            plate_text=best_text or "",
            confidence=best_confidence if best_text else 0.0,
            region_hint=self.region,
            bounding_box={"x": 0, "y": 0, "width": 0, "height": 0},
            provider="easyocr"
        )
    
    def name(self) -> str:
        return "easyocr"