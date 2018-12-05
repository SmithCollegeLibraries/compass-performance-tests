description = """Measure Fedora object retreval response times.
Keeps track of previous requests to avoid repeats. Minimum time elapsed before
accessing the same url can be set with MIN_OBJECT_URL_STALENESS below.
"""
import requests
import random
from datetime import datetime
from datetime import timedelta
import statistics
import pickle
import json
import logging
import argparse
import configparser


NUM_UNIQUE_CHECKS = 30

MIN_ASSET_SIZE = 10000000 # in bytes

# Maximum age of large asset list cache
LIST_CACHE_EXPIRATION = timedelta(days=30)
# in format timedelta(days=0, seconds=0, microseconds=0, milliseconds=0, minutes=0, hours=0, weeks=0)
# c.f. https://docs.python.org/3/library/datetime.html#timedelta-objects

MIN_OBJECT_URL_STALENESS = timedelta(minutes=30)
# Format same as LIST_CACHE_EXPIRATION

logging.getLogger("requests").setLevel(logging.WARNING)

import pprint

CONFIGFILE = "compass.cfg"

logging.getLogger("requests").setLevel(logging.WARNING)

argparser = argparse.ArgumentParser(description=description)
argparser.add_argument("--debug", action='store_true', help="Go into debug mode -- fewer unique queries, more verbosity, write to files labeled with 'DEBUG'")
argparser.add_argument("--dry-run", action='store_true', help="Do not write out json report file")
argparser.add_argument("SERVERCFG", default="PROD", help="Name of the server configuration section e.g. 'PROD' or 'STAGE'. Edit compass.cfg to add a server configuration section.")
cliArguments = argparser.parse_args()

if cliArguments.debug:
    NUM_UNIQUE_CHECKS = 3
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)

section = cliArguments.SERVERCFG
configData = configparser.ConfigParser()

try:
    configData.read_file(open(CONFIGFILE), source=CONFIGFILE)
except FileNotFoundError:
    logging.error('No configuration file found. Configuration file required. Please make a config file called %s.' % CONFIGFILE)
    exit(1)
    
try:
    serverConfig = configData[section]
except KeyError:
    print("'%s' section not present in configuration file %s" % (section, CONFIGFILE))
    exit(1)

#protocol_host_port = "http://compass-fedora-prod.fivecolleges.edu:8080"
protocol_host_port = serverConfig['solr_protocol'] + "://" + serverConfig['solr_hostname'] + ":" + serverConfig['solr_port']
solr_core_path = serverConfig['solr_core_path']
solr_end_point = protocol_host_port + solr_core_path

def makeSampleObjectList():
    """Query Solr for a good size list of objects then filter them by size to
    produce a list of objects that are greater than MIN_ASSET_SIZE.
    """
    SolrQueryUrl = "http://compass-fedora-prod.fivecolleges.edu:8080/solr/collection1/select?q=*%3A*&rows=100000&fl=PID%2Cfedora_datastream_latest_OBJ_SIZE_ms&wt=json&indent=true"
    logging.debug("Getting a random list of objects")
    request = requests.get(SolrQueryUrl)
    objectList = request.json()["response"]["docs"]
    # Now filter the list for objects that are a decent size.
    # Solr is storing data stream sizes in a string field so a range
    # query doesn't work.
    # c.f. https://groups.google.com/forum/#!topic/islandora/6XsphOdOdjU
    bigEnoughObjectsList = []
    for myObject in objectList:
        try:
            if int(myObject['fedora_datastream_latest_OBJ_SIZE_ms'][0]) > MIN_ASSET_SIZE:
                logging.debug("Object is greater than %s. Adding to list." % MIN_ASSET_SIZE)
                bigEnoughObjectsList.append(myObject)
        except KeyError:
            pass
    logging.debug("%s objects found" % len(bigEnoughObjectsList))
    return bigEnoughObjectsList

def cacheObjectList(objectList):
    """Save cache file of list of good sized objects as a Python pickle.
    """
    logging.debug("Writing list of large objects to cache file")
    objectListCache = {
        'dateStamp': datetime.now(),
        'objectList': objectList
    }
    with open('largeobjectslist.cache', 'wb') as f:
        # Pickle the 'data' dictionary using the highest protocol available.
        pickle.dump(objectListCache, f, pickle.HIGHEST_PROTOCOL)

def loadObjectList():
    """Return a list of Compass objects that are good for testing on. Uses
    caching to improve speed. If the cache is older than LIST_CACHE_EXPIRATION
    then it will get a fresh list from Solr and filter for objects that are
    large enough, and then will save it to the cache file.
    """
    logging.debug("Loading an object list")

    try:
        with open('largeobjectslist.cache', 'rb') as f:
            objectListCache = pickle.load(f)
        cacheAge = datetime.now() - objectListCache['dateStamp']
        logging.debug("Cache timestamp: %s" % objectListCache['dateStamp'])
        logging.debug("Cache age: %s" % cacheAge)
        logging.debug("LIST_CACHE_EXPIRATION: %s" % LIST_CACHE_EXPIRATION)
        # If the cache is older than LIST_CACHE_EXPIRATION in days
        if cacheAge > LIST_CACHE_EXPIRATION:
            logging.debug("Cache too old, getting a fresh list")
            objectList = makeSampleObjectList()
            logging.debug("Cache-ing it")
            cacheObjectList(objectList)
            return objectList
        else:
            logging.debug("Using cached list")
            return objectListCache['objectList']
    except FileNotFoundError:
        logging.debug("No cache file, getting a fresh list")
        objectList = makeSampleObjectList()
        logging.debug("Cache-ing it")
        cacheObjectList(objectList)
        return objectList

def downloadObject(downloadUrl):
    report = {
        'type': '',
        'assetSize': 0,
        'transferElapsedTime': 0,
        'transferMBytesPerS': 0,
        'responseTime': 0,
        'url': '',
        'objectPid': '',
        'timeStamp': datetime.now(),
    }
    logging.info(downloadUrl)
    report['url'] = downloadUrl
    requestStart=datetime.now()
    request = requests.get(downloadUrl, allow_redirects=True)
    report['transferElapsedTime'] = datetime.now()-requestStart
    report['transferElapsedTime'] = float(report['transferElapsedTime'].total_seconds())
    logging.debug('Transfer time: %s' % report['transferElapsedTime'])
    logging.debug(request.headers.get('content-type'))
    report['type'] = request.headers.get('content-type')
    logging.debug("Request response time: %s" % request.elapsed.total_seconds())
    report['responseTime'] = request.elapsed.total_seconds()
    logging.debug("Fedora datastream size: %s" % request.headers.get('content-length', None))
    open('.last-fedora-download', 'wb').write(request.content)
    report['assetSize'] = int(request.headers.get('content-length', None))
    report['transferMBytesPerS'] = (report['assetSize']/1000000)/report['transferElapsedTime']
    return report

def loadQueryHistory():
    try:
        with open('fedora-queryhistory.json', 'r') as fp:
            queryHistoryJson = json.load(fp)
        # Convert all the date strings into real dates... D:
        queryHistory = {}
        for key,value in queryHistoryJson.items():
            value = datetime.strptime(value,'%Y-%m-%d %H:%M:%S.%f')
            queryHistory[key] = value
    except FileNotFoundError:
        logging.info("No query history file, starting a fresh dictionary")
        queryHistory = {}
    return queryHistory


transferRates = []
responseTimes = []

queryHistory = loadQueryHistory()

objectList = loadObjectList()
logging.debug("Using object list of %s items" % len(objectList))
def getFreshObjectUrl():
    objectPid = objectList[random.randint(0,len(objectList) - 1)]['PID']
    downloadUrl = "https://compass.fivecolleges.edu/islandora/object/%s/datastream/OBJ/download" % objectPid
    try:
        dateStamp = queryHistory[downloadUrl]
        logging.debug("URL found in history with datestamp: %s" % dateStamp)
        objectUrlAge = datetime.now() - dateStamp
        if objectUrlAge > MIN_OBJECT_URL_STALENESS:
            logging.debug("Object URL age %s is older than MIN_OBJECT_URL_STALENESS %s" % (objectUrlAge, MIN_OBJECT_URL_STALENESS))
            return downloadUrl
        else:
            logging.debug("Object URL age %s is younger than MIN_OBJECT_URL_STALENESS %s" % (objectUrlAge, MIN_OBJECT_URL_STALENESS))
            logging.debug("Try again! rerunning getFreshUrl()")
            return getFreshObjectUrl()
    except KeyError:
        # That URL is not even on the list so it's definitely fresh
        logging.debug("URL not even in history")
        return downloadUrl

for i in range(NUM_UNIQUE_CHECKS):
    logging.debug("***** START LOOP *****")
    downloadUrl = getFreshObjectUrl()
    queryHistory[downloadUrl] = datetime.now()
    objectReport = downloadObject(downloadUrl)
    logging.debug("Save query history for later")
    with open('fedora-queryhistory.json', 'w') as fp:
        # Do this on every request in case something happens before we get to
        # the end of the program
        json.dump(queryHistory, fp, indent=4, sort_keys=True, default=str)
#    objectReport['objectPid'] = objectPid
    transferRates.append(objectReport['transferMBytesPerS'])
    responseTimes.append(objectReport['responseTime'])

logging.debug(transferRates)
logging.debug(responseTimes)
logging.info("Mean response time: %s seconds" % statistics.mean(responseTimes))
logging.info("Mean transfer rate: %s MB/s" % statistics.mean(transferRates))
