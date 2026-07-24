from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthContext
from app.models.entities import AuditLog


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        context: AuthContext | None,
        action: str,
        resource_type: str,
        resource_id: str,
        request: Request | None = None,
        metadata: dict | None = None,
    ) -> AuditLog:
        ip_address = None
        user_agent = None
        if request is not None:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")

        log = AuditLog(
            actor_user_id=context.user_id if context else None,
            actor_role=context.role.value if context else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            audit_metadata=metadata or {},
        )
        self.session.add(log)
        await self.session.flush()
        return log
