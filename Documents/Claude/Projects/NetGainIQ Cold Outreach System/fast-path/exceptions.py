"""Custom exceptions for the Fast Path pipeline."""


class FastPathError(Exception):
    """Base exception for the Fast Path pipeline."""


class FastPathHttpError(FastPathError):
    """HTTP request failed after exhausting retries."""


class AuthFailureError(FastPathError):
    """API rejected credentials (HTTP 401). Halt — do not retry."""


class CreditsExhaustedError(FastPathError):
    """API reports the account is out of credits (HTTP 402). Halt enrichment."""


class PreflightFailure(FastPathError):
    """One or more preflight checks failed; pipeline must not proceed."""
