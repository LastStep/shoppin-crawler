import json
from time import sleep

import pandas as pd
from src.base import BasePlatformCrawler, Product, CrawlerRegistry


@CrawlerRegistry.register("nykaafashion")
class NykaaFashionCrawler(BasePlatformCrawler):
    """
    Crawler for NykaaFashion platform.
    """
    domain = "nykaafashion.com"
    platform_name = "NykaaFashion"
    base_url = "https://www.nykaafashion.com"
    api_url = "https://www.nykaafashion.com/rest/appapi/V2/categories/products"
    
    def __init__(self):
        super().__init__()

        self.DEFAULT_COOKIES = {
            "_abck": "97DE1BB7DAEE8550739D43E0D84E19D8~0~YAAQrwFAF/3LK/OVAQAAgTZa9Q1agrDz1N5LJ3KjksWloncliAa2RcpFfmCi04RAUeJxy8lZc9jkpBh+PcwXpqiymhHKMgSs1VCWLKCX0dOzfzj0D8I+seBNYvmMfrnldy8svwEgTP+iF3/4WcSZRIJaJMqFgmUYucHyPSwdtcFU1WnQmzjf0V6+82NYwqKvdAeJ2G4gJ/8X1uEcHL1oNHWRD4fHEfBUl1w6zXN7MfU+67irf9zRI3eFXg+8JnwdzJk9MFroNI/nNJE8hSrY4Do7/Nen0IkcCLC9ErAKcGRm6WjhAiIVOv+m/d4skKp2172LCOphPbO2M8IejM2vAKsRZiR628bP+2mCISwR3YIjydgCwJV1MiFiVj1RWZIMRLloBLxOdW8tWxbwVeEkN2tWLjbTvzc5+p0YO8K1CenpKQlUiVHkyUOow1S+IoEKju9Fn78rA1aInPRhIZcuVlReHJ3jslRoprRFBN1JY+XHqP4hGyngzKClVLbWWfjFLpDg4vIpOP6I+rx6Xfnf6cvVAGqwJaadTI0fyRIAcQs5WBHI4bK/XNi3OfaWdu2noVu+sBJD7aLgwITDqIgK6/rYJXKeyaO748Oz7nhZ2z8KXgKkY+vpomE/v9lv6pl7Hl2QiheJazUx68wR~-1~-1~1743581645",
            "bm_sz": "762F5D7AF1847B291638208A5B4A45AF~YAAQrwFAF/rLK/OVAQAAvjVa9RtDW1vwPqXquLrMEBX3t6s+0FreD2InRK90v/e3fx51LYp2N7qdXJe+Pc/L/AGYgoKIFuxt0b9wPQqljI8cle4QSCUbF/fZNLgrOWjrbhKByq3RlKK6EJiqQMu4Es7GYKBSNADUAZsXi0D+vhEO30MjyKUFgMjY8hH9SCSa6dv3aY+HJ8nDqGlYBp+x+IAhN8bucOpPw1zdqeI7wuKlgQqUSE4cwbhFE10UIXJ1MPFXeu7Lhe6IRSXj8fldXQzasQH/Ua+zWGlh/cUeRAQEaTgbVrTDRQQ2UZzBV0RjPOr+u97RJGJkHAwItAVqNgY7WlEc+519+CxF+FbURzBThyjX/F3zs3NVtQueEq/F/H0QN0xtUV+VzRk5bnGaSQX9HBNCRmfGWhpesbzNRJe4rbKGE7ezadkpdQa2kvSKervDsNCXHihYENls/sYnMw1byuzWt2o/3mM4xZDZIe40iovohwSDXu3Ev+qDME4=~3159874~3749699"
        }
        self.params = {
            "PageSize": 50,
            "filter_format": "v2",
            "apiVersion": 5,
            "currency": "INR",
            "counter_code": "IN",
            "deviceType": "WEBSITE",
            "sort": "popularity",
            "device_os": "desktop",
            "sort_algo": "default",
        }

        self.collection_ids = [
            2, 3, 4, 5, 6, 7, 8, 9, 10
        ]

    def run(self):

        for collection_id in self.collection_ids:
            page_number = 1

            while page_number < self.MAX_PAGES:
                self.log("info", f"Fetching Category: {collection_id} Page: {page_number}...")  

                self.params["categoryId"] = collection_id
                self.params["currentPage"] = page_number

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
            product_data = json_body["response"]
            if 'products' in product_data and product_data["products"]:
                self.parse_data(product_data["products"])
                return True
            else:
                self.log("warning", "No product data found")  
                return False
            
    def check_error(self, response):
        json_body = self.get_json(response)
        if "status" in json_body and json_body["status"] == "success":
            return False
        return True
    
    def parse_data(self, products: list):
        parsed_products = []
    
        for product in products:
            product_title = product.get("title", "")
            product_subtitle = product.get("subTitle", "")
            product_name = f"{product_title} {product_subtitle}".strip()

            product_url = product.get("actionUrl", "")
            product_url = f"{self.base_url}{product_url}" if product_url else ""

            product = Product(
                product_id=str(product.get("id", "")),
                product_name=product_name,
                product_url=product_url,
            )
            parsed_products.append(product.model_dump())
        
        df = pd.DataFrame(parsed_products)
        self.DATAFRAME = pd.concat([self.DATAFRAME, df], ignore_index=True)
