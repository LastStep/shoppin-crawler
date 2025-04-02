import json
from time import sleep

import pandas as pd
from src.base import BasePlatformCrawler, Product, CrawlerRegistry


@CrawlerRegistry.register("virgio")
class VirgioCrawler(BasePlatformCrawler):
    """
    Crawler for Virgio platform.
    """
    domain = "westside.com"
    platform_name = "Virgio"
    base_url = "https://www.virgio.com/"
    api_url = "https://www.virgio.com/collections/all"
    
    def __init__(self):
        super().__init__()

        self.params = {
            "_data": "routes/collections.$collectionHandle.(products).($productHandle)",
        }
        
    def run(self):
        page_number = 1

        while True:
            self.log("info", f"Fetching page {page_number}...")  

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
            product_data = json_body["collection"]["products"]
            if 'nodes' in product_data and product_data["nodes"]:
                self.parse_data(product_data["nodes"])
                page_info = product_data["pageInfo"]
                if not page_info["hasNextPage"]:
                    self.log("info", f"No more pages to fetch.")  
                    return False
                else:
                    self.params["cursor"] = page_info["endCursor"]
                    self.params["direction"] = "next"
                return True
            else:  
                self.log("info", "No product data found.")  
                return False
            
    def check_error(self, response):
        return super().check_error(response)
    
    def parse_data(self, products: list):
        parsed_products = []
    
        for product in products:
            product_id = product.get("id", "")
            product_id = product_id.split("/")[-1] if product_id else ""

            product_url = product.get("handle", "")
            product_url = f"{self.base_url}products/{product_url}" if product_url else ""

            product = Product(
                product_id=product_id,
                product_name=product.get("title", ""),
                product_url=product_url,
            )
            parsed_products.append(product.model_dump())
        
        df = pd.DataFrame(parsed_products)
        self.DATAFRAME = pd.concat([self.DATAFRAME, df], ignore_index=True)
