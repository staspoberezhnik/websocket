import hashlib

from decouple import config
from tornado.web import authenticated

from chat.handlers import BaseHandler
from chat.utils import valid_chars


class LoginHandler(BaseHandler):
    def prepare(self):
        return super(BaseHandler, self).prepare()

    def get(self):
        self.render('login.html', users=[], data=[], errors=[])

    async def post(self):
        flag = True
        users = []
        value = []
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
            res = await self.select(
                query="SELECT username FROM users where username = '%(username)s' and password = '%(password)s' ",
                params=dict(username=username,
                            password=hash_password.hexdigest())
            )
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
    @authenticated
    def get(self):
        self.clear_cookie('user')
        self.redirect('/')


class RegisterHandler(BaseHandler):
    def get(self):
        super(RegisterHandler, self).get()
        self.render('register.html', users=[], data=[], errors=[])

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
            res = await self.select(
                query="SELECT username FROM users where username = '%(username)s' ",
                params=dict(username=username)
            )
            if res:
                errors = 'Current Username already in use. Choose another one'
                self.render('register.html', users=users, data=value, errors=errors)
            else:
                await self.insert(
                    table='users',
                    params=dict(
                        username=username,
                        password=hash_password.hexdigest())
                )
                self.set_secure_cookie("user", self.get_argument("username"))
                self.redirect("/")
        else:
            errors = 'Incorrect letters in Username. Try again'
            self.render('register.html', users=users, data=value, errors=errors)
