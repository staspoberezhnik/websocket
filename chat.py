import tornado.ioloop
import tornado.web
import tornado.websocket
import asyncpg

from tornado import escape
import datetime
from decouple import config


def get_db_pool():
    return asyncpg.create_pool(
        user=config('DB_USER'),
        password=config('DB_USER_PASSWORD'),
        database=config('DB_NAME'),
        host=config('DB_HOST'),
        port=config('DB_PORT')
    )


class BaseHandler(tornado.web.RequestHandler):

    def get_current_user(self):
        user = self.get_secure_cookie('user')
        return escape.xhtml_escape(user) if user else None


class MainHandler(BaseHandler):

    async def get(self):
        if not self.current_user:
            self.redirect("/login")
        else:

            async with get_db_pool() as con:
                result = await con.fetch('''SELECT sender,
             message, date_created FROM chat where reciever is NULL''')

            users = []
            name = tornado.escape.xhtml_escape(self.get_current_user())
            users.append(name)
            self.render("base.html", users=users, data=result)


class LoginHandler(BaseHandler):
    def get(self):
        users = []
        value = []
        self.render('login.html', users=users, data=value)

    def post(self):
        self.set_secure_cookie("user", self.get_argument("name"))
        self.redirect("/")


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

        async with get_db_pool() as con:
            await con.execute('''
                INSERT INTO chat( sender, message, date_created) VALUES($1, $2, $3)
            ''', data['user'],
                 data['message'],
                 datetime.datetime.now())

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
                db_connection = await asyncpg.connect(user=config('DB_USER'),
                                                      password=config('DB_USER_PASSWORD'),
                                                      database=config('DB_NAME'),
                                                      host=config('DB_HOST'),
                                                      port=config('DB_PORT')
                                                      )
                values = await db_connection.fetch('''SELECT sender, reciever, message,
                 date_created FROM chat''')

                for value in values:
                    if value['sender'] == self.get_current_user() and value['reciever'] == user:
                        filtered_values.append(value)
                    else:
                        continue
                send_to_user = user
                self.render("private.html", send_to=send_to_user, data=filtered_values)


class SendToUser(BaseHandler, tornado.websocket.WebSocketHandler):

    connections = dict()

    def check_origin(self, origin):
        return True

    def open(self):

        self.connections[self.get_current_user()] = self

    async def on_message(self, message):
        data = tornado.escape.json_decode(message)
        receiver = self.connections.get(data['send_to'])
        sender = self.connections.get(data['user'])
        if receiver:
            receiver.write_message(message)
        if sender:
            sender.write_message(message)

        db_connection = await asyncpg.connect(user=config('DB_USER'),
                                              password=config('DB_USER_PASSWORD'),
                                              database=config('DB_NAME'),
                                              host=config('DB_HOST'),
                                              port=config('DB_PORT')
                                              )
        await db_connection.execute('''
                        INSERT INTO chat( sender,reciever, message, date_created) VALUES($1, $2, $3, $4)
                    ''', data['user'],
                         data['send_to'],
                         data['message'],
                         datetime.datetime.now())

        await db_connection.close()

    def on_close(self):
        self.connections.pop(self.get_current_user())


def make_app():
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/login", LoginHandler),
        (r'/logout', LogoutHandler),
        (r"/websocket", SimpleWebSocket),
        (r"/privatmessage/(?P<user>[-\w]+)/$", PrivateHandler),
        (r"/send_private", SendToUser),
    ],
        cookie_secret="__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__",
    )


if __name__ == "__main__":
    app = make_app()
    app.listen(config('PORT'))
    tornado.ioloop.IOLoop.current().start()

