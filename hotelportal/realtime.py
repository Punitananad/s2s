# hotelportal/realtime.py
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def push_live_board(hotel):
    """
    Tell all LiveBoardConsumer clients for this hotel to refresh their board state.
    Called from normal Django views after any change.
    """
    layer = get_channel_layer()
    if not layer:
        return

    if hotel is not None:
        group_name = f"hotel_{hotel.id}_live"
    else:
        group_name = "platform_live"

    async_to_sync(layer.group_send)(
        group_name,
        {
            "type": "live_board_update",   # maps to LiveBoardConsumer.live_board_update
        },
    )
