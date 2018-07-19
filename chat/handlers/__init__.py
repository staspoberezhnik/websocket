group_chat_ws_connections = dict()
private_chat_ws_connections = dict()


def get_online_users(current_user=None, without_current=False):
    if without_current:
        return [user for user in set(group_chat_ws_connections.keys()) if user != current_user]
    else:
        return [user for user in set(group_chat_ws_connections.keys())]


def send_group_chat_message(message, message_type='chat',  receiver=None,):
    params = dict(message=dict(message_type=message_type, message=message))
    connections = [group_chat_ws_connections.get(receiver)] if receiver else group_chat_ws_connections.values()
    for connection in connections:
        connection.write_message(**params)


def send_private_chat_message(message, message_type='chat', receiver=None):
    params = dict(message=dict(message_type=message_type, message=message))
    connections = [private_chat_ws_connections.get(receiver)] if receiver else private_chat_ws_connections.values()
    for connection in connections:
        connection.write_message(**params)


# def send_message_to_all_chats(message, message_type='chat', receiver=None):
#     if group_chat_ws_connections is not None:
#         send_group_chat_message(message, message_type, receiver)
#     if private_chat_ws_connections is not None:
#         send_private_chat_message(message, message_type, receiver)

from .web_handlers import *
from .websocket_handlers import SimpleWebSocket, SendToUser
from .auth_handlers import *
