description = """Print out a URL to an object that hasn't been used in a while.

Takes a list of PIDs in standard Solr json output:
$ curl "http://compass-fedora-dev.fivecolleges.edu:8080/solr/collection1/select?q=RELS_EXT_hasModel_uri_s%3A+%22info%3Afedora%2Fislandora%3AbookCModel%22&rows=3000&fl=PID&wt=json&indent=true"> devbooks-`date +%s`.json

$ python3 get_fresh_pid.py devbooks-1572882275.json DEV
https://compass-dev.fivecolleges.edu/islandora/object/islandora:7381
"""

import json
import random
from datetime import datetime
from datetime import timedelta
import logging
import argparse
import configparser

# in format timedelta(days=0, seconds=0, microseconds=0, milliseconds=0, minutes=0, hours=0, weeks=0)
# c.f. https://docs.python.org/3/library/datetime.html#timedelta-objects
MIN_OBJECT_URL_STALENESS = timedelta(hours=24)

CONFIGFILE = "islandora.cfg"

def getFreshObjectUrl(queryHistory, pidList, drupal_end_point, max_age):
    """pidList is list of dictionaries containing fields called 'PID'"""
    objectPid = pidList[random.randint(0,len(pidList) - 1)]['PID']
    downloadUrl = drupal_end_point + "%s" % objectPid
    try:
        dateStamp = queryHistory.state[downloadUrl]
        logging.debug("URL found in history with datestamp: %s" % dateStamp)
        objectUrlAge = datetime.now() - dateStamp
        if objectUrlAge > max_age:
            logging.debug("Object URL age %s is older than max_age %s" % (objectUrlAge, max_age))
            return downloadUrl
        else:
            logging.debug("Object URL age %s is younger than max_age %s" % (objectUrlAge, max_age))
            logging.debug("Try again! rerunning getFreshUrl()")
            try:
                return getFreshObjectUrl(queryHistory, pidList, drupal_end_point, max_age)
            except RecursionError:
                logging.error("FAIL Exhausted available list of objects")
                exit(1)
    except KeyError:
        # That URL is not even on the list so it's definitely fresh
        logging.debug("URL not even in history")
        queryHistory.recordQuery(downloadUrl)
        return downloadUrl

class QueryHistory:
    def __init__(self, historyfile):
        self.historyfile = historyfile
        self.state = self._loadQueryHistory(historyfile)

    def _loadQueryHistory(self, queryHistoryFile):
        try:
            with open(queryHistoryFile, 'r') as fp:
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

    def recordQuery(self, downloadUrl):
        self.state[downloadUrl] = datetime.now()
        with open(self.historyfile, 'w') as fp:
            json.dump(self.state, fp, indent=4, sort_keys=True, default=str)

def loadPidList(pidListFile):
    """Take json output from Solr and return just the 'docs' section, which is a
     list of dictionaries containing fields"""
    with open(pidListFile, 'r') as fp:
        pidListData = json.load(fp)
    return pidListData['response']['docs']

if __name__ == '__main__':
    argparser = argparse.ArgumentParser(description=description)
    argparser.add_argument("PIDLISTFILE", help="List of PIDs to draw from. Standard Solr json output including PID field.")
    argparser.add_argument("SERVERCFG", default="PROD", help="Name of the server configuration section e.g. 'PROD' or 'STAGE'. Edit islandora.cfg to add a server configuration section.")
    argparser.add_argument("--historyfile", default="queryhistory.json", help="Name of file to record what queries were made when.")
    cliArguments = argparser.parse_args()

    section = cliArguments.SERVERCFG
    configData = configparser.ConfigParser()
    largeobjectslistFilename = 'largeobjectslist-%s.cache' % cliArguments.SERVERCFG

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

    drupal_protocol_host_port = serverConfig['drupal_protocol'] + "://" + serverConfig['drupal_hostname']
    drupal_object_path = serverConfig['drupal_object_path']
    drupal_end_point = drupal_protocol_host_port + drupal_object_path

    mylist = loadPidList(cliArguments.PIDLISTFILE)
    queryHistory = QueryHistory(cliArguments.historyfile)
    freshUrl = getFreshObjectUrl(queryHistory, mylist, drupal_end_point, MIN_OBJECT_URL_STALENESS)
    print(freshUrl)
