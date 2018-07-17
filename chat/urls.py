from .handlers import *

urls = [
    (r"/", MainHandler),
    (r"/register", RegisterHandler),
    (r"/login", LoginHandler),
    (r'/logout', LogoutHandler),
    (r"/websocket", SimpleWebSocket),
    (r"/privatmessage/(?P<receiver>[-\w]+)/$", PrivateHandler),
    (r"/send_private/(?P<receiver>[-\w]+)$", SendToUser),
    (r"/friends", NotificationHandler),
    (r"/requests", RequestsHandler),
    (r"/all_users", AllUsersHandler),
    (r"/invite/(?P<user>[-\w]+)/$", InviteHandler),
    (r"/confirm/(?P<user>[-\w]+)/$", AddToFriendsHandler),
    (r"/remove/(?P<user>[-\w]+)/$", RemoveFromFriendsHandler),
    (r"/messages", PrivateMessages),
]
