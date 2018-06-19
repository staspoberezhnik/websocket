import tornado.ioloop
import tornado.web
import tornado.websocket
import asyncpg
import asyncio
import json


class MainHandler(tornado.web.RequestHandler):
    def get(self):

        self.render("index.html")


class SimpleWebSocket(tornado.websocket.WebSocketHandler):
    connections = set()
    # connections = dict()

    def check_origin(self, origin):
        return True

    def open(self):
        self.connections.add(self)

    async def on_message(self, message):
        [client.write_message(message) for client in self.connections]
        mes = json.loads(message)
        name = mes['user']
        print(name)

        conn = await asyncpg.connect(host='127.0.0.1',
                                     port='5432',
                                     user='provider',
                                     password='12345',
                                     database='websocket')

        await conn.execute('''
               INSERT INTO chat(message, author) VALUES($1, $2)
           ''', mes['message'], mes['user'])

        row = await conn.fetch(
            'SELECT * FROM chat')

        await conn.close()

    def on_close(self):
        self.connections.remove(self)


def make_app():
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/websocket", SimpleWebSocket)
    ])


if __name__ == "__main__":
    app = make_app()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()
