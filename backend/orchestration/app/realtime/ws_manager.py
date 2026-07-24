from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket


class RoomSocketManager:
    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, room_id: str) -> None:
        await websocket.accept()
        async with self._lock:
            self._rooms[room_id].add(websocket)

    async def disconnect(self, websocket: WebSocket, room_id: str) -> None:
        async with self._lock:
            sockets = self._rooms.get(room_id)
            if not sockets:
                return
            sockets.discard(websocket)
            if not sockets:
                self._rooms.pop(room_id, None)

    async def broadcast(self, room_id: str, payload: dict) -> None:
        sockets = list(self._rooms.get(room_id, set()))
        stale: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:
                stale.append(socket)

        if stale:
            async with self._lock:
                room = self._rooms.get(room_id)
                if room:
                    for socket in stale:
                        room.discard(socket)
                    if not room:
                        self._rooms.pop(room_id, None)

    async def room_size(self, room_id: str) -> int:
        async with self._lock:
            return len(self._rooms.get(room_id, set()))


ws_manager = RoomSocketManager()
