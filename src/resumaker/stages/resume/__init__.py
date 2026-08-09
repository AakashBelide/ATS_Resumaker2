"""Resume generation: grounded tailoring -> ATS-safe .docx -> PDF, 1-page trim,
deterministic skills ranking, JD-aware location, reverse-chronological ordering."""
from resumaker.stages.resume.generate import generate_resume

__all__ = ["generate_resume"]
