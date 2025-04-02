import json
from time import sleep
from bs4 import BeautifulSoup as bs

import pandas as pd
from src.base import BasePlatformCrawler, Product, CrawlerRegistry


@CrawlerRegistry.register("inmyprime")
class InMyPrimeCrawler(BasePlatformCrawler):
    """
    Crawler for inmyprime platform.
    """
    domain = "inmyprime.com"
    platform_name = "InMyPrime"
    base_url = "https://www.inmyprime.in/"
    page_url = "https://www.inmyprime.in/collections/all-products"
    
    def __init__(self):
        super().__init__()

    def run(self):
        page_number = 1

        while True:
            self.log("info", f"Fetching page {page_number}...")  

            self.api_url = f"{self.page_url}?page={page_number}" 

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
        ) as r:
            soup = bs(r.text, 'html.parser')
            product_items = soup.select('li.grid__item')
            
            if not product_items:
                self.log("warning", "No product items found")
                return False
                
            products = []
            for item in product_items:
                card_info = item.select_one('div.card__information')
                if card_info:
                    product_link = card_info.select_one('a')
                    if product_link:
                        product_url = product_link.get('href', '').lstrip('/')
                        product_url = f"{self.base_url}{product_url}"
                        product = Product(
                            product_id="",
                            product_name=product_link.get_text(strip=True),
                            product_url=product_url,
                        )
                        products.append(product)
            
            if products:
                self.parse_data(products)
                return True
            else:
                self.log("warning", "No product data found")
                return False
            
    def check_error(self, response):
        pass
    
    def parse_data(self, products: list):
        parsed_products = [product.model_dump() for product in products]
        
        df = pd.DataFrame(parsed_products)
        self.DATAFRAME = pd.concat([self.DATAFRAME, df], ignore_index=True)
