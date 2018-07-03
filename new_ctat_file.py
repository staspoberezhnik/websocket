import asyncio
import logging

import tornado.ioloop
import tornado.web
import tornado.websocket
import asyncpg
import tornado.platform.asyncio
from tornado import escape
import datetime
from decouple import config
import hashlib

from tornado.options import options

logger = logging.getLogger()

valid_chars = 'abcdefghijklmnopqrstuvwxyz' \
             'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' \
             'ЙЦУКЕНГШЩЗХЪЭЖДЛОРПАВЫФЯЧСМИТЬБЮЁ' \
             'ёйцукенгшщзхъэждлорпавыфячсмитьбю'


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


class MainHandler(BaseHandler):

    async def get(self):
        if not self.current_user:
            self.redirect("/login")
        else:

            res = await self.select('''SELECT sender,
             message, date_created FROM chat where reciever is %(receiver)s''', params=dict(receiver=None))
            users = []
            name = tornado.escape.xhtml_unescape(self.get_current_user())
            users.append(name)

            self.render("base.html", users=users, data=res)


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
        hash_password = hashlib.sha256(password.encode())

        for char in username:
            if char in valid_chars:
                continue
            else:
                flag = False
                break
        print(flag)
        if flag:

            res = await self.select('''SELECT username FROM users
                where username = '%(username)s' and password = '%(password)s' ''',
                                    params=dict(
                                           username=username,
                                           password=hash_password.hexdigest()))
            if res:
                print(res)
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

        hash_password = hashlib.sha256(password.encode())

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
    connections = set()

    def check_origin(self, origin):
        return True

    def open(self):
        self.connections.add(self)

    async def on_message(self, message):

        [client.write_message(message) for client in self.connections]
        data = tornado.escape.json_decode(message)
        print(data)

        await self.insert(
            table='chat',
            params=dict(
                sender=tornado.escape.xhtml_unescape(data['user']),
                message=data['message'],
                date_created=datetime.datetime.now()
            )
        )

    def on_close(self):
        self.connections.remove(self)


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
                values = await self.select('''SELECT sender, reciever,
                                            message,date_created FROM chat''')

                for value in values:
                    if value['sender'] == self.get_current_user() and value['reciever'] == user:
                        filtered_values.append(value)
                    if value['reciever'] == self.get_current_user() and value['sender'] == user:
                        received_values.append(value)
                    else:
                        continue
                print(filtered_values)
                print(received_values)
                send_to_user = user
                self.render("private.html", send_to=send_to_user, data=filtered_values, received_data=received_values)


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


class MakeApp(tornado.web.Application):
    pool = None

    def __init__(self):
        handlers = [
            (r"/", MainHandler),
            (r"/register", RegisterHandler),
            (r"/login", LoginHandler),
            (r'/logout', LogoutHandler),
            (r"/websocket", SimpleWebSocket),
            (r"/privatmessage/(?P<user>[-\w]+)/$", PrivateHandler),
            (r"/send_private", SendToUser),
        ]
        settings = dict(
                    cookie_secret="__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__",
                        )
        super(MakeApp, self).__init__(handlers, **settings)

    async def create_pool(self):
        self.pool = await asyncpg.create_pool(
            user=config('DB_USER'),
            password=config('DB_USER_PASSWORD'),
            database=config('DB_NAME'),
            host=config('DB_HOST'),
            port=config('DB_PORT')
        )


def main():
    loop = asyncio.get_event_loop()
    app = MakeApp()
    app.listen(config('PORT'))
    logger.warning('Starting server at http://%s:%s' % ('0.0.0.0', config('PORT')))
    loop.run_until_complete(app.create_pool())
    loop.run_forever()


if __name__ == "__main__":
    main()

