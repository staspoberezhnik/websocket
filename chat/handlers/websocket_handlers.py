import datetime

from tornado.escape import json_decode, xhtml_unescape
from tornado.websocket import WebSocketHandler

from chat.handlers import BaseHandler, group_chat_ws_connections, private_chat_ws_connections, get_online_users, \
    send_group_chat_message, send_private_chat_message


class BaseWebSocketHandler(BaseHandler, WebSocketHandler):
    def check_origin(self, origin):
        return True

    def get(self, *args, **kwargs):
        WebSocketHandler.get(self, *args, **kwargs)

    async def get_unread_messages(self, receiver):
        return await self.select(
            query="SELECT count(message) FROM chat where" +
                  " reciever = '%(username)s' and status = '0' ",
            params=dict(username=receiver)
        )


class SimpleWebSocket(BaseWebSocketHandler):
    async def open(self):
        group_chat_ws_connections[self.get_current_user()] = self
        send_group_chat_message(message_type='online_users', message=get_online_users())
        current_id = await self.get_user_id(self.get_current_user())
        friendship_requests = await self.get_friendship_requests(current_id)
        unread_private_message = await self.get_unread_messages(self.current_user)
        send_group_chat_message(message_type='requests',
                                message=friendship_requests[0]['count'],
                                receiver=self.current_user
                                )
        send_group_chat_message(message_type='unreaded',
                                message=unread_private_message[0]['count'],
                                receiver=self.current_user
                                )

    async def on_message(self, message):
        send_group_chat_message(message=message)
        data = json_decode(message)
        await self.insert(
            table='chat',
            params=dict(
                sender=xhtml_unescape(data['user']),
                message=data['message'],
                date_created=datetime.datetime.now(),
            )
        )

    def on_close(self):
        group_chat_ws_connections.pop(self.get_current_user())
        send_group_chat_message(message_type='online_users', message=get_online_users(self.get_current_user()))


class SendToUser(BaseWebSocketHandler):
    async def open(self, receiver, *args, **kwargs):
        self.receiver = receiver
        private_chat_ws_connections[self.get_current_user()] = self
        current_id = await self.get_user_id(self.get_current_user())
        friendship_requests = await self.get_friendship_requests(current_id)
        send_private_chat_message(message_type='requests',
                                  message=friendship_requests[0]['count'],
                                  receiver=self.current_user)
        unread_private_message = await self.get_unread_messages(self.current_user)
        send_private_chat_message(message_type='unreaded',
                                  message=unread_private_message[0]['count'],
                                  receiver=self.current_user)

    async def on_message(self, message):
        data = json_decode(message)
        send_private_chat_message(message=message, receiver=data['user'])
        receiver_connection = private_chat_ws_connections.get(self.receiver)

        if receiver_connection and receiver_connection.receiver == data['user']:
            if receiver_connection.receiver == data['user']:
                send_private_chat_message(message=message, receiver=data['send_to'])

        await self.insert(
            table='chat',
            params=dict(
                sender=data['user'],
                reciever=data['send_to'],
                message=data['message'],
                date_created=datetime.datetime.now())
        )
        unread_private_message = await self.get_unread_messages(xhtml_unescape(data['send_to']))
        if data['send_to'] in group_chat_ws_connections.keys():
            send_group_chat_message(message=unread_private_message[0]['count'],
                                    message_type='unreaded',
                                    receiver=xhtml_unescape(data['send_to'])
                                    )
        if data['send_to'] in private_chat_ws_connections.keys():
            send_private_chat_message(message=unread_private_message[0]['count'],
                                      message_type='unreaded',
                                      receiver=xhtml_unescape(data['send_to'])
                                      )

    def on_close(self):
        user = self.get_current_user()
        if user in private_chat_ws_connections:
            private_chat_ws_connections.pop(user)
