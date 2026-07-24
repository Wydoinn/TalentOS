from app.routes.auth import router as auth_router
from app.routes.candidate import router as candidate_router
from app.routes.system import router as system_router

__all__ = ["auth_router", "candidate_router", "system_router"]
