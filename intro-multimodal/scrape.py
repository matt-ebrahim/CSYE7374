#!/usr/bin/env python3

import json
import os
import requests
import logging
import argparse
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from time import sleep
from pathlib import Path

from bs4 import BeautifulSoup
import pdfplumber  # Add to requirements.txt

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)  # Fixed typo in getlogger -> getLogger

class PaperScraper:
    """
    Class for searching and retrieving scientific literature from PubMed.
    Features:
      - Metadata retrieval and PDF downloading (when available)
      - Rate limiting for API calls
    """
    def __init__(self, output_dir: str = "scrape_output", rate_limit: float = 0.1):
        self.output_dir = output_dir
        self.rate_limit = rate_limit # Time between requests in seconds
        self.unpaywall_email = os.getenv("UNPAYWALL_EMAIL")
        self.core_api_key = os.getenv("CORE_API_KEY")
        os.makedirs(output_dir, exist_ok=True)
        
    def create_query_folder(self, database: str, query: str) -> tuple[Path, Path]:
        """
        Create folder structure for a specific query under the given database.
        Returns paths for metadata and PDF storage.
        """
        query_folder = query.replace(" ","_").replace("/","_")[:20]
        metadata_path = Path(self.output_dir) / database / "metadata" / query_folder
        pdf_path = Path(self.output_dir) / database / "pdf" / query_folder
        
        metadata_path.mkdir(parents=True, exist_ok=True)
        pdf_path.mkdir(parents=True, exist_ok=True)
        return metadata_path, pdf_path
    
    def search_pubmed(self, query: str, max_results: int = 100,
                      date_range: Optional[Tuple[str, str]] = None,
                      sort: str = "relevance") -> List[str]:
        """
        Search PubMed for the given query and return a list of PubMed IDs.
        """
        logger.info(f"Searching PubMed for : {query}")
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        
        # Append date filter if provided
        if date_range:
            start, end = date_range
            query = f"{query} AND {start}[PDAT] : {end}[PDAT]"
            
        # Use official NCBI E-utilities API
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": min(max_results * 2, 100000), # Respect PubMed's max limit
            "retmode": "json",
            "sort": "relevance" if sort == "relevance" else "pub+date",
            # "api_key": os.getenv("NCBI_API_KEY", ""), 
        }
        
        try:
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if "error" in data:
                raise RuntimeError(f"PubMed API error: {data['error']}")
                
            id_list = data.get("esearchresult", {}).get("idlist", [])
            if not id_list:
                logger.warning("No results found for query")
            else:
                logger.info(f"Found {len(id_list)} results")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch results from PubMed: {e}")
            raise
        return id_list
    
    def fetch_pubmed_details(self, id_list: List[str]) -> List[Dict]:
        """
        Retrieve detailed metadata for a list of PubMed IDs.
        """
        logger.info(f"Fetching details for {len(id_list)} papers...")
        details = []
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        
        for pmid in id_list:
            sleep(max(self.rate_limit, 0.5))  # Ensure at least 0.5 seconds between requests
            params = {
                "db": "pubmed",
                "id": pmid,
                "retmode": "xml",
                "rettype": "full"
            }
            try:
                response = requests.get(base_url, params=params)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "xml")
                article_element = soup.find("PubmedArticle")
                
                if not article_element:
                    logger.warning(f"No article data found for PMID {pmid}")
                    continue
                    
                full_text_link = self._get_full_text_link(article_element)
                
                article = {
                    "pubmed_id": pmid,
                    "doi": self._get_doi(article_element),
                    "title": self._get_title(article_element),
                    "abstract": self._get_abstract(article_element),
                    "authors": self._get_authors(article_element),
                    "journal": self._get_journal_info(article_element),
                    "publication_date": self._get_pub_date(article_element),
                    "full_text_link": full_text_link
                }
                details.append(article)
                logger.info(f"Successfully processed PMID {pmid}")
            except Exception as e:
                logger.error(f"Error processing PMID {pmid}: {e}")
                continue
        
        logger.info(f"Successfully fetched details for {len(details)} papers")
        return details
    
    def download_pdf(self, pdf_url: str, filename: str) -> str:
        """
        Download a PDF from a given URL and save it to the specified filename.
        Handles HTML pages and extracts PDF links from them.
        """
        logger.info(f"Downloading PDF from {pdf_url}")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/pdf,text/html,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        
        session = requests.Session()
        
        try:
            # First, try to get the page
            response = session.get(pdf_url, headers=headers, allow_redirects=True, timeout=30)
            response.raise_for_status()
            
            content_type = response.headers.get('Content-Type', '').lower()
            
            # If we got HTML, try to extract PDF link from it
            if 'html' in content_type:
                logger.info(f"Received HTML page, extracting PDF link from {response.url}")
                pdf_link = self._extract_pdf_from_html(response.text, response.url)
                if pdf_link:
                    logger.info(f"Found PDF link: {pdf_link}")
                    # Download the actual PDF
                    return self._download_actual_pdf(pdf_link, filename, session, headers)
                else:
                    raise ValueError("Could not find PDF link in HTML page")
            
            # If we got a PDF directly
            elif 'pdf' in content_type or response.url.endswith('.pdf'):
                return self._save_pdf_response(response, filename)
            
            else:
                raise ValueError(f"Unexpected content type: {content_type}")
                
        except Exception as e:
            logger.error(f"Failed to download PDF: {e}")
            raise

    def _extract_pdf_from_html(self, html: str, base_url: str) -> Optional[str]:
        """
        Extract PDF link from PMC HTML page.
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # Look for PDF download links in PMC pages
        pdf_selectors = [
            'a[href*=".pdf"]',
            'a[href*="/pdf/"]',
            'a[href*="download"]',
            'a[href*="fulltext"]',
            'a[href*="article"]',
            '.pdf-link',
            '.download-pdf',
            '#pdf-download',
            '[data-pdf-url]'
        ]
        
        for selector in pdf_selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href', '')
                if href:
                    # Make URL absolute
                    if href.startswith('/'):
                        href = 'https://www.ncbi.nlm.nih.gov' + href
                    elif not href.startswith('http'):
                        href = requests.compat.urljoin(base_url, href)
                    
                    # Check if it looks like a PDF URL
                    if any(keyword in href.lower() for keyword in ['.pdf', 'pdf', 'download', 'fulltext']):
                        logger.debug(f"Found potential PDF link: {href}")
                        return href
        
        # Look for any link containing "pdf" in the text or href
        for link in soup.find_all('a'):
            href = link.get('href', '')
            text = link.get_text().lower()
            if 'pdf' in href.lower() or 'pdf' in text:
                if href.startswith('/'):
                    href = 'https://www.ncbi.nlm.nih.gov' + href
                elif not href.startswith('http'):
                    href = requests.compat.urljoin(base_url, href)
                logger.debug(f"Found PDF link via text search: {href}")
                return href
        
        logger.debug("No PDF link found in HTML")
        return None

    def _download_actual_pdf(self, pdf_url: str, filename: str, session: requests.Session, headers: dict) -> str:
        """
        Download the actual PDF file with streaming, inspect non-PDF responses, and dump for debugging.
        """
        try:
            with session.get(pdf_url, headers=headers, timeout=60, stream=True, allow_redirects=True) as response:
                response.raise_for_status()
                final_url = response.url
                content_type = response.headers.get("Content-Type", "").lower()

                # Read the first chunk to inspect
                buffer = bytearray()
                for chunk in response.iter_content(1024 * 64):
                    if chunk:
                        buffer.extend(chunk)
                        # Stop early if buffer is large enough to inspect
                        if len(buffer) >= 1024:
                            break

                # If it looks like HTML (common when blocked or redirected), save and error
                prefix = bytes(buffer[:15])
                if prefix.startswith(b'<!') or b'<html' in buffer.lower() or 'html' in content_type:
                    debug_path = f"{filename}.debug.html"
                    # Save full body for manual inspection (re-fetch small amount to avoid truncation)
                    with open(debug_path, "wb") as f:
                        f.write(buffer)
                        # try to append more if available
                        remaining = response.raw.read(1024 * 256, decode_content=True) or b""
                        f.write(remaining)
                    raise ValueError(f"Expected PDF but got HTML or non-PDF content. Saved debug to {debug_path}. Final URL: {final_url}, Content-Type: {content_type}")

                # If still not starting with %PDF- after reading initial bytes, fail with dump
                if not buffer.startswith(b'%PDF-'):
                    # Save the initial bytes to help debug
                    debug_path = f"{filename}.debug.bin"
                    with open(debug_path, "wb") as f:
                        f.write(buffer)
                    raise ValueError(f"Content is not a valid PDF (initial bytes={buffer[:10]}...). Dumped to {debug_path}.")

                # Otherwise, stream full content to disk (including what we've already read)
                with open(filename, "wb") as f:
                    f.write(buffer)
                    # write rest
                    for chunk in response.iter_content(1024 * 64):
                        if chunk:
                            f.write(chunk)

            logger.info(f"PDF saved to {filename}")
            return filename

        except Exception as e:
            logger.error(f"Failed to download actual PDF: {e}")
            raise

    def _save_pdf_response(self, response: requests.Response, filename: str) -> str:
        """
        Save a PDF response to file.
        """
        if not response.content.startswith(b'%PDF-'):
            raise ValueError("Content is not a valid PDF")
        
        with open(filename, "wb") as f:
            f.write(response.content)
        logger.info(f"PDF saved to {filename}")
        return filename
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        Extract text from a PDF file using pdfplumber.
        """
        logger.info(f"Extracting text from {pdf_path}")
        text = ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text = "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())
        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {e}")
            return ""
        logger.info(f"Successfully extracted text from {pdf_path}")
        return text
    
    def _get_full_text_link(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Try to obtain a full text PDF link.
        """
        pmid = soup.find("Id").text if soup.find("Id") else "Unknown"
        logger.debug(f"Attempting to get full text link for PMID {pmid}")

        # Check for PMC ID in multiple locations
        pmc_id = None
        for id_tag in soup.find_all(["ArticleId", "OtherID"]):
            if id_tag.get("IdType") == "pmc" or id_tag.get("Source") == "PMC":
                pmc_id = id_tag.text.strip().replace("PMC", "")
                logger.debug(f"Found PMC ID: {pmc_id}")
                break

        if pmc_id:
            # Return the article URL instead of direct PDF URL
            # The download_pdf method will handle extracting the PDF from the HTML
            article_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/"
            logger.debug(f"Generated PMC article URL: {article_url}")
            return article_url

        # Try DOI resolution
        doi = self._get_doi(soup)
        if doi:
            logger.debug(f"Found DOI: {doi}")
            pdf_url = self._resolve_doi_to_pdf(doi)
            if pdf_url:
                logger.debug(f"Resolved DOI to PDF: {pdf_url}")
                return pdf_url

        logger.debug("No full text link found through any method")
        return None

    def _resolve_doi_to_pdf(self, doi: str) -> Optional[str]:
        """
        Resolve a DOI to a direct PDF link via multiple services
        """
        if not doi:
            return None
        
        logger.debug(f"Attempting to resolve DOI: {doi}")
        
        # Check if DOI is from a known publisher
        publisher_patterns = {
            "10.1016": "Elsevier",
            "10.1038": "Nature",
            "10.1093": "Oxford",
            "10.1007": "Springer",
            "10.1111": "Wiley",
            "10.1371": "PLOS",
        }
        
        for pattern, publisher in publisher_patterns.items():
            if pattern in doi:
                logger.debug(f"Identified publisher: {publisher}")
                break
            
        # Try direct publisher PDF links first
        if "10.1016" in doi:  # Elsevier
            pdf_url = f"https://www.sciencedirect.com/science/article/pii/{doi.split('/')[-1]}/pdfft"
            logger.debug(f"Trying Elsevier direct PDF: {pdf_url}")
            try:
                response = requests.head(pdf_url, allow_redirects=True, timeout=10)
                if response.ok and "pdf" in response.headers.get("Content-Type", "").lower():
                    return pdf_url
            except Exception as e:
                logger.debug(f"Elsevier PDF attempt failed: {e}")

        # Try Unpaywall
        if self.unpaywall_email:
            logger.debug("Trying Unpaywall API")
            unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email={self.unpaywall_email}"
            try:
                response = requests.get(unpaywall_url, timeout=10)
                if response.ok:
                    data = response.json()
                    logger.debug(f"Unpaywall response: {data.get('best_oa_location')}")
                    best_location = data.get("best_oa_location", {})
                    if best_location:
                        pdf_url = best_location.get("pdf_url") or best_location.get("url")
                        if pdf_url and (pdf_url.endswith(".pdf") or "pdf" in pdf_url.lower()):
                            return pdf_url
            except Exception as e:
                logger.debug(f"Unpaywall API error: {e}")

        # Try DOI resolution
        try:
            logger.debug("Trying DOI resolution")
            headers = {"Accept": "text/html,application/pdf"}
            response = requests.get(f"https://doi.org/{doi}", headers=headers, allow_redirects=True)
            if response.ok:
                final_url = response.url
                logger.debug(f"DOI resolves to: {final_url}")
                if final_url.endswith(".pdf"):
                    return final_url
        except Exception as e:
            logger.debug(f"DOI resolution failed: {e}")

        return None



    # --- Helper methods for parsing PubMed XML ---
    def _get_doi(self, soup: BeautifulSoup) -> Optional[str]:
        """Get DOI from article."""
        article_ids = soup.find("ArticleIdList") or soup.find("PubmedData")
        if article_ids:
            doi_tag = article_ids.find("ArticleId", {"IdType": "doi"})
            if doi_tag:
                return doi_tag.text.strip()
        return None

    def _get_title(self, soup: BeautifulSoup) -> str:
        """Get article title."""
        title_tag = soup.find("ArticleTitle")
        return title_tag.text.strip() if title_tag else ""

    def _get_abstract(self, soup: BeautifulSoup) -> str:
        """Get article abstract."""
        abstract = soup.find("Abstract")
        if not abstract:
            return ""
        
        sections = abstract.find_all("AbstractText")
        if not sections:
            return ""
        
        # Handle structured abstracts
        if any(section.get("Label") for section in sections):
            return "\n".join(
                f"{section.get('Label', 'Abstract')}: {section.text.strip()}"
                for section in sections
            )
        
        # Handle simple abstracts
        return " ".join(section.text.strip() for section in sections)

    def _get_authors(self, soup: BeautifulSoup) -> List[Dict]:
        """Get article authors."""
        author_list = soup.find("AuthorList")
        if not author_list:
            return []
        
        authors = []
        for author in author_list.find_all("Author"):
            if author.find("CollectiveName"):
                authors.append({
                    "collective_name": author.find("CollectiveName").text.strip(),
                    "lastname": "",
                    "firstname": "",
                    "affiliation": ""
                })
            else:
                lastname = author.find("LastName")
                firstname = author.find("ForeName")
                affiliation = author.find("Affiliation")
                
                authors.append({
                    "lastname": lastname.text.strip() if lastname else "",
                    "firstname": firstname.text.strip() if firstname else "",
                    "affiliation": affiliation.text.strip() if affiliation else ""
                })
        
        return authors

    def _get_journal_info(self, soup: BeautifulSoup) -> Dict:
        """Get journal information."""
        journal = soup.find("Journal")
        if not journal:
            return {}
        
        return {
            "name": (journal.find("Title").text.strip() if journal.find("Title") 
                    else journal.find("ISOAbbreviation").text.strip() if journal.find("ISOAbbreviation")
                    else ""),
            "issn": journal.find("ISSN").text.strip() if journal.find("ISSN") else "",
            "volume": journal.find("Volume").text.strip() if journal.find("Volume") else "",
            "issue": journal.find("Issue").text.strip() if journal.find("Issue") else "",
        }

    def _get_pub_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Get publication date."""
        pub_date = (
            soup.find("PubDate") or 
            soup.find("DateCompleted") or 
            soup.find("DateRevised")
        )
        
        if not pub_date:
            return None
        
        if pub_date.find("MedlineDate"):
            return pub_date.find("MedlineDate").text.strip()
        
        year = pub_date.find("Year")
        month = pub_date.find("Month")
        day = pub_date.find("Day")
        
        if year:
            date_parts = [year.text.strip()]
            if month:
                date_parts.append(month.text.strip().zfill(2))
                if day:
                    date_parts.append(day.text.strip().zfill(2))
            return "-".join(date_parts)
        
        return None

def main():
    parser = argparse.ArgumentParser(description="PubMed Literature Search Tool")
    parser.add_argument('--query', '-q', required=True, help='Search query')
    parser.add_argument('--max-results', '-n', type=int, default=100,
                        help='Maximum number of results with valid PDFs (default: 100)')
    parser.add_argument('--output-dir', '-o', default='scrape_output',
                        help='Output directory (default: scrape_output)')
    parser.add_argument('--rate-limit', '-r', type=float, default=0.5,
                        help='Rate limit between requests in seconds (default: 0.1)')
    parser.add_argument('--date-range', '-dr', nargs=2, metavar=('START', 'END'),
                        help='Date range in YYYY/MM/DD format (PubMed only)')
    parser.add_argument('--sort', '-s', choices=['relevance', 'date'], default='relevance',
                        help='Sort order (default: relevance)')
    parser.add_argument('--download-pdfs', '-p', action='store_true',
                        help='Download PDFs when available')
    args = parser.parse_args()
    
    # Initialize scraper and create folders
    scraper = PaperScraper(output_dir=args.output_dir, rate_limit=args.rate_limit)
    metadata_path, pdf_path = scraper.create_query_folder('pubmed', args.query)
    
    valid_papers = []
    total_attempts = 0
    max_attempts = args.max_results * 5 
    
    while len(valid_papers) < args.max_results and total_attempts < max_attempts:
        batch_size = min(100, args.max_results * 2)
        pmids = scraper.search_pubmed(args.query, batch_size, args.date_range, args.sort)
        results = scraper.fetch_pubmed_details(pmids)
        
        for paper in results:
            if len(valid_papers) >= args.max_results:
                break
                    
            if pdf_url := paper.get('full_text_link'):
                try:
                    title = paper.get('title', '')
                    safe_title = ''.join(c.lower() for c in title if c.isalnum() or c.isspace())
                    safe_title = safe_title.replace(' ', '_')[:100]  # Truncate to reasonable length
                    
                    # Fall back to PMID if title processing results in empty string
                    filename = f"{safe_title or paper['pubmed_id']}.pdf"
                    pdf_file = pdf_path / filename
                    
                    scraper.download_pdf(pdf_url, str(pdf_file))
                    valid_papers.append(paper)
                    logger.info(f"Successfully downloaded PDF {len(valid_papers)}/{args.max_results}")
                except Exception as e:
                    logger.warning(f"Failed to download PDF for PMID {paper['pubmed_id']}: {e}")
            total_attempts += 1
            
     # Save metadata of the successfully processed papers
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    metadata_file = metadata_path / f"metadata_{timestamp}.json"
    with open(metadata_file, "w") as f:
        json.dump(valid_papers, f, indent=2)
    logger.info(f"Saved metadata to {metadata_file}")

if __name__ == '__main__':
    main()