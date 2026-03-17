"""
AGENT NEO - Attachment Handler
Processes image and PDF attachments for chat.
"""

import base64
import logging
import uuid
from typing import Optional, Dict
from pathlib import Path
import tempfile

from app.interactive.contracts import AttachmentUpload, AttachmentResponse

logger = logging.getLogger(__name__)


class AttachmentHandler:
    """
    Handles image and PDF attachments.
    
    For MVP: Simple temporary file storage and text extraction.
    """
    
    def __init__(self):
        """Initialize attachment handler."""
        self._attachments: Dict[str, AttachmentResponse] = {}
        self._temp_dir = Path(tempfile.gettempdir()) / "agent-neo-attachments"
        self._temp_dir.mkdir(exist_ok=True)
    
    async def process_attachment(
        self,
        upload: AttachmentUpload
    ) -> AttachmentResponse:
        """
        Process uploaded attachment.
        
        Args:
            upload: Attachment upload request
            
        Returns:
            Attachment response with extracted content
            
        TODO: Implement in SLICE 6
        """
        attachment_id = str(uuid.uuid4())
        
        logger.info(f"Processing {upload.file_type} attachment: {upload.file_name}")
        
        # Decode base64 content
        try:
            content_bytes = base64.b64decode(upload.content_base64)
        except Exception as e:
            logger.error(f"Failed to decode attachment: {e}")
            raise ValueError("Invalid base64 content")
        
        # Save to temp file
        file_path = self._temp_dir / f"{attachment_id}_{upload.file_name}"
        file_path.write_bytes(content_bytes)
        
        # Extract content based on type
        extracted_content = None
        if upload.file_type == "image":
            extracted_content = await self._process_image(file_path)
        elif upload.file_type == "pdf":
            extracted_content = await self._process_pdf(file_path)
        
        response = AttachmentResponse(
            attachment_id=attachment_id,
            session_id=upload.session_id,
            file_name=upload.file_name,
            file_type=upload.file_type,
            extracted_content=extracted_content
        )
        
        self._attachments[attachment_id] = response
        return response
    
    async def _process_image(self, file_path: Path) -> Optional[str]:
        """
        Process image via GPT-4o vision API.

        Args:
            file_path: Path to image file

        Returns:
            Extracted text/description from the image
        """
        import os
        logger.info(f"Processing image via vision API: {file_path.name}")

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set — skipping vision analysis")
            return "[Image attached — set OPENAI_API_KEY to enable vision analysis]"

        try:
            from openai import AsyncOpenAI

            image_bytes = file_path.read_bytes()
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")

            suffix = file_path.suffix.lower()
            mime_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }
            mime_type = mime_map.get(suffix, "image/png")

            client = AsyncOpenAI(api_key=api_key)
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_b64}",
                                    "detail": "high",
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Describe this image in detail. "
                                    "If it contains code, extract it exactly. "
                                    "If it contains text, transcribe it. "
                                    "If it is a diagram or UI screenshot, describe the structure and layout."
                                ),
                            },
                        ],
                    }
                ],
                max_tokens=1500,
            )
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            return f"[Image analysis failed: {e}]"

    async def _process_pdf(self, file_path: Path) -> Optional[str]:
        """
        Extract text from PDF using pdfplumber (falls back to pypdf).

        Args:
            file_path: Path to PDF file

        Returns:
            Extracted text content (first 20 pages, max 15 000 chars)
        """
        logger.info(f"Extracting text from PDF: {file_path.name}")

        MAX_PAGES = 20
        MAX_CHARS = 15_000

        try:
            import pdfplumber

            pages_text: list[str] = []
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    if i >= MAX_PAGES:
                        pages_text.append("... (truncated — first 20 pages shown)")
                        break
                    text = page.extract_text() or ""
                    if text.strip():
                        pages_text.append(f"--- Page {i + 1} ---\n{text.strip()}")

            full_text = "\n\n".join(pages_text)
            if len(full_text) > MAX_CHARS:
                full_text = full_text[:MAX_CHARS] + "\n... (truncated)"
            return full_text or "[No extractable text found in PDF]"

        except Exception as primary_err:
            logger.warning(f"pdfplumber failed ({primary_err}), trying pypdf fallback")
            try:
                from pypdf import PdfReader

                reader = PdfReader(file_path)
                pages_text = []
                for i, page in enumerate(reader.pages):
                    if i >= MAX_PAGES:
                        break
                    text = page.extract_text() or ""
                    if text.strip():
                        pages_text.append(f"--- Page {i + 1} ---\n{text.strip()}")
                full_text = "\n\n".join(pages_text)
                if len(full_text) > MAX_CHARS:
                    full_text = full_text[:MAX_CHARS] + "\n... (truncated)"
                return full_text or "[No extractable text found in PDF]"
            except Exception as fallback_err:
                logger.error(f"PDF extraction fallback failed: {fallback_err}")
                return f"[PDF extraction failed: {primary_err}]"
    
    def get_attachment(self, attachment_id: str) -> Optional[AttachmentResponse]:
        """
        Get attachment by ID.
        
        Args:
            attachment_id: Attachment ID
            
        Returns:
            Attachment response or None
        """
        return self._attachments.get(attachment_id)
    
    def cleanup_old_attachments(self, max_age_hours: int = 24):
        """
        Clean up old temporary attachments.
        
        Args:
            max_age_hours: Maximum age in hours
            
        TODO: Implement cleanup logic
        """
        # Placeholder for cleanup
        pass


# Global attachment handler instance
_attachment_handler: Optional[AttachmentHandler] = None


def get_attachment_handler() -> AttachmentHandler:
    """Get global attachment handler instance."""
    global _attachment_handler
    if _attachment_handler is None:
        _attachment_handler = AttachmentHandler()
    return _attachment_handler

