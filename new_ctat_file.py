import tornado.ioloop
import tornado.web
import tornado.websocket
import asyncpg
import tornado.platform.asyncio
from tornado import escape
import datetime
from decouple import config
import string

valid_chars = 'abcdefghijklmnopqrstuvwxyz' \
             'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' \
             'ЙЦУКЕНГШЩЗХЪЭЖДЛОРПАВЫФЯЧСМИТЬБЮЁ' \
             'ёйцукенгшщзхъэждлорпавыфячсмитьбю'



class BaseHandler(tornado.web.RequestHandler):

    def get_current_user(self):
        user = self.get_secure_cookie('user')
        return escape.xhtml_unescape(user) if user else None

    async def get_db_pool(self):
        return await asyncpg.create_pool(
            user=config('DB_USER'),
            password=config('DB_USER_PASSWORD'),
            database=config('DB_NAME'),
            host=config('DB_HOST'),
            port=config('DB_PORT')
        )

    async def select(self, query, params=None):
        if params:
            for key, value in params.items():
                if value is None:
                    value = 'Null'
                    params[key] = value
        if params:
            query = query % params
        # print(query)
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
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
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
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
            self.render('login.html', users=users, data=value)

    def post(self):
        flag = True
        user = tornado.escape.xhtml_unescape(self.get_argument("name"))
        for char in user:
            if char in valid_chars:
                continue
            else:
                flag = False
                break
        if flag:
            self.set_secure_cookie("user", tornado.escape.xhtml_unescape(self.get_argument("name")))
            self.redirect("/")
        else:
            self.redirect('/login')


class LogoutHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.clear_cookie('user')
        self.redirect('/')


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
        user_1 = tornado.escape.url_unescape(user)
        print(user_1)

        if not self.current_user:
            self.redirect("/login")

        else:
            if user == self.get_current_user():
                self.redirect('/')
            else:
                print(user)
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
        print(data)

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

    def __init__(self):
        handlers = [
            (r"/", MainHandler),
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


def main():

    app = MakeApp()
    app.listen(config('PORT'))
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()

