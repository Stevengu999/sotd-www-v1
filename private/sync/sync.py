#!/usr/bin/env python

import argparse
import codecs
import json
import os
import re
from collections import Counter
from datetime import datetime

import gspread
from oauth2client.client import GoogleCredentials
from pymongo import MongoClient
from slugify import slugify
import dateutil.parser

DAPPS_SHEET_KEY = '1VdRMFENPzjL2V-vZhcc_aa5-ysf243t5vXlxC2b054g'
MONGODB_URL = os.getenv('MONGODB_URL', 'mongodb://127.0.0.1:27017/sotd')

def sync_row(db, cell_list, row_nr, last_sync, tags_cnt):
    name, teaser, description, url, github, reddit, slack, gitter, blog, wiki, the_etherian, twitter, facebook, contact, tags, license, platform, status, created, last_update, contract_address_mainnet, contract_address_ropsten, logo = cell_list

    if name == '' or status == '' or created == '' or last_update == '':
        print "Skipping empty line on row", row_nr + 1
        return

    if tags:
        tags = [tag.strip().lower() for tag in tags.split(',')]
        tags_cnt.update(tags)
    else:
        tags = []

    attributes = {
        'row_nr': row_nr,
        'teaser': teaser,
        'description': description,
        'url': url,
        'github': github,
        'reddit': reddit,
        'slack': slack,
        'gitter': gitter,
        'blog': blog,
        'wiki': wiki,
        'the_etherian': the_etherian,
        'twitter': twitter,
        'facebook': facebook,
        'contact': contact,
        'tags': tags,
        'license': license,
        'platform': platform,
        'slug': slugify(name),
        'status': status,
        'created': created,
        'last_update': last_update,
        'last_sync': last_sync,
        'contract_address_mainnet': contract_address_mainnet,
        'contract_address_ropsten': contract_address_ropsten,
        'logo': logo,
    }

    if 'featured' in tags:
        attributes['featured'] = True

    # remove attributes with empty strings
    empty_attributes = {}
    for key, value in attributes.items():
        if value == '':
            empty_attributes[key] = True
            del attributes[key]

    db.dapps.update({'name': name}, {'$set': attributes, '$unset': empty_attributes}, upsert=True)

def sync_sheet(worksheet, db):
    last_sync = datetime.utcnow()

    list_of_lists = worksheet.get_all_values()
    print list_of_lists
    row_nr = 0

    tags_cnt = Counter()

    print "Syncing dapps..."
    for cell_list in list_of_lists:
        print(cell_list)

        if row_nr > 0:
            sync_row(db, cell_list, row_nr, last_sync, tags_cnt)

        row_nr += 1

    print "Syncing tags..."
    for tag, freq in tags_cnt.items():
        db.tags.update({'tag': tag}, {'$set': {'freq': freq, 'last_sync': last_sync}}, upsert=True)

    # remove old / unused
    print "Removing old dapps..."
    print db.dapps.delete_many({'last_sync': {'$ne': last_sync}}).deleted_count
    print "Removing old tags..."
    print db.tags.delete_many({'last_sync': {'$ne': last_sync}}).deleted_count

def import_json(filename):
    data = []
    with codecs.open(filename, 'rU', 'utf-8') as f:
        for line in f:
            data.append(json.loads(line))
    return data

def import_queue(db):
    return list(db.queue.find())

def update_sheet(worksheet, db, data, prune=False):
    imported_ids = []
    for row in data:
        dapp_name = row['dapp_name']
        dt = dateutil.parser.parse(row['timestamp'])
        timestamp = dt.strftime('%Y-%m-%d')
        print row['timestamp'], dt, timestamp
        db_entry = db.dapps.find_one({'name': re.compile('^' + re.escape(dapp_name) + '$', re.IGNORECASE)})
        if db_entry:
            print 'Existing', row['dapp_name'], db_entry['row_nr']
            print worksheet.row_values(db_entry['row_nr'] + 1)
        else:
            print 'New', row['dapp_name']
            output = [
                row['dapp_name'],
                row.get('teaser', ''),
                row['description'],
                row['site'],
                row['github'],
                row['reddit'],
                row.get('slack', ''),
                row.get('gitter', ''),
                row.get('blog', ''),
                row.get('wiki', ''),
                row.get('the_etherian', ''),
                row.get('twitter', ''),
                row.get('facebook', ''),
                row['contact'],
                row['tags'],
                row['license'],
                'Ethereum',
                row['status'],
                timestamp,
                timestamp,
                row['contract_address_mainnet'],
                row['contract_address_ropsten'],
            ]
            worksheet.append_row(output)
            imported_ids.append(row['_id'])


    if prune:
        print "Pruning queue after import, count=", len(imported_ids)
        for queue_id in imported_ids:
            deletion_result = db.queue.delete_one({'_id': queue_id})
            print "removing queue_id", queue_id, ' deleted=', deletion_result.deleted_count
    else:
        print "Pruning disabled"

def parse_cli_args():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--import', action='store_true', dest='import_queue', help='import submission queue to worksheet')
    group.add_argument('--sync', action='store_true', help='sync worksheet to database')
    parser.add_argument('--prune', action='store_true', help='prune queue after import')
    return parser.parse_args()

def main():
    args = parse_cli_args()

    credentials = GoogleCredentials.get_application_default()
    credentials = credentials.create_scoped(['https://spreadsheets.google.com/feeds'])
    gc = gspread.authorize(credentials)

    sh = gc.open_by_key(DAPPS_SHEET_KEY)
    worksheet = sh.get_worksheet(0)

    client = MongoClient(MONGODB_URL)
    db = client.get_default_database()
    db.dapps.ensure_index('name')
    db.dapps.ensure_index('slug')
    db.dapps.ensure_index('tags')

    if args.import_queue:
        print "import queue"
        data = import_queue(db)
        update_sheet(worksheet, db, data, args.prune)

    if args.sync:
        print "sync"
        sync_sheet(worksheet, db)

if __name__ == '__main__':
    main()
