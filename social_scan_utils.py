import asyncio
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

from social_scan_platforms import PlatformResponse, Platforms, QueryError

EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&’*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,253}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,253}[a-zA-Z0-9])?)+$"
)


def init_prerequest(platform, checkers):
    if hasattr(platform.value, "prerequest"):
        checkers[platform].get_token()


def init_checkers(session, platforms=list(Platforms), proxy_list=[]):
    checkers = {}
    for platform in platforms:
        checkers[platform] = platform.value(session, proxy_list=proxy_list)
    return checkers


def query(query_, platform, checkers):
    try:
        is_email = EMAIL_REGEX.match(query_)
        if is_email and hasattr(platform.value, "check_email"):
            response = checkers[platform].check_email(query_)
            if response is None:
                raise QueryError("Error retrieving result")
            return response
    except (KeyError, QueryError, Exception):
        return PlatformResponse(
            platform=platform,
            query=query_,
            available=False,
            valid=False,
            success=False,
            # message=f"{type(e).__name__} - {e}",
            message='',
            link=None,
            data=None
        )


async def execute_queries(queries, platforms=list(Platforms), proxy_list=[]):
    with ThreadPoolExecutor(max_workers=80) as executor:
        with requests.Session() as session:
            loop = asyncio.get_event_loop()
            checkers = init_checkers(
                session, platforms=platforms, proxy_list=proxy_list)
            query_tasks = [
                loop.run_in_executor(
                    executor,
                    query,
                    *(queries, p, checkers)
                )
                for p in platforms
            ]
            results = await asyncio.gather(*query_tasks,
                                           return_exceptions=True)
            return [x for x in results if x is not None]


def sync_execute_queries(queries, platforms=list(Platforms), proxy_list=[]):
    loop = asyncio.get_event_loop()
    future = asyncio.ensure_future(
        execute_queries(queries, platforms, proxy_list))
    return loop.run_until_complete(future)
