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

import requests, os, datetime, argparse
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import pandas as pd
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
NRESULTS = 100 # Fetch 100 articles
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

    try:
        download_link = div.find("div", {"class": "gs_ggs gs_fl"}).find("a").get("href")
        if "pdf" in download_link.lower():
            return download_link
    except Exception:
        pass
    return None
def download_pdf(url,path):

    try:
        response = requests.get(url, stream=True)
        if response.headers.get("content-type") == "application/pdf":
            with open(path, "wb") as file:
                for chunk in response.iter_content(chunk_size=1024):
                    file.write(chunk)
            print(f"Downloaded: {path}")
        else:
            print(f"Skipping non-PDF content: {url}")
    except Exception as e:
        print(f"Failed to download PDF from {url}. Error: {e}")
        
def format_strings(strings):
    if len(strings) == 1:
        return f'lang_{strings[0]}'
    else:
        return '%7C'.join(f'lang_{s}' for s in strings)

def main():
    def main():
        # Get command line arguments
        keyword, number_of_results, save_database, path, sortby_column, langfilter, plot_results, start_year, end_year, debug = get_command_line_args()

        print("Running with the following parameters:")
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
        links, title, citations, year, author, venue, publisher, rank, download_links = ([] for _ in range(9))
        rank = [0]  # Start rank at 0
        pdf_save_dir = os.path.join(path, "PDFs")  # Directory for saving PDFs
        os.makedirs(pdf_save_dir, exist_ok=True)

        # Function to extract download links
        def get_download_link(div):
            try:
                download_link = div.find("div", {"class": "gs_ggs gs_fl"}).find("a").get("href")
                if "pdf" in download_link.lower():
                    return download_link
            except Exception:
                pass
            return None

        # Function to download PDF
        def download_pdf(url,path):
            try:
                response = requests.get(url, stream=True)
                if response.headers.get("content-type") == "application/pdf":
                    with open(path, "wb") as file:
                        for chunk in response.iter_content(chunk_size=1024):
                            file.write(chunk)
                    print(f"Downloaded: {path}")
                else:
                    print(f"No download link: {url}")
            except Exception as e:
                print(f"Failed to download PDF from {url}. Error: {e}")

        # Get content from number_of_results URLs
        for n in range(0, number_of_results, 10):
            url = GSCHOLAR_MAIN_URL.format(str(n), keyword.replace(' ', '+'))
            if debug:
                print("Opening URL:", url)

            print(f"Loading next {n + 10} results")
            page = session.get(url)
            c = page.content
            if any(kw in c.decode('ISO-8859-1') for kw in ROBOT_KW):
                print("Robot checking detected, handling with selenium (if installed)")
                try:
                    c = get_content_with_selenium(url)
                except Exception as e:
                    print("No success. The following error was raised:")
                    print(e)

            # Create parser
            soup = BeautifulSoup(c, 'html.parser', from_encoding='utf-8')

            # Get stuff
            mydivs = soup.findAll("div", {"class": "gs_or"})
            for div in mydivs:
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

                # Download PDF if download link is available
                if download_link:
                    pdf_filename = f"{rank[-1]}_{re.sub(r'[^\w]', '_', title[-1])[:50]}.pdf"
                    pdf_save_path = os.path.join(pdf_save_dir, pdf_filename)
                    download_pdf(download_link, pdf_save_path)

                rank.append(rank[-1] + 1)

            # Delay
            sleep(random.uniform(0.5, 3))

        # Create a dataset and sort by the number of citations
        data = pd.DataFrame(list(zip(author, title, citations, year, publisher, venue, links, download_links)),
                            index=rank[1:],
                            columns=['Author', 'Title', 'Citations', 'Year', 'Publisher', 'Venue', 'Source',
                                     'Download Link'])
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
            print('Results saved to', fpath_csv)

    if __name__ == '__main__':
        main()


if __name__ == '__main__':
        main()
