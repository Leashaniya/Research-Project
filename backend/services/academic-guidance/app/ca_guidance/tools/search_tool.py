# tools/search_tool.py

import logging
from typing import List

import requests
from crewai.tools import tool
from ddgs import DDGS

logger = logging.getLogger(__name__)

@tool
def duckduckgo_search(query: str, max_results: int = 5, max_youtube_results: int = 3) -> str:
    """
    Performs a web search using DuckDuckGo and returns:
    - Valid article links
    - Valid YouTube video links

    Args:
        query: The search query.
        max_results: Maximum number of valid article results to return. Defaults to 5.
        max_youtube_results: Maximum number of YouTube video results to return. Defaults to 3.

    Returns:
        A formatted markdown string containing articles and YouTube video links.
    """
    try:
        article_results: List[str] = []
        youtube_results: List[str] = []

        # Use a slightly higher limit internally so we can filter out bad links
        internal_article_limit = max_results * 3
        internal_video_limit = max_youtube_results * 3

        with DDGS() as ddgs:
            # -------- 1) ARTICLE SEARCH (TEXT) --------
            raw_results = ddgs.text(query, max_results=internal_article_limit)

            for result in raw_results:
                if len(article_results) >= max_results:
                    break

                title = result.get("title", "No title")
                body = result.get("body", "No description")
                url = result.get("href", "")

                # Basic sanity check on URL
                if not isinstance(url, str) or not url.startswith("http"):
                    continue

                # Skip youtube here; we'll handle videos separately
                if "youtube.com" in url or "youtu.be" in url:
                    continue

                try:
                    # Validate the URL with a HEAD request
                    resp = requests.head(url, allow_redirects=True, timeout=5)
                    status = resp.status_code

                    if status >= 400:
                        logger.info(f"Skipping URL with bad status {status}: {url}")
                        continue
                except requests.RequestException as e:
                    logger.info(f"Skipping URL due to request error: {url} ({e})")
                    continue

                # Format as markdown hyperlink
                formatted = f"- [{title}]({url})"
                article_results.append(formatted)

            # -------- 2) YOUTUBE VIDEO SEARCH --------
            # You can tweak the query here if you want more "tutorial" style videos
            video_query = f"{query} tutorial dbms"

            try:
                raw_videos = ddgs.videos(video_query, max_results=internal_video_limit)
            except Exception as e:
                logger.info(f"Error while searching videos: {e}")
                raw_videos = []

            for v in raw_videos:
                if len(youtube_results) >= max_youtube_results:
                    break

                title = v.get("title", "No title")
                url = v.get("content", "") or v.get("url", "")

                if not isinstance(url, str) or not url.startswith("http"):
                    continue

                # Keep only YouTube links
                if "youtube.com" not in url and "youtu.be" not in url:
                    continue

                try:
                    resp = requests.head(url, allow_redirects=True, timeout=5)
                    status = resp.status_code

                    if status >= 400:
                        logger.info(f"Skipping YouTube URL with bad status {status}: {url}")
                        continue
                except requests.RequestException as e:
                    logger.info(f"Skipping YouTube URL due to request error: {url} ({e})")
                    continue

                formatted = f"- [{title}]({url})"
                youtube_results.append(formatted)

        # -------- 3) BUILD FINAL OUTPUT --------
        sections: List[str] = []

        if article_results:
            sections.append("#### Articles\n" + "\n".join(article_results))

        if youtube_results:
            sections.append("#### YouTube Videos\n" + "\n".join(youtube_results))

        if not sections:
            return (
                f"No valid (non-404) results found for query: {query}. "
                f"Try refining your search keywords."
            )

        # This string is ready to be dropped inside **Related Web Resources**
        return "\n\n".join(sections)

    except Exception as e:
        logger.exception("Error during DuckDuckGo search")
        return f"An error occurred while searching: {e}"
