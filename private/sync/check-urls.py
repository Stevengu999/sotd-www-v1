#!/usr/bin/env python

import os

import csv
import requests
from pymongo import MongoClient
from joblib import Parallel, delayed

MONGODB_URL = os.getenv('MONGODB_URL', 'mongodb://127.0.0.1:27017/sotd')

IGNORE_STATUSES = ['abandoned']
URL_FIELDS = ['url', 'github', 'wiki', 'blog', 'twitter', 'facebook', 'slack', 'gitter', 'logo']

REQUEST_TIMEOUT = 30

def check_url(url):
    code = 0
    error = ''
    error_message = ''
    body = ''
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        code = response.status_code
        body = response.text
    except requests.exceptions.SSLError as err:
        error = 'ssl-error'
        error_message = str(err)
    except requests.exceptions.ConnectionError as err:
        error = 'connection-error'
        error_message = str(err)
    except requests.exceptions.MissingSchema as err:
        error = 'missing-schema'
        error_message = str(err)
    except requests.exceptions.InvalidSchema as err:
        error = 'invalid-schema'
        error_message = str(err)
    except requests.exceptions.Timeout as err:
        error = 'timeout'
        error_message = str(err)

    if code == 200 and is_parking(body):
        error = 'domain-parking'
        error_message = "domain parking page detected "

    return code, error, error_message

TEST_URLS = [
    # "http://www.stackoverflow.com",
    # "http://eyepi.com/",
    # "http://communitycurrency.website/",
    # "http://dappstore.io",
    # "http://ethereumwall.com/",
    # "https://github.com/profeth/",
    # "http://app.etherdoubler.com/",
    # "http://insureth.mkvd.net/",
    # "https://ventureequity.exchange/",
    # "http://lazooz.org/", # TODO detect
    # "http://etherscripter.com",
    # "http://airlock.me/",
    # "http://atomrigs.blogspot.com",
    # "http://etherboard.io/",
    # "http://quorumwallet.com/",
    # "http://verbatm.info/",
    # "https://ethereumpyramid.com/",
    # "http://cryptorps.com/",
    # "http://jaakme.in/"
]


PARKING_TEXTS = [
    "This domain is for sale.",
    "This domain may be for sale.",
    "This domain was recently registered",
    "This Domain Name Has Expired",
    "Sedo's Domain Parking",
    "This page is provided courtesy of GoDaddy.com",
    "Domain Parking",
    "parkingcrew.net",
    "This page has been suspended"
]

def is_parking(body):
    for text in PARKING_TEXTS:
        if text in body:
            return True
    return False

def check_dapp(dapp):
    result = []
    slug = dapp.get('slug')
    for field in URL_FIELDS:
        url = dapp.get(field)
        if not url:
            continue
        code, error, error_message = check_url(url)
        if code != 200 or error:
            err_report = [slug, field, url, str(code), error, error_message]
            result.append(err_report)
            print("\t".join(err_report))
    return result

def check_dapps(db):
    fields = {'slug': 1}
    fields.update({field: 1 for field in URL_FIELDS})

    dapps = db.dapps.find({'url': {'$ne': ''}, 'status': {'$nin': IGNORE_STATUSES}}, fields)

    result = Parallel(n_jobs=-1, verbose=10)(delayed(check_dapp)(dapp) for dapp in dapps)

    with open('url_failures.csv', 'wb') as csvfile:
        err_writer = csv.writer(csvfile)
        err_writer.writerow(['dapp', 'field', 'url', 'http_code', 'error', 'message'])
        for dapp in result:
            for row in dapp:
                err_writer.writerow(row)

def main():
    client = MongoClient(MONGODB_URL)
    db = client.get_default_database()

    check_dapps(db)

if __name__ == '__main__':
    main()
