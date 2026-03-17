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
        Process image attachment.
        
        Args:
            file_path: Path to image file
            
        Returns:
            Extracted text/description
            
        TODO: Implement in SLICE 6
        - Use vision model for image analysis
        - Extract text if present (OCR)
        """
        logger.info(f"Processing image: {file_path}")
        # Placeholder
        return "[Image uploaded - analysis pending]"
    
    async def _process_pdf(self, file_path: Path) -> Optional[str]:
        """
        Process PDF attachment.
        
        Args:
            file_path: Path to PDF file
            
        Returns:
            Extracted text content
            
        TODO: Implement in SLICE 6
        - Extract text from PDF
        - Handle multi-page documents
        - Chunk if too large
        """
        logger.info(f"Processing PDF: {file_path}")
        # Placeholder
        return "[PDF uploaded - extraction pending]"
    
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

