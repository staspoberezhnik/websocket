from chat.utils import valid_chars
import tornado.ioloop
import tornado.web
import tornado.websocket
import tornado.platform.asyncio
from tornado import escape
import datetime
from decouple import config
import hashlib


class BaseHandler(tornado.web.RequestHandler):
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



class MainHandler(BaseHandler):

    async def get(self):
        if not self.current_user:
            self.redirect("/login")
        else:

            res = await self.select('''SELECT sender,
             message, date_created FROM chat where reciever is %(receiver)s''', params=dict(receiver=None))
            self.render("base.html", data=res)


class LoginHandler(BaseHandler):
    def get(self):
        if self.current_user:
            self.redirect('/')
        else:
            users = []
            value = []
            errors = []
            self.render('login.html', users=users, data=value, errors=errors)

    async def post(self):
        flag = True
        users = []
        value = []
        errors = []
        username = self.get_argument("name", "")
        password = self.get_argument("password", "")
        hash_password = hashlib.sha256((password + config('SALT')).encode())

        for char in username:
            if char in valid_chars:
                continue
            else:
                flag = False
                break
        if flag:

            res = await self.select('''SELECT username FROM users
                where username = '%(username)s' and password = '%(password)s' ''',
                                    params=dict(
                                           username=username,
                                           password=hash_password.hexdigest()))
            if res:
                self.set_secure_cookie('user', res[0]['username'])
                self.redirect("/")
            else:
                errors = 'User or Password did not match. Try again'
                self.render('login.html', users=users, data=value, errors=errors)
        else:
            errors = 'Incorrect letters in Username. Try again'
            self.render('login.html', users=users, data=value, errors=errors)


class LogoutHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.clear_cookie('user')
        self.redirect('/')


class RegisterHandler(BaseHandler):
    def get(self):
        if self.current_user:
            self.redirect('/')
        else:
            users = []
            value = []
            errors = []
            self.render('register.html', users=users, data=value, errors=errors)

    async def post(self):
        users = []
        value = []
        flag = True
        username = self.get_argument("username", "")
        password = self.get_argument("password", "")

        hash_password = hashlib.sha256((password + config('SALT')).encode())

        for char in username:
            if char in valid_chars:
                continue
            else:
                flag = False
                break

        if flag:
            res = await self.select('''SELECT username FROM users
                            where username = '%(username)s'  ''',
                                    params=dict(
                                        username=username))
            if res:
                errors = 'Current Username already in use. Choose another one'
                self.render('register.html', users=users, data=value, errors=errors)
            else:
                await self.insert(
                    table='users',
                    params=dict(
                        username=username,
                        password=hash_password.hexdigest(),
                    )
                )
                self.set_secure_cookie("user", self.get_argument("username"))
                self.redirect("/")
        else:
            errors = 'Incorrect letters in Username. Try again'
            self.render('register.html', users=users, data=value, errors=errors)


class SimpleWebSocket(BaseHandler, tornado.websocket.WebSocketHandler):
    connections = dict()

    def check_origin(self, origin):
        return True

    def open(self):
        self.connections[self.get_current_user()] = self
        self.send_message(message_type='online_users', message=self.get_online_users(), send_all=True)

    async def on_message(self, message):
        self.send_message(message=message, send_all=True)
        data = tornado.escape.json_decode(message)

        await self.insert(
            table='chat',
            params=dict(
                sender=tornado.escape.xhtml_unescape(data['user']),
                message=data['message'],
                date_created=datetime.datetime.now()
            )
        )

    def on_close(self):
        self.connections.pop(self.get_current_user())
        self.send_message(message_type='online_users', message=self.get_online_users(), send_all=True)

    def send_message(self, message, message_type='chat', send_all=False):
        params = dict(message=dict(message_type=message_type, message=message))
        if send_all:
            for connection in self.connections.values():
                connection.write_message(**params)
        else:
            self.write_message(**params)

    def get_online_users(self):
        return list(set(self.connections.keys()))


class PrivateHandler(BaseHandler):

    async def get(self, user):

        if not self.current_user:
            self.redirect("/login")

        else:
            if user == self.get_current_user():
                self.redirect('/')
            else:
                filtered_values = []
                received_values = []
                receiver = await self.select('''SELECT username FROM users where username = '%(receiver)s' ''',
                                             params=dict(receiver=user))

                if receiver:
                    friend_one_id = await self.select('''SELECT id FROM users where username = '%(username)s' ''',
                                                   params=dict(username=self.current_user))
                    friend_two_id = await self.select('''SELECT id FROM users where username = '%(username)s' ''',
                                                   params=dict(username=user))

                    values = await self.select('''SELECT sender, reciever,
                                                message,date_created FROM chat''')

                    status = await self.select('''
                                 SELECT friend_one, friend_two,  status FROM friends where
                                 (friend_one = '%(friend_one)s' or friend_two = '%(friend_one)s')
                                 and (friend_one = '%(friend_two)s' or friend_two = '%(friend_two)s') ''',
                                               params=dict(friend_one=friend_one_id[0]['id'],
                                                           friend_two=friend_two_id[0]['id']))
                    if status:
                        if status[0]['status'] == '1':
                            status = 'Friends'
                        elif status[0]['friend_one'] == friend_one_id[0]['id'] and status[0]['status'] == '0':
                            status = 'Receive'
                        else:
                            status = 'Send'

                    for value in values:
                        if value['sender'] == self.get_current_user() and value['reciever'] == user:
                            filtered_values.append(value)
                        if value['reciever'] == self.get_current_user() and value['sender'] == user:
                            received_values.append(value)
                        else:
                            continue
                    send_to_user = user
                    self.render("private.html",
                                send_to=send_to_user,
                                data=filtered_values,
                                received_data=received_values,
                                status=status)
                else:
                    self.redirect('/')


class SendToUser(BaseHandler, tornado.websocket.WebSocketHandler):
    connections = dict()

    def check_origin(self, origin):
        return True

    def open(self):

        self.connections[self.get_current_user()] = self

    async def on_message(self, message):
        data = tornado.escape.json_decode(message)

        receiver = self.connections.get(data['send_to'])
        sender = self.connections.get(tornado.escape.xhtml_unescape(data['user']))
        if receiver:
            receiver.write_message(message)
        if sender:
            sender.write_message(message)

        await self.insert(
            table='chat',
            params=dict(
                sender=tornado.escape.xhtml_unescape(data['user']),
                reciever=data['send_to'],
                message=data['message'],
                date_created=datetime.datetime.now()))

    def on_close(self):
        self.connections.pop(self.get_current_user())


class NotificationHandler(BaseHandler):
    async def get(self):
        if not self.current_user:
            self.redirect("/login")
        else:

            cur_id = await self.select(''' SELECT id FROM users where
                                             username = '%(username)s' ''',
                                       params=dict(username=self.get_current_user()))
            print(cur_id)
            friends = await self.select(''' SELECT friend_one, friend_two FROM friends where
                                                         friend_one = '%(id_1)s' or friend_two = '%(id_1)s'
                                                          and status = '1'  ''',
                                        params=dict(id_1=cur_id[0]['id']))
            
            list_id = []
            for friend in friends:
                if friend['friend_one'] != cur_id[0]['id']:
                    list_id.append(friend['friend_one'])
                    if friend['friend_two'] != cur_id[0]['id']:
                        list_id.append(friend['friend_two'])

            print(list_id)
            friends_name = []
            if list_id:
                friends_name = await self.select(''' SELECT username FROM users where
                                                         id =  any(array%(id)s) ''',
                                                 params=dict(id=list_id))
            print(friends_name)
            users = []
            res = []

            self.render("friends_list.html", users=users, data=res, friends=friends_name)


class AllUsersHandler(BaseHandler):
    async def get(self):
        if not self.current_user:
            self.redirect("/login")
        else:
            res = await self.select('''SELECT username FROM users''')
            self.render("all_users.html", data=[], users=res)


class InviteHandler(BaseHandler):
    async def get(self, user):
        if not self.current_user:
            self.redirect("/login")
        else:

            friend_one = await self.select('''SELECT id FROM users where username = '%(username)s' ''',
                                           params=dict(username=self.current_user))
            friend_two = await self.select('''SELECT id FROM users where username = '%(username)s' ''',
                                           params=dict(username=user))
            await self.insert(
                table='friends',
                params=dict(
                    friend_one=str(friend_one[0]['id']),
                    friend_two=str(friend_two[0]['id'])))

            self.redirect('/')


class AddToFriendsHandler(BaseHandler):
    async def get(self, user):
        if not self.current_user:
            self.redirect("/login")
        else:

            friend_one = await self.select('''SELECT id FROM users where username = '%(username)s' ''',
                                           params=dict(username=self.current_user))
            friend_two = await self.select('''SELECT id FROM users where username = '%(username)s' ''',
                                           params=dict(username=user))
            await self.update(
                '''UPDATE friends SET status='1' where (friend_one = '%(friend_one)s' or friend_two = '%(friend_one)s')
                     and (friend_one = '%(friend_two)s' or friend_two = '%(friend_two)s') ''',
                params=dict(
                    friend_one=str(friend_one[0]['id']),
                    friend_two=str(friend_two[0]['id'])))

            self.redirect('/')


