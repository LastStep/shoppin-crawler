# Import all crawler modules here to ensure registration
from .westside import WestsideCrawler
from .virgio import VirgioCrawler
from .tatacliq import TataCliqCrawler
from .nykaafashion import NykaaFashionCrawler
from .inmyprime import InMyPrimeCrawler

# Export available crawlers
__all__ = [
    'WestsideCrawler', 
    'VirgioCrawler', 
    'TataCliqCrawler',
    'NykaaFashionCrawler',
    'InMyPrimeCrawler'
]
