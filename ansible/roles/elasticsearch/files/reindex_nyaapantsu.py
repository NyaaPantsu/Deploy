# coding: utf-8
# Reindexes whatever is in the reindex torrent tables. There are two possible
# action, 'index' and 'delete'.
# To reindex the whole torrent table, run the following query:
# INSERT INTO reindex_torrents (torrent_id, action)
# SELECT torrent_id, 'index' FROM torrents WHERE deleted_at IS NULL;
#
from elasticsearch import Elasticsearch, helpers
import psycopg2, pprint, sys, time, os
import psycopg2.extras
# Default to UNICODE encoding
import psycopg2.extensions
psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
psycopg2.extensions.register_type(psycopg2.extensions.UNICODEARRAY)

CHUNK_SIZE = 100000

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

# Use a unique name to create a server-side cursor
cur = pgconn.cursor('reindex_{torrent_tablename}_cursor'.format(torrent_tablename=torrent_tablename),
                    cursor_factory=psycopg2.extras.DictCursor)
# We MUST use NO QUERY CACHE because the values are insert on triggers and
# not through pgppool.
cur.execute("""/*NO QUERY CACHE*/
               SELECT reindex_torrents_id,
                      t.torrent_id,
                      action,
                      torrent_name,
                      description,
                      hidden,
                      category,
                      sub_category,
                      status,
                      torrent_hash,
                      date,
                      uploader,
                      downloads,
                      filesize,
                      language,
                      seeders,
                      leechers,
                      completed,
                      last_scrape
               FROM {torrent_tablename} t
               INNER JOIN {scrape_tablename} s ON (t.torrent_id = s.torrent_id)
               INNER JOIN reindex_{torrent_tablename} r ON (s.torrent_id = r.torrent_id)
               WHERE deleted_at IS NULL""".format(torrent_tablename=torrent_tablename,
                                                   scrape_tablename=scrape_tablename))

cur.itersize = CHUNK_SIZE
fetches = cur.fetchmany(CHUNK_SIZE)
to_delete = list()
while fetches:
    actions = list()
    for record in fetches:
        if record == None:
            print('Record was null')
            continue
        new_action = {
          '_op_type': record['action'],
          '_index': pantsu_index,
          '_type': 'torrents',
          '_id': record['torrent_id']
        }
        if record['action'] == 'index':
            doc = {
              'id': record['torrent_id'],
              'name': record['torrent_name'],
              'category': str(record['category']),
              'sub_category': str(record['sub_category']),
              'status': record['status'],
              'hidden': record['hidden'],
              'description': record['description'],
              'hash': record['torrent_hash'],
              'date': record['date'],
              'uploader_id': record['uploader'],
              'downloads': record['downloads'],
              'filesize': record['filesize'],
              'language': record['language'],
              'seeders': record['seeders'],
              'leechers': record['leechers'],
              'completed': record['completed'],
              'last_scrape': record['last_scrape']
            }
            new_action['_source'] = doc
        to_delete.append(record['reindex_torrents_id'])
        actions.append(new_action)
    # TODO Check no errors happened
    helpers.bulk(es, actions, chunk_size=CHUNK_SIZE, request_timeout=120)
    print('Successfuly applied {count} operation'.format(count=cur.rowcount))
    fetches = cur.fetchmany(CHUNK_SIZE)

# FIXME This delete is super slow when reindexing the whole database. We do it
# at the end to reindex into ES as quick as possible.
print('Reindexing finished, deleting reindex entries.')
delete_cur = pgconn.cursor()
delete_cur.execute("""DELETE FROM reindex_{torrent_tablename}
                      WHERE reindex_torrents_id = ANY(%s)"""
          .format(torrent_tablename=torrent_tablename), (to_delete, ))
delete_cur.close()
print('Done deleting reindex entries.')
pgconn.commit() # Commit the deletes transaction
pgconn.close()
