# hotelportal/consumers.py
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from asgiref.sync import sync_to_async
from django.utils import timezone

from urllib.parse import parse_qs          # 14.1A
from django.conf import settings          # 14.1A

from .models import Request, Room

import os








# 14.2A — HotelLiveConsumer supports:
# - normal portal users (browser, authenticated)
# - external "staff bot" via ?bot_key=...

class HotelLiveConsumer(AsyncJsonWebsocketConsumer):
    """
    Live board WebSocket for hotel portal.

    Modes:
    - Browser mode: authenticated HOTEL_ADMIN/STAFF/PLATFORM_ADMIN, bound to one hotel.
    - Bot mode: external script connects with ?bot_key=... and listens to ALL hotels
      in group "hotel_portal_live_all".
    """

    async def connect(self):
        # Default flags
        self.is_bot = False
        self.hotel_id = None

        # -------------------------
        # Try BOT mode first (query param ?bot_key=...)
        # -------------------------
        raw_qs = self.scope.get("query_string", b"").decode()  # e.g. "bot_key=abc"
        params = parse_qs(raw_qs)
        bot_key = (params.get("bot_key") or [None])[0]

        # You can later move this to env var; for now we hard-match what script uses
        expected_key = os.environ.get(
            "STAFF_BOT_KEY",
            "CHANGE_THIS_TO_SOMETHING_LONG_RANDOM",   # must match your Python script
        )

        if bot_key and bot_key == expected_key:
            # ✅ BOT MODE
            self.is_bot = True
            # Bot listens to ALL hotels at once
            self.group_name = "hotel_portal_live_all"

            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()

            # Send initial board snapshot
            data = await self._build_board_state()
            await self.send_json({
                "type": "board_state",
                "data": data,
            })
            return

        # -------------------------
        # Otherwise: Browser mode (normal portal user)
        # -------------------------
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close()
            return

        role = getattr(user, "role", None)
        if role not in ("HOTEL_ADMIN", "STAFF", "PLATFORM_ADMIN"):
            await self.close()
            return

        # Get hotel safely
        hotel = await sync_to_async(
            lambda u: getattr(u, "hotel", None),
            thread_sensitive=True
        )(user)

        if hotel is None and role != "PLATFORM_ADMIN":
            # Staff/Admin must be tied to a hotel
            await self.close()
            return

        self.hotel_id = hotel.id if hotel else None

        # Group per hotel; PLATFORM_ADMIN sees all
        if self.hotel_id:
            self.group_name = f"hotel_portal_live_{self.hotel_id}"
        else:
            self.group_name = "hotel_portal_live_all"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Initial board state
        data = await self._build_board_state()
        await self.send_json({
            "type": "board_state",
            "data": data,
        })

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # === Group event handler ===
    async def board_push(self, event):
        """
        Called when views send group_send with type="board.push".
        Forwards payload as JSON to browser/bot.
        """
        payload = event.get("payload") or {}
        await self.send_json(payload)

    # === Internal: build board snapshot (same shape as live_poll) ===
    @sync_to_async
    def _build_board_state(self):
        hotel_id = self.hotel_id  # None => all hotels

        qs = Request.objects.all().select_related("room", "hotel").prefetch_related("lines")
        room_qs = Room.objects.all().select_related("current_stay")

        if hotel_id:
            qs = qs.filter(hotel_id=hotel_id)
            room_qs = room_qs.filter(hotel_id=hotel_id)

        new_qs = qs.filter(status="NEW").order_by("-created_at")[:100]
        acc_qs = qs.filter(status="ACCEPTED").order_by("-updated_at")[:100]

        today = timezone.localdate()
        counts = {
            "completed_today": qs.filter(status="COMPLETED", completed_at__date=today).count(),
            "cancelled_today": qs.filter(status="CANCELLED", cancelled_at__date=today).count(),
        }

        def _serialize_requests_inner(qs_):
            out = []
            for r in qs_:
                h = getattr(r, "hotel", None)
                out.append({
                    "id": r.id,
                    "room": r.room.number if r.room else "",
                    "kind": r.kind,
                    "status": r.status,
                    "subtotal": float(r.subtotal or 0),
                    "created_at": r.created_at.isoformat(),
                    "accepted_at": r.accepted_at.isoformat() if r.accepted_at else None,
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                    "cancelled_at": r.cancelled_at.isoformat() if r.cancelled_at else None,
                    "note": r.note or "",
                    "lines": [
                        {
                            "name": ln.name_snapshot,
                            "qty": ln.qty,
                        } for ln in r.lines.all()
                    ],
                    "hotel_id": h.id if h else None,
                    "hotel_name": h.name if h else "",
                })
            return out

        def _serialize_rooms_inner(qs_):
            out = []
            for rm in qs_:
                st = rm.current_stay
                out.append({
                    "id": rm.id,
                    "number": rm.number,
                    "floor": rm.floor,
                    "status": rm.status,  # FREE / BUSY / CLEANING
                    "guest_name": st.guest_name if st else "",
                    "guest_phone": st.phone if st else "",
                })
            return out

        room_qs = room_qs.order_by("floor", "number")
        free_rooms = [r for r in room_qs if r.status == "FREE"]
        busy_rooms = [r for r in room_qs if r.status == "BUSY"]
        cleaning_rooms = [r for r in room_qs if r.status == "CLEANING"]

        return {
            "new": _serialize_requests_inner(new_qs),
            "accepted": _serialize_requests_inner(acc_qs),
            "counts": counts,
            "rooms": {
                "free": _serialize_rooms_inner(free_rooms),
                "busy": _serialize_rooms_inner(busy_rooms),
                "cleaning": _serialize_rooms_inner(cleaning_rooms),
            }
        }
