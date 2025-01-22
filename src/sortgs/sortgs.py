#!/usr/bin/env python3

# -*- coding: utf-8 -*-
"""
This code creates a database with a list of publications data from Google 
Scholar.
The data acquired from GS is Title, Citations, Links and Rank.
It is useful for finding relevant papers by sorting by the number of citations
This example will look for the top 100 papers related to the keyword, 
so that you can rank them by the number of citations

As output this program will plot the number of citations in the Y axis and the 
rank of the result in the X axis. It also, optionally, export the database to
a .csv file.


"""
from urllib.parse import urljoin
import requests
import bs4
import requests, os, datetime, argparse
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import pandas as pd
import aiohttp
import asyncio
from aiofiles import open as aio_open
from time import sleep
import warnings
import random
import os
import re

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Solve conflict between raw_input and input on Python 2 and Python 3
import sys
if sys.version[0]=="3": raw_input=input

# Default Parameters
KEYWORD = 'machine learning' # Default argument if command line is empty
NRESULTS = 40# Fetch 100 articles
CSVPATH = os.getcwd() # Current folder as default path
SAVECSV = True
SORTBY = 'Citations'
PLOT_RESULTS = True
STARTYEAR = None
now = datetime.datetime.now()
ENDYEAR = now.year # Current year
DEBUG=False # debug mode
MAX_CSV_FNAME = 255
LANG = 'All'
MAX_RETRIES = 4
RETRY_DELAY = 2 




# Websession Parameters
GSCHOLAR_URL = 'https://scholar.google.com/scholar?start={}&q={}&hl=en&as_sdt=0,5'
YEAR_RANGE = '' #&as_ylo={start_year}&as_yhi={end_year}'
#GSCHOLAR_URL_YEAR = GSCHOLAR_URL+YEAR_RANGE
STARTYEAR_URL = '&as_ylo={}'
ENDYEAR_URL = '&as_yhi={}'
LANG_URL = '&lr={}'

ROBOT_KW=['unusual traffic from your computer network', 'not a robot']

def get_command_line_args():
    # Command line arguments
    parser = argparse.ArgumentParser(description='Arguments')
    parser.add_argument('kw', type=str, help="""Keyword to be searched. Use double quote followed by simple quote to search for an exact keyword. Example: "'exact keyword'" """, default=KEYWORD)
    parser.add_argument('--sortby', type=str, help='Column to be sorted by. Default is by the columns "Citations", i.e., it will be sorted by the number of citations. If you want to sort by citations per year, use --sortby "cit/year"')
    parser.add_argument('--langfilter', nargs='+', type=str, help='Only languages listed are permitted to pass the filter. List of supported language codes: zh-CN, zh-TW, nl, en, fr, de, it, ja, ko, pl, pt, es, tr')

    parser.add_argument('--nresults', type=int, help='Number of articles to search on Google Scholar. Default is 100. (carefull with robot checking if value is too high)')
    parser.add_argument('--csvpath', type=str, help='Path to save the exported csv file. By default it is the current folder')
    parser.add_argument('--notsavecsv', action='store_true', help='By default results are going to be exported to a csv file. Select this option to just print results but not store them')
    parser.add_argument('--plotresults', action='store_true', help='Use this flag in order to plot the results with the original rank in the x-axis and the number of citaions in the y-axis. Default is False')
    parser.add_argument('--startyear', type=int, help='Start year when searching. Default is None')
    parser.add_argument('--endyear', type=int, help='End year when searching. Default is current year')
    parser.add_argument('--debug', action='store_true', help='Debug mode. Used for unit testing. It will get pages stored on web archive')

    # Parse and read arguments and assign them to variables if exists
    args, _ = parser.parse_known_args()

    # Check if no arguments were provided and print help if so
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    keyword = KEYWORD
    if args.kw:
        keyword = args.kw

    nresults = NRESULTS
    if args.nresults:
        nresults = args.nresults

    csvpath = CSVPATH
    if args.csvpath:
        csvpath = args.csvpath

    save_csv = SAVECSV
    if args.notsavecsv:
        save_csv = False

    sortby = SORTBY
    if args.sortby:
        sortby=args.sortby

    langfilter = LANG
    if args.langfilter:
        langfilter = args.langfilter

    plot_results = False
    if args.plotresults:
        plot_results = True

    start_year = STARTYEAR
    if args.startyear:
        start_year=args.startyear

    end_year = ENDYEAR
    if args.endyear:
        end_year=args.endyear

    debug = DEBUG
    if args.debug:
        debug = True

    return keyword, nresults, save_csv, csvpath, sortby, langfilter, plot_results, start_year, end_year, debug


def get_citations(content):
    out = 0
    for char in range(0,len(content)):
        if content[char:char+9] == 'Cited by ':
            init = char+9
            for end in range(init+1,init+6):
                if content[end] == '<':
                    break
            out = content[init:end]
    return int(out)

def get_year(content):
    for char in range(0,len(content)):
        if content[char] == '-':
            out = content[char-5:char-1]
    if not out.isdigit():
        out = 0
    return int(out)

def setup_driver():
    print('Loading...')
    chrome_options = Options()
    chrome_options.add_argument("disable-infobars")
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def get_author(content):
    content = content.replace('\xa0', ' ')  # Replaces the non-breaking space with a regular space
    out = ""
    if len(content)>0:
        out = content.split(" - ")[0]
    return out

def get_element(driver, xpath, attempts=5, _count=0):
    '''Safe get_element method with multiple attempts'''
    try:
        element = driver.find_element_by_xpath(xpath)
        return element
    except Exception as e:
        if _count<attempts:
            sleep(random.uniform(0.5, 3))
            get_element(driver, xpath, attempts=attempts, _count=_count+1)
        else:
            print("Element not found")

def get_content_with_selenium(url):
    if 'driver' not in globals():
        global driver
        driver = setup_driver()
    driver.get(url)

    while True:
        # Wait for a specific element that indicates the page has loaded
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Get the body element
        el = driver.find_element(By.TAG_NAME, "body")

        c = el.get_attribute('innerHTML')
        if any(kw in el.text for kw in ROBOT_KW):
            raw_input("Solve captcha manually and press enter here to continue...")
        else:
            break

    return c.encode('utf-8')

def get_download_link(div):
    """Finds and returns the download link for a paper if available."""
    try:
        download_div = div.find("div", {"class": "gs_ggs gs_fl"})
        if not download_div:
            return None

        link = download_div.find("a").get("href")
        if link and "pdf" in link.lower():
            return link

        # Handle external HTML links
        if "HTML" in download_div.text:
            print(f"Processing external HTML link: {link}")
            pdf_link = handle_external_link(link)
            if pdf_link:
                print(f"Found PDF link in external HTML: {pdf_link}")
                return pdf_link
            else:
                print("Pdf link not found at", link, "search manually")

    except Exception as e:
        print(f"Error extracting download link: {e}")

    return None


     
 
    

async def download_pdf_async(session, url, path):
    """Downloads the PDF asynchronously from a URL to the specified path, with retries."""
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(url, timeout=10) as response:
                if response.headers.get("content-type") == "application/pdf" or url.endswith(".pdf"):
                    async with aio_open(path, "wb") as file:
                        async for chunk in response.content.iter_chunked(1024):
                            if chunk:
                                await file.write(chunk)
                    print(f"Downloaded PDF: {path}")
                    return True
                else:
                    # Attempt to detect PDFs from content if Content-Type is misleading
                    first_chunk = await response.content.read(1024)
                    if b"%PDF" in first_chunk:  # PDF files usually start with %PDF
                        async with aio_open(path, "wb") as file:
                            await file.write(first_chunk)
                            async for chunk in response.content.iter_chunked(1024):
                                await file.write(chunk)
                        print(f"Downloaded PDF (detected from content): {path}")
                        return True
                    else:
                        print(f"Skipping non-PDF content: {url}")
                        return False
        except aiohttp.ClientError as e:
            print(f"Network error during attempt {attempt + 1} for {url}: {e}")
        except asyncio.TimeoutError:
            print(f"Timeout during attempt {attempt + 1} for {url}.")
        except Exception as e:
            print(f"Unexpected error during attempt {attempt + 1} for {url}: {e}")

        if attempt < MAX_RETRIES - 1:
            print(f"Retrying in {RETRY_DELAY} seconds...")
            await asyncio.sleep(RETRY_DELAY)

    print(f"Failed to download PDF from {url} after {MAX_RETRIES} attempts.")
    return False


# Function to handle all PDF downloads asynchronously
async def download_pdfs(papers):
    """Handles downloading PDFs for all papers asynchronously."""
    async with aiohttp.ClientSession() as session:
        tasks = []
        for paper in papers:
            if paper['download_link']:
                pdf_save_path = os.path.join(paper['pdf_save_dir'], f"{paper['paper_id']}.pdf")
                tasks.append(download_pdf_async(session, paper['download_link'], pdf_save_path))
            else:
                print(f"No download link available for {paper['title']}.")

        # Run all tasks concurrently
        results = await asyncio.gather(*tasks)
        return results




def handle_external_link(link):
    """
    Handle an external link to find the PDF link within the page.
    """
    outer_page = requests.get(link).content
    soup = BeautifulSoup(outer_page, "html.parser")
    a_tags = soup.findAll("a")

    for a_tag in a_tags:
        href = a_tag.get("href")

        resolved_link = urljoin(link, href)  # Resolve relative link

        if "pdf" in resolved_link.lower():
            return resolved_link

    return None



def format_strings(strings):
    if len(strings) == 1:
        return f'lang_{strings[0]}'
    else:
        return '%7C'.join(f'lang_{s}' for s in strings)


def main():
    # Get command line arguments
    keyword, number_of_results, save_database, path, sortby_column, langfilter, plot_results, start_year, end_year, debug = get_command_line_args()

    # print("Running with the following parameters:")
    print(
        f"Keyword: {keyword}, Number of results: {number_of_results}, Save database: {save_database}, Path: {path}, Sort by: {sortby_column}, Permitted Languages: {langfilter}, Plot results: {plot_results}, Start year: {start_year}, End year: {end_year}, Debug: {debug}")

    # Create main URL based on command line arguments
    if start_year:
        GSCHOLAR_MAIN_URL = GSCHOLAR_URL + STARTYEAR_URL.format(start_year)
    else:
        GSCHOLAR_MAIN_URL = GSCHOLAR_URL

    if end_year != now.year:
        GSCHOLAR_MAIN_URL = GSCHOLAR_MAIN_URL + ENDYEAR_URL.format(end_year)

    if langfilter != 'All':
        formatted_filters = format_strings(langfilter)
        GSCHOLAR_MAIN_URL = GSCHOLAR_MAIN_URL + LANG_URL.format(formatted_filters)

    if debug:
        GSCHOLAR_MAIN_URL = 'https://web.archive.org/web/20210314203256/' + GSCHOLAR_URL

    # Start new session
    session = requests.Session()

    # Variables
    links, title, citations, year, author, venue, publisher, rank, download_links, download_status, paper_ids = ([] for _ in range(11))
    rank = [0]  # Start rank at 0
    pdf_save_dir = os.path.join(path, "PDFs")  # Directory for saving PDFs
    os.makedirs(pdf_save_dir, exist_ok=True)
    df = pd.DataFrame()
    # Check for temporary progress file
    temp_csv = os.path.join(path, "temp_results.csv")
    temp_cols = 0
    if os.path.exists(temp_csv):
        print(f"Found temporary file: {temp_csv}. Resuming from saved progress.")
        try:
            df = pd.read_csv(temp_csv)

            # Verify and fix the Rank column if missing or invalid
            if 'Rank' not in df.columns or df['Rank'].isnull().all():
                print("Rank column missing or invalid. Regenerating index...")
                df.index = range(1, len(df) + 1)
                df.index.name = 'Rank'
            else:
                df.set_index('Rank', inplace=True)
            temp_cols = len(df)
            print(f"Resuming from paper {len(df) + 1}.")
            rank_start = len(df)  # Start from the next unprocessed paper
        except Exception as e:
            print(f"Error reading temporary file: {e}. Starting from scratch.")
            rank_start = 0
            data = pd.DataFrame()
    else:
        # print("No temporary file found. Starting from scratch.")
        rank_start = 0
        data = pd.DataFrame()

    # Generate unique IDs
    def generate_unique_id(idx):
        return f"paper_{idx:04d}"

    # Function to download PDF


    # Get content from number_of_results URLs
    for n in range(rank_start, number_of_results, 10):
        url = GSCHOLAR_MAIN_URL.format(str(n), keyword.replace(' ', '+'))
        if debug:
            print("Opening URL:", url)

        # print(f"Loading next {n + 10} results")
        page = session.get(url)
        c = page.content
        if any(kw in c.decode('ISO-8859-1') for kw in ROBOT_KW):
            # print("Robot checking detected, handling with selenium (if installed)")
            try:
                c = get_content_with_selenium(url)
            except Exception as e:
                # print("No success. The following error was raised:")
                print(e)

        # Create parser
        soup = BeautifulSoup(c, 'html.parser', from_encoding='utf-8')

        # Get stuff
        mydivs = soup.findAll("div", {"class": "gs_or"})
        papers= []
        for div in mydivs:
            paper_id = generate_unique_id(len(rank)+temp_cols)
            paper_ids.append(paper_id)

            try:
                links.append(div.find('h3').find('a').get('href'))
            except:
                links.append(f'Look manually at: {url}')

            try:
                title.append(div.find('h3').find('a').text)
            except:
                title.append('Could not catch title')

            try:
                citations.append(get_citations(str(div.format_string)))
            except:
                warnings.warn(f"Number of citations not found for {title[-1]}. Appending 0")
                citations.append(0)

            try:
                year.append(get_year(div.find('div', {'class': 'gs_a'}).text))
            except:
                warnings.warn(f"Year not found for {title[-1]}, appending 0")
                year.append(0)

            try:
                author.append(get_author(div.find('div', {'class': 'gs_a'}).text))
            except:
                author.append("Author not found")

            try:
                publisher.append(div.find('div', {'class': 'gs_a'}).text.split("-")[-1])
            except:
                publisher.append("Publisher not found")

            try:
                venue.append(" ".join(div.find('div', {'class': 'gs_a'}).text.split("-")[-2].split(",")[:-1]))
            except:
                venue.append("Venue not found")

            # Extract and store download link
            download_link = get_download_link(div)
            download_links.append(download_link)


            if not download_link:
                download_status.append("No Link")
            rank.append(rank[-1] + 1)


        for idx, (paper_id, title, download_link) in enumerate(zip(paper_ids, title, download_links)):
            pdf_save_path = os.path.join(pdf_save_dir, f"{paper_id}.pdf")
            papers.append({
                "paper_id": paper_id,
                "title": title,
                "download_link": download_link,
                "pdf_save_dir": pdf_save_dir,
                "pdf_save_path": pdf_save_path,
            })
        print("Starting asynchronous PDF downloads...")
        results = asyncio.run(download_pdfs(papers))
        download_status+= results
        
            
        
        # Save progress to a temporary file
        temp_data = pd.DataFrame(list(zip(paper_ids, author, title, citations, year, publisher, venue, links, download_links, download_status)),
                                 columns=['ID', 'Author', 'Title', 'Citations', 'Year', 'Publisher', 'Venue', 'Source', 'Download Link', 'Download Status'])
        temp_data['Rank'] = range(1, len(temp_data) + 1)
        temp_data.to_csv(temp_csv, index=False)
        print("Progress saved to temp_results.csv")
        title = list(title)
        # Delay
        sleep(random.uniform(0.5, 3))

    # Create a dataset and sort by the number of citations
    data = pd.DataFrame(list(zip(paper_ids, author, title, citations, year, publisher, venue, links, download_links)),
                        index=rank[1:],
                        columns=['ID', 'Author', 'Title', 'Citations', 'Year', 'Publisher', 'Venue', 'Source', 'Download Link'])
    if not df.empty:
        frames = [df, data]
        data = pd.concat(frames)
    data.index.name = 'Rank'

    # Avoid years that are higher than the current year by clipping it to end_year
    data['cit/year'] = data['Citations'] / (end_year + 1 - data['Year'].clip(upper=end_year))
    data['cit/year'] = data['cit/year'].round(0).astype(int)

    # Sort by the selected columns, if exists
    try:
        data_ranked = data.sort_values(by=sortby_column, ascending=False)
    except Exception as e:
        print('Column name to be sorted not found. Sorting by the number of citations...')
        data_ranked = data.sort_values(by='Citations', ascending=False)
        print(e)

    # Print data
    print(data_ranked)

    # Plot by citation number
    if plot_results:
        plt.plot(rank[1:], citations, '*')
        plt.ylabel('Number of Citations')
        plt.xlabel('Rank of the keyword on Google Scholar')
        plt.title(f'Keyword: {keyword}')
        plt.show()

    # Save results
    if save_database:
        fpath_csv = os.path.join(path, keyword.replace(' ', '_').replace(':', '_') + '.csv')
        fpath_csv = fpath_csv[:MAX_CSV_FNAME]
        data_ranked.to_csv(fpath_csv, encoding='utf-8')
        # print('Results saved to', fpath_csv)

    #delete the temporary file
    if os.path.exists(temp_csv):
        os.remove(temp_csv)







if __name__ == '__main__':
        main()
