"""OCR.space provider for license plate recognition."""
import os, re, io
from typing import Dict, Any, Optional
import httpx


def _extract_plate(raw_text: str) -> str:
    """Extract the most likely plate from OCR.space raw text."""
    text = re.sub(r'[^A-Z0-9]', '', raw_text.upper())
    
    # Indian format LLDDLLNNNN
    if re.match(r'^[A-Z]{2}[0-9]{2}[A-Z]{1,3}[0-9]{1,4}$', text):
        return text
    
    # UAE format: letter(s) + numbers
    m = re.match(r'^([A-Z]{1,2})([0-9]{1,5})$', text)
    if m:
        return text
    
    # UAE numbers only
    if re.match(r'^[0-9]{1,5}$', text):
        return text
    
    # Fallback: longest number sequence
    numbers = re.findall(r'[0-9]{4,8}', text)
    if numbers:
        return numbers[0]
    
    return text


class OCRSpaceProvider:
    """OCR.space API provider."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OCR_SPACE_API_KEY", "")
        self.api_url = "https://api.ocr.space/parse/image"
    
    async def recognize_plate(self, image_bytes: bytes, filename: str = "image.jpg") -> Dict[str, Any]:
        if not self.api_key:
            return {"plate_text_raw": None, "plate_text_normalized": None, "confidence": 0, "success": False, "error": "OCR_SPACE_API_KEY not configured"}
        
        try:
            payload = {
                "apikey": self.api_key,
                "language": "eng",
                "isOverlayRequired": "false",
                "detectOrientation": "true",
                "scale": "true",
                "OCREngine": "2",
            }
            files = {"file": (filename, io.BytesIO(image_bytes), "image/jpeg")}
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(self.api_url, data=payload, files=files)
                data = response.json()
            
            if data.get("IsErroredOnProcessing"):
                return {"plate_text_raw": None, "plate_text_normalized": None, "confidence": 0, "success": False, "error": data.get("ErrorMessage", "Unknown OCR error")}
            
            parsed_results = data.get("ParsedResults", [])
            if not parsed_results:
                return {"plate_text_raw": None, "plate_text_normalized": None, "confidence": 0, "success": False, "error": "No text detected"}
            
            raw_text = parsed_results[0].get("ParsedText", "")
            plate = _extract_plate(raw_text)
            
            if not plate:
                return {"plate_text_raw": raw_text, "plate_text_normalized": None, "confidence": 0, "success": False, "error": "No plate detected"}
            
            return {"plate_text_raw": plate, "plate_text_normalized": plate, "confidence": 0.85, "success": True, "error": None}
        
        except Exception as e:
            return {"plate_text_raw": None, "plate_text_normalized": None, "confidence": 0, "success": False, "error": str(e)}


_ocr_provider: Optional[OCRSpaceProvider] = None


def get_ocr_provider() -> OCRSpaceProvider:
    global _ocr_provider
    if _ocr_provider is None:
        from app.core.config import settings
        _ocr_provider = OCRSpaceProvider(api_key=settings.OCR_SPACE_API_KEY)
    return _ocr_provider
