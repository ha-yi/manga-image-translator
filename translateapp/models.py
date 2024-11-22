from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

@dataclass
class Chapter:
    title: str
    url: str
    number: float
    download_url: str = ""
    date: Optional[datetime] = None

@dataclass
class Manga:
    title: str
    cover_image: str
    rating: float
    url: str
    chapters: List[Chapter]
    genres: List[str] = None
    description: Optional[str] = None 