import asyncio
import os
import logging
import tornado.web
import asyncpg
import tornado.platform.asyncio
from decouple import config
from chat.handlers import MainHandler, RegisterHandler, LoginHandler, LogoutHandler, SimpleWebSocket, PrivateHandler, \
    SendToUser, NotificationHandler, AllUsersHandler, InviteHandler, AddToFriendsHandler, RemoveFromFriendsHandler,\
    RequestsHandler, PrivateMessages
from chat.urls import urls

logger = logging.getLogger()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class MakeApp(tornado.web.Application):
    pool = None

    def __init__(self):
        settings = dict(
                    cookie_secret="__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__",
                    template_path=os.path.join(BASE_DIR, "templates")
                        )

        super(MakeApp, self).__init__(handlers=urls, **settings)

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
