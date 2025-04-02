import json
from time import sleep

import pandas as pd
from src.base import BasePlatformCrawler, Product, CrawlerRegistry


@CrawlerRegistry.register("westside")
class WestsideCrawler(BasePlatformCrawler):
    """
    Crawler for Westside platform.
    """
    domain = "westside.com"
    platform_name = "Westside"
    base_url = "https://www.westside.com"
    api_url = "https://westside-api.wizsearch.in/v1/products/filter"
    
    def __init__(self):
        super().__init__()

        self.DEFAULT_HEADERS["x-api-key"] = "cXVuelRXaTlGQzFQUmJ3VEU5ZllVSzh4YldTQWxBTTQ2K2l4OXhrZmxoSXhzcGFZTjA1YnZJRkNPekVpcE5ERTBHOUhTSEE1TDc2dFIyNkwveFNramc9PQ=="
        self.DEFAULT_HEADERS["x-store-id"] = "fa5abe64dc3011eca5fb0a0c8095feae"

        self.params = {}

    def run(self):
        # Collections
        # 154202341429
        # 154205126709
        product_count = 50
        page_number = 1

        while page_number < self.MAX_PAGES:
            self.log("info", f"Fetching page {page_number}...")  

            filters = {
                "attributes": {},
                "categories": [ "154205126709"],
                "sort": [],
                "page": page_number,
                "type": "DEFAULT",
                "getAllVariants": "false",
                "swatch": [],
                "currency": "INR",
                "productsCount": product_count, 
                "showOOSProductsInOrder": "true",
                "inStock": [
                    "true"
                ],
                "attributeFacetValuesLimit": 20,
                "searchedKey": "NzhHalJra25ucnVzZThqMmlwemRMUStUR1FIUElzWjl1ODhmaFBkWk9WRT0="
            }
        
            self.params = {
                "filters": json.dumps(filters),
            }

            result = self.crawl()
            if not result:
                break
            else:
                page_number += 1
                sleep(self.DELAY)

        self.output_data()

    def crawl(self) -> bool:
        
        with self.post(
            self.api_url,
            params=self.params,
        ) as r:
            json_body = self.get_json(r)
            product_data = json_body["payload"]
            if 'result' in product_data and product_data["result"]:
                self.parse_data(product_data["result"])
                return True
            else:
                self.log("warning", "No product data found")  
                return False
            
    def check_error(self, response):
        return super().check_error(response)
    
    def parse_data(self, products: list):
        parsed_products = []
    
        for product in products:
            product = Product(
                product_id=str(product.get("id", "")),
                product_name=product.get("name", ""),
                product_url=product.get("url", ""),
            )
            parsed_products.append(product.model_dump())
        
        df = pd.DataFrame(parsed_products)
        self.DATAFRAME = pd.concat([self.DATAFRAME, df], ignore_index=True)
