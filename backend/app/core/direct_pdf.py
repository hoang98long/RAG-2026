"""Limits for the standalone PDF supplied explicitly by the chat user."""
DIRECT_PDF_MAX_BYTES = 10 * 1024 * 1024
DIRECT_PDF_MAX_PAGES = 100
DIRECT_PDF_MAX_BODY_BYTES = DIRECT_PDF_MAX_BYTES + 128 * 1024
