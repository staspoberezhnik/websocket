import datetime

import tornado.web
import tornado.platform.asyncio
from tornado import escape

from chat.handlers import send_group_chat_message,\
    group_chat_ws_connections, private_chat_ws_connections, send_private_chat_message


class BaseHandler(tornado.web.RequestHandler):
    def data_received(self, chunk):
        pass

    def get_current_user(self):
        user = self.get_secure_cookie('user')
        return escape.xhtml_unescape(user) if user else None

    async def select(self, query, params=None):
        if params:
            for key, value in params.items():
                if value is None:
                    value = 'Null'
                    params[key] = value
        if params:
            query = query % params
        async with self.application.pool.acquire() as conn:
            res = await conn.fetch(query)
        return res

    async def insert(self, table, params):
        query = "insert into %(table)s (%(columns)s) values (%(values)s);"
        columns = list()
        values = list()
        for key, value in params.items():
            columns.append(key)
            if isinstance(value, str):
                value = value.replace("'", "''")
                value = "'%s'" % value
            if isinstance(value, datetime.datetime):
                value = "'%s'" % value
            values.append(value)
        query = query % dict(table=table, columns=', '.join(columns), values=', '.join(values))
        async with self.application.pool.acquire() as conn:
            await conn.execute(query)

    async def update(self, query, params=None):
        if params:
            for key, value in params.items():
                if value is None:
                    value = 'Null'
                    params[key] = value
        if params:
            query = query % params
        async with self.application.pool.acquire() as conn:
            await conn.execute(query)

    def prepare(self):
        super().prepare()
        if not self.current_user:
            return self.redirect("/login")

    async def get_user_id(self, user_name):
        return await self.select(
            query="SELECT id FROM users where username = '%(username)s' ",
            params=dict(username=user_name)
        )

    async def get_friendship_requests(self, user):
        return await self.select(
            query="SELECT count(u.username) FROM users u JOIN (" +
                  "SELECT * FROM (" +
                  "SELECT friend_one, status FROM friends WHERE friend_two='%(id)s' ) fr WHERE fr.status='0')" +
                  "f ON f.friend_one=u.id; ",
            params=dict(id=user[0]['id']))


class MainHandler(BaseHandler):
    async def get(self, *args, **kwargs):
        res = await self.select(
            query="SELECT sender,message, date_created FROM chat where reciever is %(receiver)s order by date_created",
            params=dict(receiver=None)
        )
        self.render("base.html", data=res, see_all=True)


class PrivateHandler(BaseHandler):
    async def get(self, receiver, *args, **kwargs):
        if receiver == self.get_current_user():
            return self.redirect('/')
        sent_messages = []
        received_messages = []
        receiver_name = await self.get_username(receiver)
        if not receiver_name:
            return self.redirect('/')
        sender = await self.get_user_id(self.current_user)
        receiver_id = await self.get_user_id(receiver_name[0]['username'])
        status = await self.get_friendship_status(
            sender_id=sender[0]['id'],
            receiver_id=receiver_id[0]['id'],
        )

        messages = await self.select("SELECT sender, reciever, message, date_created FROM chat")
        for message in messages:
            if message['sender'] == self.get_current_user() and message['reciever'] == receiver:
                sent_messages.append(message)
            if message['reciever'] == self.get_current_user() and message['sender'] == receiver:
                received_messages.append(message)
            else:
                continue
        await self.read_messages(receiver)
        self.render(
            template_name="private.html",
            send_to=receiver_name[0]['username'],
            data=sent_messages,
            received_data=received_messages,
            status=status
        )

    async def get_username(self, user):
        return await self.select(
            query=" SELECT username FROM users where username = '%(user)s' ",
            params=dict(user=user)
        )

    async def get_friendship_status(self, sender_id, receiver_id):
        status = await self.select(
            query="SELECT friend_one, friend_two, status FROM friends where " +
                  "(friend_one = '%(sender)s' or friend_two = '%(sender)s') " +
                  "and (friend_one = '%(receiver)s' or friend_two = '%(receiver)s') ",
            params=dict(
                sender=sender_id,
                receiver=receiver_id)
        )
        if status:
            if status[0]['status'] == '1':
                status = 'Friends'
            elif status[0]['friend_one'] == sender_id and status[0]['status'] == '0':
                status = 'Send'
            else:
                status = 'Receive'
            return status
        return None

    async def read_messages(self, receiver):
        await self.update(
            query="UPDATE chat SET status='1' where (reciever = '%(sender)s' and sender = '%(receiver)s'); ",
            params=dict(receiver=receiver,
                        sender=self.get_current_user())
        )


class NotificationHandler(BaseHandler):
    async def get(self):
        if not self.current_user:
            self.redirect("/login")
        else:
            current_id = await self.get_user_id(self.get_current_user())
            friends_name = await self.select(
                query="SELECT u.username FROM users u JOIN (" +
                      "SELECT * FROM (" +
                      "SELECT friend_two, status FROM friends WHERE friend_one='%(id)s'  UNION " +
                      "SELECT friend_one, status FROM friends WHERE friend_two='%(id)s' ) fr WHERE fr.status='1')" +
                      "f ON f.friend_two=u.id;",
                params=dict(id=current_id[0]['id'])
            )
            users = []
            res = []
            self.render("friends_list.html",
                        users=users,
                        data=res,
                        friends=friends_name,
                        see_all=False)


class AllUsersHandler(BaseHandler):
    async def get(self):
        if not self.current_user:
            self.redirect("/login")
        else:
            all_users = await self.select(query="SELECT username FROM users")
            self.render("all_users.html", data=[], users=all_users, see_all=False)


class InviteHandler(BaseHandler):
    async def get(self, user):
        if not self.current_user:
            self.redirect("/login")
        else:
            friend_one_id = await self.get_user_id(self.current_user)
            friend_two_id = await self.get_user_id(user)
            await self.insert(
                table='friends',
                params=dict(
                    friend_one=str(friend_one_id[0]['id']),
                    friend_two=str(friend_two_id[0]['id'])))
            friendship_requests = await self.get_friendship_requests(friend_two_id)
            if user in group_chat_ws_connections.keys():
                send_group_chat_message(message_type='requests',
                                        message=friendship_requests[0]['count'],
                                        receiver=user)
            if user in private_chat_ws_connections.keys():
                send_private_chat_message(message_type='requests',
                                          message=friendship_requests[0]['count'],
                                          receiver=user)
            self.redirect('/')


class AddToFriendsHandler(BaseHandler):
    async def get(self, user):
        if not self.current_user:
            self.redirect("/login")
        else:
            friend_one_id = await self.get_user_id(self.current_user)
            friend_two_id = await self.get_user_id(user)
            await self.update(
                query=" UPDATE friends SET status='1' " +
                      " where (friend_one = '%(friend_one)s' or friend_two = '%(friend_one)s') " +
                      " and (friend_one = '%(friend_two)s' or friend_two = '%(friend_two)s') ",
                params=dict(
                    friend_one=str(friend_one_id[0]['id']),
                    friend_two=str(friend_two_id[0]['id'])))
            self.redirect('/requests')


class RemoveFromFriendsHandler(BaseHandler):
    async def get(self, user):
        if not self.current_user:
            self.redirect("/login")
        else:
            friend_one_id = await self.get_user_id(self.current_user)
            friend_two_id = await self.get_user_id(user)
            await self.update(
                query=" DELETE FROM friends WHERE (friend_one = '%(friend_one)s' or friend_two = '%(friend_one)s') " +
                      " and (friend_one = '%(friend_two)s' or friend_two = '%(friend_two)s') ",
                params=dict(
                    friend_one=str(friend_one_id[0]['id']),
                    friend_two=str(friend_two_id[0]['id'])))
            self.redirect('/')


class RequestsHandler(BaseHandler):
    async def get(self):
        if not self.current_user:
            self.redirect("/login")
        else:
            cur_id = await self.get_user_id(self.current_user)
            request_friends_name = await self.select(
                query=" SELECT u.username FROM users u JOIN ( " +
                      " SELECT * FROM ( " +
                      " SELECT friend_one, status FROM friends WHERE friend_two='%(id)s' ) fr WHERE fr.status='0') " +
                      " f ON f.friend_one=u.id; ",
                params=dict(id=cur_id[0]['id']))
            users = []
            res = []
            self.render("requests.html",
                        users=users,
                        data=res,
                        request_friends=request_friends_name,
                        see_all=False)


class PrivateMessages(BaseHandler):
    async def get(self):
        if not self.current_user:
            self.redirect("/login")
        else:
            senders = await self.select(
                query=" SELECT  sender, count(message) FROM chat " +
                      " WHERE reciever = '%(username)s' AND status = '0' GROUP BY sender; ",
                params=dict(username=self.get_current_user())
            )
            users = []
            res = []
            self.render("unreaded_messages.html",
                        users=users,
                        data=res,
                        unreaded=senders,
                        see_all=False)
