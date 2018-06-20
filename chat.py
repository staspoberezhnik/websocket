import tornado.ioloop
import tornado.web
import tornado.websocket
import asyncpg
from tornado import escape


class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        user = self.get_secure_cookie('user')
        return escape.xhtml_escape(user) if user else None


class MainHandler(BaseHandler):
    def get(self):

        if not self.current_user:
            self.redirect("/login")
        else:
            users = []
            name = tornado.escape.xhtml_escape(self.get_current_user())
            users.append(name)
            self.render("base.html", users=users)


class LoginHandler(BaseHandler):
    def get(self):
        users = []
        self.render('login.html', users=users)

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

        db_connection = await asyncpg.connect(user='provider',
                                              password='12345',
                                              database='websocket',
                                              host='127.0.0.1',
                                              port='5432'
                                              )
        await db_connection.execute('''
                INSERT INTO chat(author, message) VALUES($1, $2)
            ''', data['user'], data['message'])

        # values = await db_connetion.fetch('''SELECT * FROM chat''')
        # for value in values:
        #     print(value)

        await db_connection.close()

    def on_close(self):
        self.connections.remove(self)


class PrivateHandler(BaseHandler, tornado.web.RequestHandler):

    def get(self, user):
        users = []
        print(user)
        name = self.get_secure_cookie('user')
        users.append(name)
        self.render("private.html", users=users)


def make_app():
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/login", LoginHandler),
        (r'/logout', LogoutHandler),
        (r"/websocket", SimpleWebSocket),
        (r"/privatmessage/(?P<user>[-\w]+)/$", PrivateHandler),
    ],
        cookie_secret="__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__")


if __name__ == "__main__":
    app = make_app()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()
