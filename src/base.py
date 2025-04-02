from abc import ABC, abstractmethod
from datetime import datetime
import os
import random
import requests
import pandas as pd
from pydantic import BaseModel, Field
from time import sleep
from src.utils.logger_config import logger
from fake_useragent import UserAgent

class Product(BaseModel):
    """
    Pydantic model for product data
    """
    product_id: str = Field(..., description="Unique identifier for the product")
    product_name: str = Field(..., description="Name of the product")
    product_url: str = Field(..., description="URL of the product page")

class CrawlerRegistry:
    _crawlers = {}

    @classmethod
    def register(cls, name):
        def decorator(crawler_class):
            cls._crawlers[name.upper()] = crawler_class
            return crawler_class
        return decorator

    @classmethod
    def get_crawler(cls, name):
        return cls._crawlers.get(name.upper())

    @classmethod
    def available_crawlers(cls):
        return list(cls._crawlers.keys())


class QueryError(Exception):
    pass


class BasePlatformCrawler(ABC):
    """
    Abstract Base class for platforms
    """
    # Required attributes
    domain = None
    platform_name = None

    # Defaults
    DEFAULT_HEADERS = {
        # 'Accept': '/',
        # 'Accept-Encoding': 'gzip, deflate, br, zstd',
        # 'Accept-Language': 'en-US,en;q=0.9',
        # 'Connection': 'keep-alive',
        # 'Dnt': '1',  # Do Not Track
        'content-type': 'application/json',
    }

    DEFAULT_COOKIES = {}
    UNEXPECTED_CONTENT_TYPE_ERROR_MESSAGE = "Unexpected content type {}.."

    DATAFRAME = pd.DataFrame()
    DELAY = 2  # Delay between requests in seconds
    OUTPUT_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
    MAX_RETRIES = 3  # Maximum number of retries for a request
    RETRY_DELAY = 2  # Delay between retries in seconds
    REQUEST_TIMEOUT = 15  # Timeout for requests in seconds
    MAX_PAGES = float("inf") # Unlimited crawl
    USER_AGENT_ROTATION = False

    def __init__(self, proxy_list: list = None):
        if not self.domain:
            raise ValueError("Domain must be provided.")
        
        if not self.platform_name:
            raise ValueError("Platform name must be provided.")
        
        self.proxy_list = proxy_list or []
        self.session = requests.Session()
        self.request_count = 0
        self.ua = UserAgent(browsers=['Edge', 'Chrome', 'Firefox', 'Safari'], os=['Windows', 'Linux', 'Mac OS X'])
        self.DEFAULT_HEADERS['User-Agent'] = self.ua.getRandom["useragent"]
        self.data_saved = False

        logger.info(f"Initializing {self.platform_name} crawler")
    
    def safe_run(self):
        """
        Wrapper around run() that ensures output_data() is called even if an exception occurs
        """
        try:
            self.run()
        except Exception as e:
            logger.error(f"Error during crawler execution: {str(e)}")
            raise
        finally:
            self.output_data()

    def update_user_agent(self):
        """
        Get headers for the request, with optional user agent rotation
        """
        self.DEFAULT_HEADERS['User-Agent'] = self.ua.getRandom["useragent"]

    @abstractmethod
    def run(self):
        """
        Run the crawler.
        """
        pass

    # @abstractmethod
    # def pre_request(self):
    #     pass

    @abstractmethod
    def crawl(self) -> bool:
        """
        Crawl the given URL and return the response.
        """
        pass

    @abstractmethod
    def parse_data(self):
        """
        Parse data from the resposne.
        """
        pass

    @abstractmethod
    def check_error(self, response) -> bool:
        """
        Check for errors in the response.
        """
        return False

    def output_data(self):
        """
        Output the data to a CSV file.
        """
        if self.DATAFRAME.empty or self.data_saved:
            logger.warning("No data to output.")
            return
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file_path = os.path.join(self.OUTPUT_FOLDER, f"{self.platform_name}_products_{timestamp}.csv")
        
        self.DATAFRAME.drop_duplicates(inplace=True)
        self.DATAFRAME.to_csv(output_file_path, index=False)
        
        logger.info(f"Data saved to {self.platform_name}_products_{timestamp}.csv")
        self.data_saved = True

    def get_cookies(self, url):
        """
        Get cookies from a website by making a request
        """
        headers = self.get_request_headers()
        response = self.session.get(url, headers=headers)
        
        if response.status_code == 200:
            logger.info(f"Successfully retrieved cookies from {url}")
            return response.cookies
        else:
            logger.warning(f"Failed to get cookies from {url}: Status code {response.status_code}")
            return {}

    def _request(self, method, url, **kwargs):
        retry_count = 0
        while retry_count < self.MAX_RETRIES:
            try:
                self.request_count += 1

                # Randomize delay to appear more human-like
                jittered_delay = self.DELAY * (0.5 + random.random())

                if "headers" in kwargs:
                    self.DEFAULT_HEADERS.update(kwargs["headers"])
                kwargs["headers"] = self.DEFAULT_HEADERS
                
                kwargs["cookies"] = self.DEFAULT_COOKIES

                # Make the request
                response = self.session.request(method, url, timeout=self.REQUEST_TIMEOUT, **kwargs)

                # Check for errors
                if self.check_error(response):
                    logger.warning(f"Request failed (attempt {retry_count + 1}/{self.MAX_RETRIES})")
                    retry_count += 1
                    if self.USER_AGENT_ROTATION:
                        self.update_user_agent()
                    sleep(self.DELAY * (retry_count + 1))  # Exponential backoff
                    continue
                
                sleep(jittered_delay)
                return response
                
            except (requests.exceptions.RequestException, QueryError) as e:
                logger.error(f"Error during request: {str(e)}")
                retry_count += 1
                if retry_count == self.MAX_RETRIES:
                    raise
                sleep(self.DELAY * (retry_count + 1))
                
        raise QueryError(f"Failed after {self.MAX_RETRIES} attempts")

    def post(self, url, **kwargs):
        return self._request("POST", url, **kwargs)

    def get(self, url, **kwargs):
        return self._request("GET", url, **kwargs)

    @staticmethod
    def get_json(request):
        if not request.headers["Content-Type"].startswith("application/json"):
            raise QueryError(
                BasePlatformCrawler.UNEXPECTED_CONTENT_TYPE_ERROR_MESSAGE.format(
                    request.headers["Content-Type"]
                )
            )
        else:
            return request.json()
        
    def log(self, log_level: str, message: str):
        """
        Log a message with the specified level.
        
        Args:
            log_level: The logging level (info, error, warning, debug, critical)
            message: The message to log
        """
        log_func = getattr(logger, log_level.lower(), logger.info)
        log_func(f"[{self.platform_name}] {message}")


