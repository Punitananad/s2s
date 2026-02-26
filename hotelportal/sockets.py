# hotelportal/sockets.py
from typing import Optional
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def broadcast_portal_board(hotel_id: Optional[int]) -> None:
    """
    Tell all connected /ws/portal/live/ sockets for this hotel
    to refresh their board state.
    """
    layer = get_channel_layer()
    if not layer:
        return

    group_name = f"hotel_{hotel_id}" if hotel_id else "platform"

    async_to_sync(layer.group_send)(
        group_name,
        {
            "type": "board.update",  # maps to async def board_update(...) in consumer
        },
    )
