from fastapi import APIRouter

from app.services.ocr_engine import is_configured

router = APIRouter()


@router.get("")
def health_check() -> dict:
    """Liveness plus the one bit of config the UI has to warn about.

    `llm_configured` is false when LLM_API_KEY/LLM_MODEL_API/LLM_MODEL_NAME are
    missing from the repo-root .env — which breaks handwriting OCR *and*
    grading, since both call the same model. It rides along here so the sidebar
    needs a single request to know everything it displays; there used to be a
    second one against the standalone OCR service for exactly this field.
    """
    return {"status": "ok", "llm_configured": is_configured()}
