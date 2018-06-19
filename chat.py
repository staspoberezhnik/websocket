import tornado.ioloop
import tornado.web
import tornado.websocket
import asyncpg
from tornado import escape
import asyncio


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

    def on_close(self):
        self.connections.remove(self)


class PrivateMessage(SimpleWebSocket):
    pass


def make_app():
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/login", LoginHandler),
        (r'/logout',LogoutHandler),
        (r"/websocket", SimpleWebSocket),
        (r'/privatmes', PrivateMessage),
    ],
        cookie_secret="__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__")


if __name__ == "__main__":
    app = make_app()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()
