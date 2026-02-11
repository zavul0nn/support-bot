from . import command
from . import message

routers = [
    command.router,
    command.qr_router,
    command.router_id,
    message.router,
]
