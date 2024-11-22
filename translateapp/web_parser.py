import requests
from bs4 import BeautifulSoup
from .models import Manga, Chapter
import re
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RawKumaParser:
    BASE_URL = "https://rawkuma.com"
    
    @staticmethod
    def get_manga_url(search_query=None):
        """Get the appropriate URL based on search query"""
        if not search_query or search_query.lower() == "search manga...":
            return f"{RawKumaParser.BASE_URL}/manga/?status=&type=manga&order="
        else:
            # Convert spaces to + and encode the query
            query = search_query.replace(' ', '+')
            return f"{RawKumaParser.BASE_URL}/?s={query}"
    
    @staticmethod
    def parse_manga_list(url):
        logger.info(f"Fetching manga list from: {url}")
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        mangas = []
        
        logger.info("Starting to parse manga items")
        manga_items = soup.select('div.bs div.bsx')
        logger.info(f"Found {len(manga_items)} potential manga items")
        
        for item in manga_items:
            try:
                main_link = item.select_one('a')
                if not main_link:
                    continue
                
                title_div = item.select_one('.tt')
                title = title_div.text.strip() if title_div else main_link.get('title', '').strip()
                url = main_link.get('href', '')
                logger.info(f"Processing manga: {title}")
                
                cover = item.select_one('img')
                cover_url = cover.get('src', '') if cover else ''
                if not cover_url:
                    logger.warning(f"No cover image found for manga: {title}")
                
                rating_div = item.select_one('.numscore')
                try:
                    rating = float(rating_div.text.strip()) if rating_div else 0
                except (ValueError, AttributeError):
                    rating = 0
                logger.info(f"Manga: {title} - Rating: {rating}")
                
                chapter_div = item.select_one('.epxs')
                latest_chapter = chapter_div.text.strip() if chapter_div else ''
                logger.info(f"Manga: {title} - Latest Chapter: {latest_chapter}")
                
                type_span = item.select_one('.type')
                manga_type = type_span.text.strip() if type_span else ''
                logger.info(f"Manga: {title} - Type: {manga_type}")
                
                manga = Manga(
                    title=title,
                    cover_image=cover_url,
                    rating=rating,
                    url=url,
                    chapters=[],
                    genres=[manga_type] if manga_type else []
                )
                mangas.append(manga)
                logger.info(f"Successfully added manga: {title}")
                
            except Exception as e:
                logger.error(f"Error parsing manga item: {str(e)}", exc_info=True)
        
        # Find next page link
        next_page_url = None
        next_link = soup.select_one('a.r:contains("Next")')
        if next_link:
            next_href = next_link.get('href', '')
            if next_href:
                # Convert relative URL to absolute URL if necessary
                if next_href.startswith('?'):
                    next_page_url = f"{RawKumaParser.BASE_URL}/manga/{next_href}"
                else:
                    next_page_url = next_href
                logger.info(f"Found next page URL: {next_page_url}")
        
        logger.info(f"Successfully parsed {len(mangas)} manga items")
        return mangas, next_page_url
    
    @staticmethod
    def parse_manga_details(manga: Manga):
        logger.info(f"Fetching manga details from: {manga.url}")
        response = requests.get(manga.url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get manga details first
        description = ""
        try:
            synopsis = soup.select_one('.entry-content .synp')
            if synopsis:
                description = synopsis.text.strip()
                logger.info("Found manga description")
        except Exception as e:
            logger.error(f"Error parsing description: {e}")
        
        # Get genres
        genres = []
        try:
            genre_links = soup.select('.genxed a')
            genres = [a.text.strip() for a in genre_links]
            logger.info(f"Found genres: {genres}")
        except Exception as e:
            logger.error(f"Error parsing genres: {e}")
        
        chapters = []
        # Updated selector to match the actual HTML structure
        chapter_items = soup.select('#chapterlist ul li')  # Changed selector
        logger.info(f"Found {len(chapter_items)} potential chapters")
        
        for chapter in chapter_items:
            try:
                # Get chapter link and title from eph-num
                eph_num = chapter.select_one('.eph-num a')
                if not eph_num:
                    continue
                
                chapter_url = eph_num.get('href', '')
                
                # Get chapter number
                chapter_num_span = eph_num.select_one('.chapternum')
                title = chapter_num_span.text.strip() if chapter_num_span else eph_num.text.strip()
                
                # Extract chapter number from title
                number_match = re.search(r'Chapter (\d+(?:\.\d+)?)', title)
                if not number_match:
                    # Try alternative format: just the number
                    number_match = re.search(r'(\d+(?:\.\d+)?)', title)
                number = float(number_match.group(1)) if number_match else 0.0
                
                # Get chapter date
                date_span = eph_num.select_one('.chapterdate')
                date_str = date_span.text.strip() if date_span else ''
                try:
                    date = datetime.strptime(date_str, '%B %d, %Y') if date_str else None
                except ValueError:
                    try:
                        # Try alternative date format
                        date = datetime.strptime(date_str, '%Y-%m-%d') if date_str else None
                    except ValueError:
                        logger.warning(f"Could not parse date: {date_str}")
                        date = None
                
                # Get download URL from dload class
                download_url = ""
                dload_link = chapter.select_one('a.dload')
                if dload_link:
                    download_url = dload_link.get('href', '')
                    logger.info(f"Found download URL for chapter {number}: {download_url}")
                
                logger.info(f"Processing chapter: {title} ({chapter_url})")
                
                # Get manga ID from URL
                manga_id = manga.url.rstrip('/').split('/')[-1]
                
                chapter_obj = Chapter(
                    title=title,
                    url=chapter_url,
                    number=number,
                    date=date,
                    download_url=download_url,
                    # Add manga information
                    manga_title=manga.title,
                    manga_id=manga_id,
                    manga_cover=manga.cover_image
                )
                chapters.append(chapter_obj)
                logger.info(f"Successfully parsed chapter: {title}")
                
            except Exception as e:
                logger.error(f"Error parsing chapter: {str(e)}", exc_info=True)
        
        # Sort chapters by number
        chapters.sort(key=lambda x: x.number)
        
        logger.info(f"Successfully parsed {len(chapters)} chapters")
        return {
            'chapters': chapters,
            'description': description,
            'genres': genres
        }