import json
from time import sleep

import pandas as pd
from src.base import BasePlatformCrawler, Product, CrawlerRegistry
from src.utils.logger_config import logger


@CrawlerRegistry.register("tatacliq")
class TataCliqCrawler(BasePlatformCrawler):
    """
    Crawler for TataCliq platform.
    """
    domain = "tatacliq.com"
    platform_name = "Tata Cliq"
    base_url = "https://www.tatacliq.com/"
    api_url = "https://searchbff.tatacliq.com/products/mpl/search"
    
    def __init__(self):
        super().__init__()

        self.params = {
            "searchText": ":relevance:category:MSH1116100:inStockFlag:true",
            "isKeywordRedirect": "true",
            "isKeywordRedirectEnabled": "true",
            "channel": "WEB",
            "isMDE": "true",
            "isTextSearch": "false",
            "isFilter": "false",
            "qc": "false",
            "isSuggested": "false",
            "isPwa": "true",
            "pageSize": 200,
            "typeID": "all",
        }

        self.total_pages = 100
        
    def run(self):
        page_number = 0

        while page_number <= self.total_pages:
            self.log("info", f"Fetching page {page_number + 1}...")  

            self.params["page"] = page_number

            result = self.crawl()
            if not result:
                break
            else:
                page_number += 1
                sleep(self.DELAY)

        self.output_data()

    def crawl(self) -> bool:
        with self.get(
            self.api_url,
            params=self.params,
        ) as r:
            json_body = self.get_json(r)
            product_data = json_body
            if 'searchresult' in product_data and product_data["searchresult"]:
                self.parse_data(product_data["searchresult"])
                page_info = product_data["pagination"]
                self.total_pages = page_info["totalPages"]
                return True
            else:  
                self.log("warning", "No product data found")  
                return False
            
    def check_error(self, response):
        json_body = self.get_json(response)
        if 'error' in json_body and json_body["error"]:
            self.log("error", json_body['error'])  
            return True
        return False
    
    def parse_data(self, products: list):
        parsed_products = []
    
        for product in products:
            product_id = product.get("productId", "")

            product_url = product.get("webURL", "").lstrip("/")
            product_url = f"{self.base_url}{product_url}" if product_url else ""

            product = Product(
                product_id=product_id,
                product_name=product.get("productname", ""),
                product_url=product_url,
            )
            parsed_products.append(product.model_dump())
        
        df = pd.DataFrame(parsed_products)
        self.DATAFRAME = pd.concat([self.DATAFRAME, df], ignore_index=True)
