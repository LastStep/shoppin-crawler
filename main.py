#!/usr/bin/env python
import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.base import CrawlerRegistry
# Import all crawlers to ensure registration
from src.platforms import *
from src.utils.logger_config import logger


def run_crawler(crawler_name):
    try:
        crawler_class = CrawlerRegistry.get_crawler(crawler_name)
        if crawler_class is None:
            raise KeyError(crawler_name)
        
        crawler = crawler_class()
        logger.info(f"Starting crawler: {crawler_name}")
        crawler.safe_run()
        logger.info(f"Completed crawler: {crawler_name}")
        return crawler_name, True
    except Exception as e:
        logger.error(f"Error in crawler {crawler_name}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return crawler_name, False


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='E-commerce Product URL Crawler')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--crawler', '-c', help='Specify the crawler to use (e.g., virgio, westside)')
    group.add_argument('--all', '-a', action='store_true', help='Run all available crawlers')
    parser.add_argument('--workers', '-w', type=int, default=3, help='Number of parallel workers when running all crawlers')
    
    args = parser.parse_args()

    if args.all:
        # Run all available crawlers in parallel
        available_crawlers = CrawlerRegistry.available_crawlers()
        logger.info(f"Running all available crawlers: {available_crawlers}")
        
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_crawler = {
                executor.submit(run_crawler, crawler): crawler 
                for crawler in available_crawlers
            }
            
            for future in as_completed(future_to_crawler):
                crawler = future_to_crawler[future]
                try:
                    name, success = future.result()
                    if success:
                        logger.info(f"Successfully completed crawler: {name}")
                    else:
                        logger.error(f"Failed to complete crawler: {name}")
                except Exception as e:
                    logger.error(f"Crawler {crawler} generated an exception: {e}")
    else:
        # Run single crawler
        try:
            crawler_name, success = run_crawler(args.crawler)
            if not success:
                return
        except KeyError:
            logger.error(f"Invalid crawler name: {args.crawler}")
            logger.info(f"Available crawlers: {CrawlerRegistry.available_crawlers()}")
            return


if __name__ == "__main__":
    main()