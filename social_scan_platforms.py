import re
import json
import random
import string
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from bs4 import BeautifulSoup as bs


class QueryError(Exception):
    pass


class PlatformChecker:
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.121 Safari/537.36',
    }
    UNEXPECTED_CONTENT_TYPE_ERROR_MESSAGE = "Unexpected content type {}. You might be sending too many requests. Use a proxy or wait before trying again."
    TOKEN_ERROR_MESSAGE = "Could not retrieve token. You might be sending too many requests. Use a proxy or wait before trying again."
    TOO_MANY_REQUEST_ERROR_MESSAGE = "Requests denied by platform due to excessive requests. Use a proxy or wait before trying again."

    # Subclasses can implement 3 methods depending on requirements: prerequest(), check_username() and check_email()
    # 1: Be as explicit as possible in handling all cases
    # 2: Do not include any queries that will lead to side-effects on users (e.g. submitting sign up forms)
    # OK to omit checks for whether a key exists when parsing the JSON response. KeyError is handled by the parent coroutine.

    def get_token(self):
        """
        Retrieve and return platform token using the `prerequest` method specified in the class

        Normal calls will not be able to take advantage of this as all tokens are retrieved concurrently
        This only applies to when tokens are retrieved before main queries with -c
        Adds 1-2s to overall running time but halves HTTP requests sent for bulk queries
        """
        if self.prerequest_sent:
            if self.token is None:
                raise QueryError(PlatformChecker.TOKEN_ERROR_MESSAGE)
            return self.token
        else:
            self.token = self.prerequest()
            self.prerequest_sent = True
            if self.token is None:
                raise QueryError(PlatformChecker.TOKEN_ERROR_MESSAGE)
            return self.token

    def response_failure(self, query, *, message="Failure"):
        return PlatformResponse(
            platform=Platforms(self.__class__),
            query=query,
            available=False,
            valid=False,
            success=False,
            message=message,
            link=None,
            data=None
        )

    def response_available(self, query, *, message="Available"):
        return PlatformResponse(
            platform=Platforms(self.__class__),
            query=query,
            available=True,
            valid=True,
            success=True,
            message=message,
            link=None,
            data=None
        )

    def response_unavailable(self, query, *, message="Unavailable", link=None, data=None):
        return PlatformResponse(
            platform=Platforms(self.__class__),
            query=query,
            available=False,
            valid=True,
            success=True,
            message=message,
            link=link,
            data=data
        )

    def response_invalid(self, query, *, message="Invalid"):
        return PlatformResponse(
            platform=Platforms(self.__class__),
            query=query,
            available=False,
            valid=False,
            success=True,
            message=message,
            link=None,
            data=None,
        )

    def response_unavailable_or_invalid(self, query, *, message, unavailable_messages, link=None):
        if any(x in message for x in unavailable_messages):
            return self.response_unavailable(query, message=message, link=link)
        else:
            return self.response_invalid(query, message=message)

    def _request(self, method, url, **kwargs):
        proxy = (
            self.proxy_list[self.request_count %
                            len(self.proxy_list)] if self.proxy_list else None
        )
        self.request_count += 1
        if "headers" in kwargs:
            kwargs["headers"].update(PlatformChecker.DEFAULT_HEADERS)
        else:
            kwargs["headers"] = PlatformChecker.DEFAULT_HEADERS
        return self.session.request(method, url, timeout=15,
                                    **kwargs)

    def post(self, url, **kwargs):
        return self._request("POST", url, **kwargs)

    def get(self, url, **kwargs):
        return self._request("GET", url, **kwargs)

    @staticmethod
    def get_json(request):
        if not request.headers["Content-Type"].startswith("application/json"):
            raise QueryError(
                PlatformChecker.UNEXPECTED_CONTENT_TYPE_ERROR_MESSAGE.format(
                    request.headers["Content-Type"]
                )
            )
        else:
            return request.json()

    def __init__(self, session, proxy_list=[]):
        self.session = session
        self.proxy_list = proxy_list
        self.request_count = 0
        self.prerequest_sent = False
        self.token = None

    def create_random_pass(self, length, use_letters=True,
                           use_digits=True, use_punc=True):
        sample = ''
        if use_letters:
            sample += ''.join(random.choice(string.ascii_letters)
                              for i in range(int(0.65 * length)))
        if use_digits:
            sample += ''.join(random.choice(string.digits)
                              for i in range(int(0.25 * length)))
        if use_punc:
            sample += ''.join(random.choice('@_#&')
                              for i in range(int(0.1 * length)))
        passwd = list(sample)
        random.shuffle(passwd)
        return ''.join(passwd)


class Snapchat(PlatformChecker):
    URL = "https://accounts.snapchat.com/accounts/login"
    ENDPOINT = "https://accounts.snapchat.com/accounts/get_username_suggestions"
    USERNAME_TAKEN_MSGS = ["is already taken", "is currently unavailable"]

    def prerequest(self):
        with self.get(Snapchat.URL) as r:
            cookies = r.headers.getall("Set-Cookie")
            for cookie in cookies:
                match = re.search(r"xsrf_token=([\w-]*);", cookie)
                if match:
                    token = match.group(1)
                    return token

    async def check_username(self, username):
        token = self.get_token()
        with self.post(
            Snapchat.ENDPOINT,
            data={"requested_username": username, "xsrf_token": token},
            cookies={"xsrf_token": token},
        ) as r:
            # Non-JSON received if too many requests
            json_body = self.get_json(r)
            if "error_message" in json_body["reference"]:
                return self.response_unavailable_or_invalid(
                    username,
                    message=json_body["reference"]["error_message"],
                    unavailable_messages=Snapchat.USERNAME_TAKEN_MSGS,
                )
            elif json_body["reference"]["status_code"] == "OK":
                return self.response_available(username)

    # Email: Snapchat doesn't associate email addresses with accounts


class Instagram(PlatformChecker):
    URL = "https://instagram.com"
    ENDPOINT = "https://www.instagram.com/accounts/web_create_ajax/attempt/"
    USERNAME_TAKEN_MSGS = [
        "This username isn't available.",
        "A user with that username already exists.",
    ]
    USERNAME_LINK_FORMAT = "https://www.instagram.com/{}"

    def prerequest(self):
        with self.get(Instagram.URL) as r:
            if "csrftoken" in r.cookies:
                token = r.cookies["csrftoken"].value
                return token

    def check_username(self, username):
        token = self.get_token()
        with self.post(
            Instagram.ENDPOINT, data={"username": username}, headers={"x-csrftoken": token}
        ) as r:
            json_body = self.get_json(r)
            # Too many requests
            if json_body["status"] == "fail":
                return self.response_failure(username, message=json_body["message"])
            if "username" in json_body["errors"]:
                return self.response_unavailable_or_invalid(
                    username,
                    message=json_body["errors"]["username"][0]["message"],
                    unavailable_messages=Instagram.USERNAME_TAKEN_MSGS,
                    link=Instagram.USERNAME_LINK_FORMAT.format(username),
                )
            else:
                return self.response_available(username)

    def check_email(self, email):
        token = self.get_token()
        print(token)
        with self.post(
            Instagram.ENDPOINT, data={"email": email}, headers={"x-csrftoken": token}
        ) as r:
            json_body = self.get_json(r)
            # Too many requests
            if json_body["status"] == "fail":
                return self.response_failure(email, message=json_body["message"])
            if "email" not in json_body["errors"]:
                return self.response_available(email)
            else:
                message = json_body["errors"]["email"][0]["message"]
                if json_body["errors"]["email"][0]["code"] == "invalid_email":
                    return self.response_invalid(email, message=message)
                else:
                    return self.response_unavailable(email, message=message)


class GitHub(PlatformChecker):
    URL = "https://github.com/join"
    USERNAME_ENDPOINT = "https://github.com/signup_check/username"
    EMAIL_ENDPOINT = "https://github.com/signup_check/email"
    # [username taken, reserved keyword (Username __ is unavailable)]
    USERNAME_TAKEN_MSGS = ["already taken", "unavailable", "not available"]
    USERNAME_LINK_FORMAT = "https://github.com/{}"

    token_regex = re.compile(
        r'<auto-check src="/signup_check/username[\s\S]*?value="([\S]+)"[\s\S]*<auto-check src="/signup_check/email[\s\S]*?value="([\S]+)"'
    )
    tag_regex = re.compile(r"<[^>]+>")

    def prerequest(self):
        with self.get(GitHub.URL) as r:
            text = r.text
            match = self.token_regex.search(text)
            if match:
                username_token = match.group(1)
                email_token = match.group(2)
                return (username_token, email_token)

    def check_username(self, username):
        pr = self.get_token()
        (username_token, _) = pr
        with self.post(
            GitHub.USERNAME_ENDPOINT,
            data={"value": username, "authenticity_token": username_token},
        ) as r:
            if r.status_code == 422:
                text = r.text
                text = self.tag_regex.sub("", text).strip()
                return self.response_unavailable_or_invalid(
                    username,
                    message=text,
                    unavailable_messages=GitHub.USERNAME_TAKEN_MSGS,
                    link=GitHub.USERNAME_LINK_FORMAT.format(username),
                )
            elif r.status_code == 200:
                return self.response_available(username)
            elif r.status_code == 429:
                return self.response_failure(
                    username, message=PlatformChecker.TOO_MANY_REQUEST_ERROR_MESSAGE
                )

    def check_email(self, email):
        pr = self.get_token()
        if pr is None:
            return self.response_failure(email, message=PlatformChecker.TOKEN_ERROR_MESSAGE)
        else:
            (_, email_token) = pr
        with self.post(
            GitHub.EMAIL_ENDPOINT, data={
                "value": email, "authenticity_token": email_token},
        ) as r:
            if r.status_code == 422:
                text = r.text
                return self.response_unavailable(email, message=text)
            elif r.status_code == 200:
                return self.response_available(email)
            elif r.status_code == 429:
                return self.response_failure(
                    email, message=PlatformChecker.TOO_MANY_REQUEST_ERROR_MESSAGE
                )


class Tumblr(PlatformChecker):
    URL = "https://tumblr.com/register"
    ENDPOINT = "https://www.tumblr.com/svc/account/register"
    USERNAME_TAKEN_MSGS = [
        "That's a good one, but it's taken",
        "Someone beat you to that username",
        "Try something else, that one is spoken for",
    ]
    USERNAME_LINK_FORMAT = "https://{}.tumblr.com"

    SAMPLE_UNUSED_EMAIL = "akc2rW33AuSqQWY8@gmail.com"
    SAMPLE_PASSWORD = "correcthorsebatterystaple"
    SAMPLE_UNUSED_USERNAME = "akc2rW33AuSqQWY8"

    def prerequest(self):
        with self.get(Tumblr.URL) as r:
            text = r.text
            match = re.search(
                r'<meta name="tumblr-form-key" id="tumblr_form_key" content="([^\s]*)">', text
            )
            if match:
                token = match.group(1)
                return token

    def _check(self, email=SAMPLE_UNUSED_EMAIL, username=SAMPLE_UNUSED_USERNAME):
        query = email if username == Tumblr.SAMPLE_UNUSED_USERNAME else username
        token = self.get_token()
        with self.post(
            Tumblr.ENDPOINT,
            data={
                "action": "signup_account",
                "form_key": token,
                "user[email]": email,
                "user[password]": Tumblr.SAMPLE_PASSWORD,
                "tumblelog[name]": username,
            },
        ) as r:
            json_body = self.get_json(r)
            if username == query:
                if "usernames" in json_body or len(json_body["errors"]) > 0:
                    return self.response_unavailable_or_invalid(
                        query,
                        message=json_body["errors"][0],
                        unavailable_messages=Tumblr.USERNAME_TAKEN_MSGS,
                        link=Tumblr.USERNAME_LINK_FORMAT.format(query),
                    )
                elif json_body["errors"] == []:
                    return self.response_available(query)
            elif email == query:
                if "This email address is already in use." in json_body["errors"]:
                    return self.response_unavailable(query, message=json_body["errors"][0],)
                elif "This email address isn't correct. Please try again." in json_body["errors"]:
                    return self.response_invalid(query, message=json_body["errors"][0])
                elif json_body["errors"] == []:
                    return self.response_available(query)

    async def check_username(self, username):
        return self._check(username=username)

    def check_email(self, email):
        return self._check(email=email)


class GitLab(PlatformChecker):
    URL = "https://gitlab.com/users/sign_in"
    ENDPOINT = "https://gitlab.com/users/{}/exists"
    USERNAME_LINK_FORMAT = "https://gitlab.com/{}"

    async def check_username(self, username):
        # Custom matching required as validation is implemented locally and not server-side by GitLab
        if not re.fullmatch(
            r"[a-zA-Z0-9_\.][a-zA-Z0-9_\-\.]*[a-zA-Z0-9_\-]|[a-zA-Z0-9_]", username
        ):
            return self.response_invalid(
                username, message="Please create a username with only alphanumeric characters."
            )
        with self.get(
            GitLab.ENDPOINT.format(username), headers={"X-Requested-With": "XMLHttpRequest"}
        ) as r:
            # Special case for usernames
            if r.status == 401:
                return self.response_unavailable(
                    username, link=GitLab.USERNAME_LINK_FORMAT.format(username)
                )
            json_body = self.get_json(r)
            if json_body["exists"]:
                return self.response_unavailable(
                    username, link=GitLab.USERNAME_LINK_FORMAT.format(username)
                )
            else:
                return self.response_available(username)

    # Email: GitLab requires a reCAPTCHA token to check email address usage which we cannot bypass


class Reddit(PlatformChecker):
    URL = "https://reddit.com"
    ENDPOINT = "https://www.reddit.com/api/check_username.json"
    USERNAME_TAKEN_MSGS = [
        "that username is already taken",
        "that username is taken by a deleted account",
    ]
    USERNAME_LINK_FORMAT = "https://www.reddit.com/u/{}"

    async def check_username(self, username):
        # Custom user agent required to overcome rate limits for Reddit API
        with self.post(Reddit.ENDPOINT, data={"user": username}) as r:
            json_body = self.get_json(r)
            if "error" in json_body and json_body["error"] == 429:
                return self.response_failure(
                    username, message=PlatformChecker.TOO_MANY_REQUEST_ERROR_MESSAGE
                )
            elif "json" in json_body:
                return self.response_unavailable_or_invalid(
                    username,
                    message=json_body["json"]["errors"][0][1],
                    unavailable_messages=Reddit.USERNAME_TAKEN_MSGS,
                    link=Reddit.USERNAME_LINK_FORMAT.format(username),
                )
            elif json_body == {}:
                return self.response_available(username)

    # Email: You can register multiple Reddit accounts under the same email address so not possible to check if an address is in use


class Twitter(PlatformChecker):
    URL = "https://twitter.com/signup"
    USERNAME_ENDPOINT = "https://api.twitter.com/i/users/username_available.json"
    EMAIL_ENDPOINT = "https://api.twitter.com/i/users/email_available.json"
    # [account in use, account suspended]
    USERNAME_TAKEN_MSGS = ["That username has been taken", "unavailable"]
    USERNAME_LINK_FORMAT = "https://twitter.com/{}"

    async def check_username(self, username):
        with self.get(Twitter.USERNAME_ENDPOINT, params={"username": username}) as r:
            json_body = self.get_json(r)
            message = json_body["desc"]
            if json_body["valid"]:
                return self.response_available(username, message=message)
            else:
                return self.response_unavailable_or_invalid(
                    username,
                    message=message,
                    unavailable_messages=Twitter.USERNAME_TAKEN_MSGS,
                    link=Twitter.USERNAME_LINK_FORMAT.format(username),
                )

    def check_email(self, email):
        with self.get(Twitter.EMAIL_ENDPOINT, params={"email": email}) as r:
            json_body = self.get_json(r)
            message = json_body["msg"]
            if not json_body["valid"] and not json_body["taken"]:
                return self.response_invalid(email, message=message)

            if json_body["taken"]:
                return self.response_unavailable(email, message=message)
            else:
                return self.response_available(email, message=message)


class Pinterest(PlatformChecker):
    URL = "https://www.pinterest.com"
    EMAIL_ENDPOINT = "https://www.pinterest.com/_ngjs/resource/EmailExistsResource/get/"

    def check_email(self, email):
        data = '{"options": {"email": "%s"}, "context": {}}' % email
        with self.get(
            Pinterest.EMAIL_ENDPOINT, params={"source_url": "/", "data": data}
        ) as r:
            json_body = self.get_json(r)
            email_exists = json_body["resource_response"]["data"]
            if email_exists:
                return self.response_unavailable(email)
            else:
                return self.response_available(email)


class Lastfm(PlatformChecker):
    URL = "https://www.last.fm/join"
    ENDPOINT = "https://www.last.fm/join/partial/validate"
    USERNAME_TAKEN_MSGS = ["Sorry, this username isn't available."]
    USERNAME_LINK_FORMAT = "https://www.last.fm/user/{}"

    def prerequest(self):
        with self.get(Lastfm.URL) as r:
            if "csrftoken" in r.cookies:
                token = r.cookies["csrftoken"]
                return token

    def _check(self, username="", email=""):
        token = self.get_token()
        data = {"csrfmiddlewaretoken": token,
                "userName": username, "email": email}
        headers = {
            "Accept": "*/*",
            "Referer": "https://www.last.fm/join",
            "X-Requested-With": "XMLHttpRequest",
            "Cookie": f"csrftoken={token}",
        }
        with self.post(Lastfm.ENDPOINT, data=data, headers=headers) as r:
            json_body = self.get_json(r)
            if email:
                if json_body["email"]["valid"]:
                    return self.response_available(
                        email, message=json_body["email"]["success_message"]
                    )
                else:
                    return self.response_unavailable(
                        email, message=json_body["email"]["error_messages"][0]
                    )
            elif username:
                if json_body["userName"]["valid"]:
                    return self.response_available(
                        username, message=json_body["userName"]["success_message"]
                    )
                else:
                    return self.response_unavailable_or_invalid(
                        username,
                        message=re.sub(
                            "<[^<]+?>", "", json_body["userName"]["error_messages"][0]),
                        unavailable_messages=Lastfm.USERNAME_TAKEN_MSGS,
                        link=Lastfm.USERNAME_LINK_FORMAT.format(username),
                    )

    def check_email(self, email):
        return self._check(email=email)

    def check_username(self, username):
        return self._check(username=username)


class Spotify(PlatformChecker):
    URL = "https://www.spotify.com/signup/"
    EMAIL_ENDPOINT = "https://spclient.wg.spotify.com/signup/public/v1/account"

    def check_email(self, email):
        with self.get(Spotify.EMAIL_ENDPOINT, params={"validate": 1, "email": email}) as r:
            json_body = self.get_json(r)
            if json_body["status"] == 1:
                return self.response_available(email)
            elif json_body["status"] == 20:
                return self.response_unavailable(email, message=json_body["errors"]["email"])
            else:
                return self.response_failure(email, message=json_body["errors"]["email"])


# class Yahoo(PlatformChecker):
#     URL = "https://login.yahoo.com/account/create"
#     USERNAME_ENDPOINT = "https://login.yahoo.com/account/module/create?validateField=yid"

#     # Modified from Yahoo source
#     error_messages = {
#         "IDENTIFIER_EXISTS": "A Yahoo account already exists with this username.",
#         "RESERVED_WORD_PRESENT": "A reserved word is present in the username",
#         "FIELD_EMPTY": "This is required.",
#         "SOME_SPECIAL_CHARACTERS_NOT_ALLOWED": "You can only use letters, numbers, full stops (‘.’) and underscores (‘_’) in your username",
#         "CANNOT_END_WITH_SPECIAL_CHARACTER": "Your username has to end with a letter or a number",
#         "CANNOT_HAVE_MORE_THAN_ONE_PERIOD": "You can’t have more than one ‘.’ in your username.",
#         "NEED_AT_LEAST_ONE_ALPHA": "Please use at least one letter in your username",
#         "CANNOT_START_WITH_SPECIAL_CHARACTER_OR_NUMBER": "Your username has to start with a letter",
#         "CONSECUTIVE_SPECIAL_CHARACTERS_NOT_ALLOWED": "You can’t have more than one ‘.’ or ‘_’ in a row.",
#         "LENGTH_TOO_SHORT": "That username is too short, please use a longer one.",
#         "LENGTH_TOO_LONG": "That username is too long, please use a shorter one.",
#     }

#     regex = re.compile(r"v=1&s=([^\s]*)")

#     def prerequest(self):
#         with self.get(Yahoo.URL) as r:
#             if "AS" in r.cookies:
#                 match = self.regex.search(r.cookies["AS"].value)
#                 if match:
#                     return match.group(1)

#     async def check_username(self, username):
#         token = self.get_token()
#         with self.post(
#             Yahoo.USERNAME_ENDPOINT,
#             data={"specId": "yidReg", "acrumb": token, "yid": username},
#             headers={"X-Requested-With": "XMLHttpRequest"},
#         ) as r:
#             json_body = self.get_json(r)
#             if json_body["errors"][2]["name"] != "yid":
#                 return self.response_available(username)
#             else:
#                 error = json_body["errors"][2]["error"]
#                 error_pretty = self.error_messages.get(
#                     error, error.replace("_", " ").capitalize())
#                 if error == "IDENTIFIER_EXISTS" or error == "RESERVED_WORD_PRESENT":
#                     return self.response_unavailable(username, message=error_pretty)
#                 else:
#                     return self.response_invalid(username, message=error_pretty)


class Firefox(PlatformChecker):
    URL = "https://accounts.firefox.com/signup"
    EMAIL_ENDPOINT = "https://api.accounts.firefox.com/v1/account/status"

    def check_email(self, email):
        with self.post(Firefox.EMAIL_ENDPOINT, data={"email": email}) as r:
            json_body = self.get_json(r)
            if "error" in json_body:
                return self.response_failure(email, message=json_body["message"])
            elif json_body["exists"]:
                return self.response_unavailable(email)
            else:
                return self.response_available(email)


class Jetblue(PlatformChecker):
    URL = "https://trueblue.jetblue.com"
    EMAIL_ENDPOINT = "https://trueblue.jetblue.com/b2c/search?customer.address.email={}"

    def check_email(self, email):
        with self.get(Jetblue.EMAIL_ENDPOINT.format(email)) as r:
            json_body = r.json()
            if json_body["found"] is False:
                return self.response_available(email)
            elif json_body["found"] is True:
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Foursquare(PlatformChecker):
    URL = "https://foursquare.com/login?continue=%2Fedit"
    EMAIL_ENDPOINT = "https://api.foursquare.com/v2/users/lookup?locale=en&explicit-lang=false&v={}&email={}&oauth_token={}"

    def prerequest(self):
        with self.get(Foursquare.URL) as r:
            text = r.text
            soup = bs(text, 'lxml')
            script = soup.find('script', type="text/javascript",
                               text=re.compile("API_BASE: 'https://api.foursquare.com/'"))
            print(script)
            token = script.get_text().split(
                'API_TOKEN:')[-1].split('API_IFRAME')[0].strip()[1:-2]
            return token

    def check_email(self, email):
        current_date = datetime.today().strftime("%Y%m%d")
        # token = self.get_token()
        token = 'QEJ4AQPTMMNB413HGNZ5YDMJSHTOHZHMLZCAQCCLXIX41OMP'
        with self.get(Foursquare.EMAIL_ENDPOINT.format(current_date, email, token)) as r:
            json_body = r.json()
            if 'errorType' in json_body["meta"]:
                return self.response_available(email)
            elif 'user' in json_body["response"]:
                return self.response_unavailable(email, data=json_body)
            else:
                return self.response_failure(email)


class Latam(PlatformChecker):
    EMAIL_ENDPOINT = "https://bff.latam.com/ws/api/customerportal/v1/rest/proxy/customerProfile/aliases?email={}"

    def check_email(self, email):
        with self.get(Latam.EMAIL_ENDPOINT.format(email)) as r:
            json_body = r.json()
            if json_body['data']['matches'] == 0:
                return self.response_available(email)
            elif json_body['data']['matches'] > 0:
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Frontier(PlatformChecker):
    EMAIL_ENDPOINT = "https://booking.flyfrontier.com/F9/Verify?email={}"

    def check_email(self, email):
        headers = {
            'Origin': 'https://www.flyfrontier.com'
        }
        with self.get(Frontier.EMAIL_ENDPOINT.format(email),
                      headers=headers) as r:
            json_body = r.json()
            # print(json_body)
            if json_body['exists'] is False:
                return self.response_available(email)
            elif json_body['exists'] is True:
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Booking(PlatformChecker):
    URL = "https://www.booking.com/index.en-gb.html"
    EMAIL_ENDPOINT = "https://account.booking.com/api/identity/authenticate/v1.0/enter/email/submit?op_token={}"

    def prerequest(self):
        with self.get(Booking.URL) as r1:
            text = r1.text
            soup = bs(text, 'lxml')
            # register_link = soup.find(
            #     'li', id='current_account_create').find('a')['href']
            register_link = soup.find('a', {'class': 'iam_login_link'})['href']
            with self.get(register_link) as r2:
                text = r2.text
                soup = bs(text, 'lxml')
                script = soup.find('script', text=re.compile("var booking"))
                # print(script)
                json_str = script.get_text().split(
                    "booking.env=")[-1].split('var booking_extra')[0].strip()[:-1]
                json_resp = json.loads(json_str)
                token = json_resp['op_token']
                return token

    def check_email(self, email):
        token = self.get_token()
        headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json',
            'X-Booking-Client': 'ap'
        }
        payload = json.dumps({
            "identifier": {
                "type": "IDENTIFIER_TYPE__EMAIL",
                "value": email
            }
        })
        with self.post(Booking.EMAIL_ENDPOINT.format(token),
                       data=payload,
                       headers=headers) as r:
            json_body = r.json()
            if 'nextStep' in json_body:
                if json_body['nextStep'] == 'STEP_REGISTER__PASSWORD':
                    return self.response_available(email)
                elif json_body['nextStep'] == 'STEP_SIGN_IN__PASSWORD':
                    return self.response_unavailable(email)
            elif 'errors' in json_body and 1400 in json_body['errors']:
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Skyscanner(PlatformChecker):
    EMAIL_ENDPOINT = "https://www.skyscanner.com/g/traveller-auth-service/accounts/v2/search"

    def check_email(self, email):
        payload = {"email": email}
        headers = {
            'Origin': 'https://www.skyscanner.com',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:80.0) Gecko/20100101 Firefox/80.0',
            'X-Requested-With': 'XMLHttpRequest',
        }
        with self.post(Skyscanner.EMAIL_ENDPOINT,
                       json=payload,
                       headers=headers) as r:
            if r.status_code == 404:
                return self.response_available(email)
            elif r.status_code == 200:
                json_body = r.json()
                if json_body['providers'][0]['state'] == "UNVERIFIED":
                    return self.response_unavailable(email)
                elif json_body['providers'][0]['state'] == "VERIFIED":
                    return self.response_unavailable(email)
                else:
                    return self.response_failure(email)
            else:
                return self.response_failure(email)


class Vrbo(PlatformChecker):
    EMAIL_ENDPOINT = "https://www.vrbo.com/auth/aam/v3/status"

    def check_email(self, email):
        payload = {"emailAddress": email}
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:80.0) Gecko/20100101 Firefox/80.0'
        }
        with self.post(Vrbo.EMAIL_ENDPOINT,
                       json=payload,
                       headers=headers) as r:
            json_body = r.json()
            if "LOGIN_UMS" in json_body["authType"]:
                return self.response_unavailable(email)
            elif any(x in json_body["authType"] for x in ["LOGIN_GOOGLE", "SIGNUP"]):
                return self.response_available(email)
            else:
                return self.response_failure(email)


class Spicejet(PlatformChecker):
    URL = "https://book.spicejet.com/Login.aspx"
    EMAIL_ENDPOINT = "https://book.spicejet.com/SpiceMoneyInfoAjax-resource.aspx?request=IsEmailIdExists&emailAddress={}"

    def prerequest(self):
        with self.get(Spicejet.URL) as r:
            return r.cookies

    def check_email(self, email):
        cookies = self.get_token()
        with self.post(Spicejet.EMAIL_ENDPOINT.format(email),
                       cookies=cookies) as r:
            resp_text = r.text
            if resp_text.strip() == "SUCCESS":
                return self.response_available(email)
            elif resp_text.strip() == "Account is already registered for SpiceClub. Please provide another email address to proceed with SpiceClub Registration.":
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Malaysia(PlatformChecker):
    URL = "https://malaysiaairlines.com"
    EMAIL_ENDPOINT = "https://member.malaysiaairlines.com{}/SelfAsserted?tx=StateProperties={}&p=B2C_1A_PROD_SIGNUP_SIGNIN"

    def prerequest(self):
        with self.get(Malaysia.URL) as r1:
            text1 = r1.text
            soup = bs(text1, 'lxml')
            login_url = soup.select_one(
                'div[id="mob_mh-logged-in-user-menu"] li.menu-item a')['href']
            with self.get(login_url) as r2:
                text2 = r2.text
                soup = bs(text2, 'lxml')
                script = soup.find('script', text=re.compile("var SETTINGS"))
                json_str = script.get_text().split(
                    "var SETTINGS = ")[-1].strip()[:-1]
                json_resp = json.loads(json_str)
                csrf_token = json_resp["csrf"]
                state_id = json_resp["transId"]
                page_id = json_resp["hosts"]["tenant"]
                return csrf_token, state_id, page_id, r2.cookies

    def check_email(self, email):
        csrf_token, state_id, page_id, cookies = self.get_token()
        random_pass = "vfs3M0Bz8$04QSh5"
        payload = f'request_type=RESPONSE&signInName={email}&password={random_pass}'
        headers = {
            'X-CSRF-TOKEN': csrf_token,
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        with self.post(Malaysia.EMAIL_ENDPOINT.format(page_id, state_id),
                       data=payload,
                       headers=headers) as r:
            resp_text = r.text
            json_body = json.loads(resp_text)
            if json_body["message"] == "We can't seem to find your account. Create one now?":
                return self.response_available(email)
            elif json_body["message"] == "Your email ID / password is incorrect. Please try again.":
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Astana(PlatformChecker):
    # URL = "https://airastana.com"
    EMAIL_ENDPOINT = "https://airastana.com/DesktopModules/AirAstana/NomadClubModule/NomadWS.asmx/CheckNomadEmail"

    # def prerequest(self):
    #     with self.get(Astana.URL) as r:
    #         return r.cookies

    def check_email(self, email):
        payload = {
            "pEmail": email,
            "pLanguage": "en-US"
        }
        # self.get_token()
        with self.post(Astana.EMAIL_ENDPOINT, json=payload) as r:
            json_body = r.json()
            if json_body["d"] is True:
                return self.response_available(email)
            elif json_body["d"] == "This e-mail is already taken.":
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Thatsthem(PlatformChecker):
    EMAIL_ENDPOINT = "https://thatsthem.com/email/{}"

    def check_email(self, email):
        with self.get(Thatsthem.EMAIL_ENDPOINT.format(email)) as r:
            resp_text = r.text
            soup = bs(resp_text, 'lxml')
            record_card = soup.find('div', class_='record')
            if record_card is None:
                return self.response_failure(email)
            elif record_card is not None:
                record = soup.find('div', class_='record')
                if record is None:
                    return self.response_available(email)
                elif record is not None:
                    return self.response_unavailable(email, data=soup)
            else:
                return self.response_failure(email)


class Flickr(PlatformChecker):
    EMAIL_ENDPOINT = 'https://identity-api.flickr.com/migration?email={}'

    def check_email(self, email):
        with self.get(Flickr.EMAIL_ENDPOINT.format(email)) as r:
            json_body = r.json()
            if json_body['stat'] == 'fail':
                return self.response_available(email)
            elif json_body['stat'] == 'ok':
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Quora(PlatformChecker):
    URL = "https://www.quora.com/"
    EMAIL_ENDPOINT = "https://www.quora.com/graphql/gql_POST?q=LoginForm_loginDo_Mutation"

    def prerequest(self):
        with self.get(Quora.URL) as r:
            text1 = r.text
            soup = bs(text1, 'lxml')
            script = soup.find('script', text=re.compile(
                "window.ansFrontendGlobals.earlySettings"))
            json_str = script.get_text().split(
                "window.ansFrontendGlobals.earlySettings = ")[-1].strip()[:-1]
            json_resp = json.loads(json_str)
            formkey = json_resp['formkey']
            return formkey, r.cookies

    def check_email(self, email):
        formkey, cookies = self.get_token()
        random_pass = "vfs3M0Bz8$04QSh5"
        payload = {
            "queryName": "LoginForm_loginDo_Mutation",
            "extensions": {
                "hash": "850beb3e5b26862cfccab95e62242ade129eba6974bfb9795ea57a8cd4ae72ce"
            },
            "variables": {
                "email": email,
                "password": random_pass
            }
        }
        headers = {
            'Quora-Formkey': formkey,
            'Content-Type': 'application/json',
        }
        with self.post(Quora.EMAIL_ENDPOINT,
                       json=payload,
                       headers=headers) as r:
            json_body = r.json()
            if json_body['data']['loginDo']['errorType'] == "email_not_found":
                return self.response_available(email)
            elif json_body['data']['loginDo']['errorType'] == "incorrect_password":
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Gravatar(PlatformChecker):
    EMAIL_ENDPOINT = "https://public-api.wordpress.com/rest/v1.1/signups/validation/user/?http_envelope=1"

    def check_email(self, email):
        payload = {
            "email": email,
            "password": "vfs3M0Bz8$04QSh5",
            "username": "vfs3m0bz804qsh5",
            "locale": "en"
        }
        with self.post(Gravatar.EMAIL_ENDPOINT, json=payload) as r:
            json_body = r.json()
            if json_body['body']['success'] is True:
                return self.response_available(email)
            elif json_body['body']['success'] is False:
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Secretflying(PlatformChecker):
    EMAIL_ENDPOINT = "https://www.secretflying.com/wp-admin/admin-ajax.php"

    def check_email(self, email):
        payload = "action=ihc_check_reg_field_ajax&type=user_email&value={}&second_value=".format(
            email)
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        }
        with self.post(Secretflying.EMAIL_ENDPOINT,
                       data=payload,
                       headers=headers) as r:
            resp_text = r.text
            if resp_text == '1':
                return self.response_available(email)
            elif resp_text == 'Email address is taken':
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Youporn(PlatformChecker):
    EMAIL_ENDPOINT = 'https://www.youporn.com/users/check-unique/?email={}'

    def check_email(self, email):
        with self.post(Youporn.EMAIL_ENDPOINT.format(email)) as r:
            json_body = r.json()
            if json_body['found'] is False:
                return self.response_available(email)
            elif json_body['found'] is True:
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Scottscheapflights(PlatformChecker):
    URL = "https://app.scottscheapflights.com/users/password/new"
    EMAIL_ENDPOINT = "https://app.scottscheapflights.com/signup.json"

    def prerequest(self):
        with self.get(Scottscheapflights.URL) as r:
            text = r.text
            soup = bs(text, 'lxml')
            token = soup.find('meta', attrs={'name': 'csrf-token'})['content']
            return token

    def check_email(self, email):
        token = self.get_token()
        payload = {
            "user": {
                "email": email,
                "first_name": "",
                "password": ""
            }
        }
        headers = {
            'X-CSRF-Token': token,
            'Content-Type': 'application/json',
        }
        with self.post(Scottscheapflights.EMAIL_ENDPOINT,
                       json=payload,
                       headers=headers) as r:
            json_body = r.json()
            if 'email' not in json_body['errors']:
                return self.response_available(email)
            elif "email" in json_body['errors'] \
                    and 'taken' in json_body['errors']['email'][0]:
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Hulu(PlatformChecker):
    EMAIL_ENDPOINT = "https://signup.hulu.com/api/v2/accounts/status?email={}"

    def check_email(self, email):
        with self.get(Hulu.EMAIL_ENDPOINT.format(email)) as r:
            json_body = r.json()
            if json_body['status'] == 'available':
                return self.response_available(email)
            elif json_body['status'] == 'existing':
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Ea(PlatformChecker):
    URL = "https://www.ea.com/register"
    EMAIL_ENDPOINT = "https://signin.ea.com/p/ajax/user/checkEmailExisted?requestorId=portal&email={}&fid={}"

    def prerequest(self):
        with self.get(Ea.URL) as r:
            text = r.text
            soup = bs(text, 'lxml')
            script = soup.find('script', text=re.compile("var options"))
            json_str = script.get_text().split(
                "var options = ")[-1].split('$.fn.registration(options);')[0].strip()[:-1].replace("'", '"')
            json_body = json.loads(json_str)
            token = json_body['fid']
            return token

    def check_email(self, email):
        token = self.get_token()
        with self.get(Ea.EMAIL_ENDPOINT.format(email, token)) as r:
            json_body = r.json()
            if json_body['message'] == 'register_email_not_existed':
                return self.response_available(email)
            elif json_body['message'] == 'register_email_existed':
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Espn(PlatformChecker):
    URL = "https://registerdisney.go.com/jgc/v6/client/ESPN-ONESITE.WEB-PROD/api-key?langPref=en-UK"
    EMAIL_ENDPOINT = "https://registerdisney.go.com/jgc/v6/client/ESPN-ONESITE.WEB-PROD/validate?langPref=en-US"

    def prerequest(self):
        with self.post(Espn.URL) as r:
            token = r.headers['api-key']
            return token

    def check_email(self, email):
        token = self.get_token()
        payload = {"email": email}
        headers = {
            'content-type': 'application/json',
            'authorization': 'APIKEY {}'.format(token)
        }
        with self.post(Espn.EMAIL_ENDPOINT,
                       json=payload,
                       headers=headers) as r:
            json_body = r.json()
            if json_body['error'] is None:
                return self.response_available(email)
            elif json_body['error']['errors'][0]['code'] == 'ACCOUNT_FOUND':
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Kayak(PlatformChecker):
    URL = "https://www.kayak.com/profile/notifications"
    EMAIL_ENDPOINT = "https://www.kayak.com/k/run/magiclink/startLogin"

    def prerequest(self):
        with self.get(Kayak.URL) as r:
            text = r.text
            soup = bs(text, 'lxml')
            json_str = soup.find(
                'script', text=re.compile("formtoken")).get_text()
            # json_str = script.get_text().split(
            #     "var globals = ")[-1].split('if (R9.globals)')[0].strip()[:-1]
            json_resp = json.loads(json_str)
            token = json_resp['serverData']['global']['formtoken']
            return token

    def check_email(self, email):
        token = self.get_token()
        payload = 'username={}&checkPasswordAuth=true'.format(email)
        headers = {
            'X-CSRF': token,
            'Content-Type': 'application/x-www-form-urlencoded',
            'x-requested-with': 'XMLHttpRequest'
        }
        with self.post(Kayak.EMAIL_ENDPOINT,
                       data=payload,
                       headers=headers) as r:
            json_body = r.json()
            if json_body['error'] is True and json_body['errorId'] == 'NO_SUCH_USER':
                return self.response_available(email)
            elif json_body['error'] is False:
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Expedia(PlatformChecker):
    URL = "https://www.expedia.com/user/auth?form=unified&uurl=e3id=redr&rurl=/?pwaLob=wizard-hotel-pwa-v2"
    EMAIL_ENDPOINT = "https://www.expedia.com/user/validate?email={}&csrfTokenL={}&sendVerifyEmail=true&uurl=e3id=redr&rurl=/?pwaLob=wizard-hotel-pwa-v2"

    def prerequest(self):
        headers = {
            'Accept-Language': 'en-US,en;q=0.5',
            'X-Requested-With': 'XMLHttpRequest',
        }
        with self.get(Expedia.URL, headers=headers) as r:
            text = r.text
            soup = bs(text, 'lxml')
            script = soup.find('script', text=re.compile("window.__STATE__"))
            json_str = script.get_text().split(
                "window.__STATE__ = JSON.parse(")[-1].split('window.__PLUGIN_STATE__')[0].strip()[:-2]
            json_resp = json.loads(json.loads(json_str))
            api_key = json_resp['context']['apiToken']
            token = json_resp['authPageData']['csrfTokenL']
            return token, api_key

    def check_email(self, email):
        token, api_key = self.get_token()
        headers = {
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Content-Type': 'application/json',
            'X-API-TOKEN': api_key,
            'X-Requested-With': 'XMLHttpRequest',
        }
        with self.get(Expedia.EMAIL_ENDPOINT.format(email, token),
                      headers=headers) as r:
            json_body = r.json()
            if json_body['validationStatus'] == 'NO':
                return self.response_available(email)
            elif json_body['errorCode'] == 'EmailInvalid':
                return self.response_invalid(email)
            elif json_body['validationStatus'] == 'FULL':
                return self.response_unavailable(email)
            elif json_body['validationStatus'] == 'UNDELIVERABLE':
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Ryanair(PlatformChecker):
    EMAIL_ENDPOINT = "https://api.ryanair.com/usrprof/rest/api/v1/login"

    def check_email(self, email):
        random_pass = '5Dye56dsd654OLsa'
        payload = 'username={}&password={}&policyAgreed=true'.format(
            email, random_pass)
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        with self.post(Ryanair.EMAIL_ENDPOINT,
                       data=payload,
                       headers=headers) as r:
            json_body = r.json()
            if json_body['code'] == 'Account.WrongPasswordOrAccNonexistent':
                return self.response_available(email)
            elif json_body['code'] == 'Account.Unverified':
                return self.response_unavailable(email)
            elif json_body['code'] == 'Password.Wrong':
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Justfly(PlatformChecker):
    EMAIL_ENDPOINT = 'https://www.justfly.com/account/modal-login-check-email'

    def check_email(self, email):
        payload = "email={}&include_header=1".format(email)
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        }
        with self.post(Justfly.EMAIL_ENDPOINT,
                       data=payload,
                       headers=headers) as r:
            json_body = r.json()
            # print(json_body)
            if json_body['result'] is True:
                if json_body['emailExists'] is False:
                    return self.response_available(email)
                elif json_body['emailExists'] is True:
                    return self.response_unavailable(email)
            elif json_body['result'] is False:
                return self.response_failure(email)
            else:
                return self.response_failure(email)


class Trivago(PlatformChecker):
    EMAIL_ENDPOINT = 'https://access.trivago.com/oauth/api/members/exists'

    def check_email(self, email):
        payload = 'email={}'.format(email)
        headers = {
            'authority': 'access.trivago.com',
            'accept': '*/*',
            'x-requested-with': 'XMLHttpRequest',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': 'https://access.trivago.com',
            'referer': 'https://access.trivago.com/oauth/en-US/login',
            'accept-language': 'en;q=0.9,zh-CN;q=0.8,zh;q=0.7'
        }
        with self.post(Trivago.EMAIL_ENDPOINT,
                       headers=headers,
                       data=payload) as r:
            json_body = r.json()
            if json_body['exists'] is False:
                return self.response_available(email)
            elif json_body['exists'] is True:
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class AshleyMadison(PlatformChecker):
    EMAIL_ENDPOINT = 'https://ashley.cynic.al/'

    def check_email(self, email):
        payload = f'email={email}'
        headers = {
            'Origin': 'https://ashley.cynic.al',
            'Referer': 'https://ashley.cynic.al/',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        with self.post(AshleyMadison.EMAIL_ENDPOINT,
                       headers=headers,
                       data=payload) as r:
            soup = bs(r.text, 'lxml')
            result = soup.find('p', id='result')
            if 'good' in result['class']:
                return self.response_available(email)
            elif 'bad' in result['class']:
                return self.response_unavailable(email)
            else:
                return self.response_failure(email)


class Apple(PlatformChecker):
    EMAIL_ENDPOINT = 'https://iforgot.apple.com/password/verify/appleid'

    def check_email(self, email):
        payload = "{\"id\":\"%s\"}" % email
        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Content-Type': 'application/json'
        }
        with self.post(Apple.EMAIL_ENDPOINT,
                       headers=headers,
                       data=payload) as r:
            if r.status_code == 200:
                return self.response_unavailable(email)
            elif r.status_code == 400:
                return self.response_available(email)
            else:
                return self.response_failure(email)


class Airasia(PlatformChecker):
    URL = "https://ssor.airasia.com/config/v2/clients/by-origin"
    EMAIL_ENDPOINT = "https://ssor.airasia.com/auth/v2/authorization/by-credentials?clientId={}"

    def prerequest(self):
        headers = {
            'Origin': 'https://www.airasia.com'
        }
        with self.get(Airasia.URL, headers=headers) as r:
            data = r.json()
            client_id = data['id']
            api_key = data['apiKey']
            return client_id, api_key

    def check_email(self, email):
        client_id, api_key = self.get_token()
        payload = "{\"username\":\"%s\",\"password\":\"Supe0000\"}" % email
        headers = {
            'x-api-key': api_key,
            'content-type': 'application/json'
        }
        with self.post(Airasia.EMAIL_ENDPOINT.format(client_id),
                       headers=headers,
                       data=payload) as r:
            json_body = r.json()
            if json_body['code'] == 'USER_TERMINATED':
                return self.response_unavailable(email)
            elif 'status' in json_body and json_body['status'] == 'active':
                return self.response_unavailable(email)
            elif 'status' not in json_body and json_body['code'] == 'INVALID_CREDENTIALS':
                return self.response_available(email)
            elif json_body['code'] == 'USER_NOT_ACTIVATED':
                return self.response_available(email)
            else:
                return self.response_failure(email)


class Travelzoo(PlatformChecker):
    EMAIL_ENDPOINT = "https://www.travelzoo.com/Marketing/ManageSubscriptions/?"

    def check_email(self, email):
        payload = "email=%s" % email
        headers = {
            'accept': '*/*',
            'x-requested-with': 'XMLHttpRequest',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'accept-language': 'en-US,en;q=0.9',
            'X-Requested-With': 'XMLHttpRequest',
        }
        with self.post(Travelzoo.EMAIL_ENDPOINT,
                       headers=headers,
                       data=payload) as r:
            if r.headers['Content-Type'] == "application/json":
                json_body = r.json()
                if json_body['ErrorCode'] == -2:
                    return self.response_available(email)
                elif json_body['ErrorCode'] != -2:
                    return self.response_unavailable(email)
                else:
                    return self.response_failure(email)
            elif "text/html" in r.headers['Content-Type']:
                return self.response_unavailable(email)


class Cnn(PlatformChecker):
    EMAIL_ENDPOINT = "https://audience.cnn.com/core/api/1/identity"

    def check_email(self, email):
        payload = {
            "identityRequests": [
                {
                    "identityType": "EMAIL",
                    "principal": email,
                    "credential": self.create_random_pass(length=12)
                }
            ]
        }
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Content-Type': 'application/json;charset=utf-8'
        }
        with self.post(Cnn.EMAIL_ENDPOINT,
                       headers=headers,
                       json=payload) as r:
            if r.status_code == 429:
                return self.response_unavailable(email)
            elif r:
                if "text/plain" in r.headers['Content-Type']:
                    return self.response_available(email)
            else:
                return self.response_failure(email)


class Fox(PlatformChecker):
    URL = "https://my.foxnews.com/js/app/config/config.json"
    EMAIL_ENDPOINT = "https://api3.fox.com/v2.0/register"

    def prerequest(self):
        headers = {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'X-Requested-With': 'XMLHttpRequest'
        }
        with self.get(Fox.URL, headers=headers) as r:
            data = r.json()
            api_key = data['API_KEY']
            return api_key

    def check_email(self, email):
        api_key = self.get_token()
        payload = {
            "email": email,
            "password": self.create_random_pass(length=15),
            "birthdate": "1993-11-17",
            "gender": "m",
            "firstName": ''.join(random.choice(string.ascii_letters) for i in range(10)),
            "lastName": ''.join(random.choice(string.ascii_letters) for i in range(10)),
            "displayName": ''.join(random.choice(string.ascii_letters) for i in range(20))
        }
        headers = {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Content-Type': 'application/json',
            'x-api-key': api_key
        }
        with self.post(Fox.EMAIL_ENDPOINT,
                       headers=headers,
                       json=payload) as r:
            json_body = r.json()
            if 'errorCode' in json_body:
                if json_body['errorCode'] == 409:
                    return self.response_unavailable(email)
                else:
                    return self.response_invalid(email)
            elif 'accessToken' in json_body:
                return self.response_available(email)
            else:
                return self.response_failure(email)


class Makemytrip(PlatformChecker):
    EMAIL_ENDPOINT = "https://mapi.makemytrip.com/ext/web/pwa/isUserRegistered?region=us&language=eng&currency=usd"

    def check_email(self, email):
        # print('inside')
        auth = "h4nhc9jcgpAGIjp"
        token = "aad357a4-c8c2-4a30-921d-f5044a7e10d0"
        payload = json.dumps({
            "loginId": email,
            "version": 2,
            "type": "EMAIL",
            "countryCode": "1"
        })
        headers = {
            'authority': 'mapi.makemytrip.com',
            'dnt': '1',
            'language': 'eng',
            'authorization': auth,
            'usr-mcid': token,
            'vid': token,
            'os': 'desktop',
            'tid': token,
            'deviceid': token,
            'currency': 'usd',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36',
            'visitor-id': token,
            'region': 'us',
            'accept': 'application/json',
            'content-type': 'application/json',
            # 'origin': 'https://www.makemytrip.com',
            'referer': 'https://www.makemytrip.com/',
            'accept-language': 'en-US,en;q=0.9,yo;q=0.8'
        }
        with self.post(Makemytrip.EMAIL_ENDPOINT,
                       headers=headers,
                       data=payload) as r:
            print(r.text)
            json_body = r.json()
            if not json_body['success']:
                return self.response_failure(email)
            elif json_body['data']['registered']:
                return self.response_unavailable(email)
            elif not json_body['data']['registered']:
                return self.response_available(email)
            else:
                return self.response_failure(email)


class Cleartrip(PlatformChecker):
    EMAIL_ENDPOINT = "https://www.cleartrip.com/v2/signin"

    def check_email(self, email):
        payload = json.dumps({
            "username": email,
            "password": ""
        })
        headers = {
            'authority': 'www.cleartrip.com',
            'sec-ch-ua': '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
            'dnt': '1',
            'service': '/',
            'sec-ch-ua-mobile': '?0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36',
            'content-type': 'application/json',
            'x-ct-sourcetype': 'web',
            'accept': 'application/json',
            # 'origin': 'https://www.cleartrip.com',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://www.cleartrip.com/',
            'accept-language': 'en-US,en;q=0.9,yo;q=0.8'
        }
        with self.post(Cleartrip.EMAIL_ENDPOINT,
                       headers=headers,
                       data=payload) as r:
            json_body = r.json()
            if json_body['status'] == 'UNAUTHORIZED':
                return self.response_unavailable(email)
            elif json_body['status'] == 'NOT_FOUND':
                return self.response_available(email)
            else:
                return self.response_failure(email)


class Platforms(Enum):
    # GITHUB = GitHub
    # GITLAB = GitLab
    # INSTAGRAM = Instagram
    # LASTFM = Lastfm
    # PINTEREST = Pinterest
    # REDDIT = Reddit
    # SNAPCHAT = Snapchat
    # SPOTIFY = Spotify
    # TWITTER = Twitter
    # TUMBLR = Tumblr
    # JETBLUE = Jetblue
    # FOURSQUARE = Foursquare
    # LATAM = Latam
    # FRONTIER = Frontier
    # SKYSCANNER = Skyscanner
    # VRBO = Vrbo
    # SPICEJET = Spicejet
    # MALAYSIA = Malaysia
    # ASTANA = Astana
    # THATSTHEM = Thatsthem
    # FLICKR = Flickr
    # QUORA = Quora
    # GRAVATAR = Gravatar
    # SECRETFLYING = Secretflying
    # YOUPORN = Youporn
    # HULU = Hulu
    # EA = Ea
    # KAYAK = Kayak
    # BOOKING = Booking
    # RYANAIR = Ryanair
    # ESPN = Espn
    # EXPEDIA = Expedia
    # JUSTFLY = Justfly
    # TRIVAGO = Trivago
    # ASHLEYMADISON = AshleyMadison
    # APPLE = Apple
    # AIRASIA = Airasia
    # TRAVELZOO = Travelzoo
    # CNN = Cnn
    # FOX = Fox

    # THATSTHEM = Thatsthem
    # KAYAK = Kayak
    # EXPEDIA = Expedia
    # SKYSCANNER = Skyscanner
    BOOKING = Booking
    # VRBO = Vrbo
    # RYANAIR = Ryanair
    # JETBLUE = Jetblue
    # MALAYSIA = Malaysia
    # JUSTFLY = Justfly
    # LATAM = Latam
    # SECRETFLYING = Secretflying
    # FOURSQUARE = Foursquare
    # TRAVELZOO = Travelzoo
    # FRONTIER = Frontier
    # SPICEJET = Spicejet
    # ASTANA = Astana
    TRIVAGO = Trivago
    # AIRASIA = Airasia
    # SCOTTSCHEAPFLIGHTS = Scottscheapflights
    # MAKEMYTRIP = Makemytrip
    # CLEARTRIP = Cleartrip

    def __str__(self):
        return self.value.__name__

    def __len__(self):
        return len(self.value.__name__)


@dataclass(frozen=True)
class PlatformResponse:
    platform: Platforms
    query: str
    available: bool
    valid: bool
    success: bool
    message: str
    link: str
    data: object
