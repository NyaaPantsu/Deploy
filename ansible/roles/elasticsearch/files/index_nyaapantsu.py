# coding: utf-8
from elasticsearch import Elasticsearch, helpers
import psycopg2, pprint, sys, time, os

CHUNK_SIZE = 10000

def getEnvOrExit(var):
    environment = ''
    try:
        environment = os.environ[var]
    except:
        print('[Error]: Environment variable ' + var + ' not defined.')
        sys.exit(1)
    return environment

dbparams = getEnvOrExit('PANTSU_DBPARAMS')
pantsu_index = getEnvOrExit('PANTSU_ELASTICSEARCH_INDEX')
torrent_tablename = getEnvOrExit('PANTSU_TORRENT_TABLENAME')
scrape_tablename = getEnvOrExit('PANTSU_SCRAPE_TABLENAME')

es = Elasticsearch()
pgconn = psycopg2.connect(dbparams)

torrent_cur = pgconn.cursor()
torrent_cur.execute("""SELECT torrent_id, torrent_name, description, hidden, category, sub_category, status, 
                       torrent_hash, date, uploader, downloads, filesize, language, seeders, leechers, completed, last_scrape
                       FROM {torrent_tablename} t INNER JOIN {scrape_tablename} s ON (t.torrent_id = s.torrent_id)
                       WHERE deleted_at IS NULL""".format(torrent_tablename=torrent_tablename))

torrent_fetches = torrent_cur.fetchmany(CHUNK_SIZE)
while torrent_fetches:
    actions = list()
    for torrent_id, torrent_name, description, hidden, category, sub_category, status, torrent_hash, date, uploader, downloads, filesize, language, seeders, leechers, completed, last_scrape in torrent_fetches:
        doc = {
          'id': torrent_id,
          'name': torrent_name.decode('utf-8'),
          'category': str(category),
          'sub_category': str(sub_category),
          'status': status,
          'hash': torrent_hash,
          'hidden': hidden,
          'description': description,
          'date': date,
          'uploader_id': uploader,
          'downloads': downloads,
          'filesize': filesize,
          'seeders': seeders,
          'leechers': leechers,
          'completed': completed,
          'last_scrape': last_scrape,
          'language': language
        }
        action = {
            '_index': pantsu_index,
            '_type': 'torrents',
            '_id': torrent_id,
            '_source': doc
        }
        actions.append(action)
    helpers.bulk(es, actions, chunk_size=CHUNK_SIZE, request_timeout=120)
    del(torrent_fetches)
    torrent_fetches = torrent_cur.fetchmany(CHUNK_SIZE)
cur.close()
pgconn.close()
