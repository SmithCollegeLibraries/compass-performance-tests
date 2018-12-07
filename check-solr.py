description = """This tool is for testing the performance of Solr.

Queries Solr with a random phrase of English words and records the response
times. Queries several times to make an average number. Also repeats query
to compare unique vs cached query times.

Note: if Solr has been dormant for a while it will be slow to respond at first.
This test should be run several times to determine "start up" performance vs
"warmed up" performance.

Assumptions: the astronomically low probably of a repeat (1 out of 5^975)
renders the random phrases virtually unique.
"""
import logging

# Check to make sure we're running Python 3!
import sys
if not (sys.version_info > (3, 0)):
    logging.error("This script requires Python 3")
    exit(1)

import random
from datasets import commonEnglishWordS
import urllib
import requests
import datetime
import json
import time

import argparse
import configparser

logging.getLogger("requests").setLevel(logging.WARNING)

import pprint

CONFIGFILE = "islandora.cfg"

NUM_UNIQUE_CHECKS = 30
NUM_REPEAT_CHECKS = 4

PLACES = 5

def makeRandomeSolrQuery():
    solrRequest = {}
    phrase = []
    
    lexiconSize = len(commonEnglishWordS)
    for i in range(PLACES):
        word = commonEnglishWordS[random.randint(0,lexiconSize - 1)]
        phrase.append(word)
    phrase = " ".join(phrase)
    urlParameters = {
        'q': phrase
    }
    solrRequest["phrase"] = phrase
    urlParameters = urllib.parse.urlencode(urlParameters)
    solrQuery = "select?%s&wt=json&indent=true&defType=dismax" % urlParameters
    solrRequest["requestUrl"] = solr_end_point + solrQuery
    return solrRequest

def doCheck(solrRequest):
    reportData = {}
    reportData["datesStamp"] = datetime.datetime.now()
    response = requests.get(solrRequest['requestUrl'])
    logging.debug(solrRequest['phrase'])
    reportData["phrase"] = solrRequest['phrase']
    logging.debug(response.json()["responseHeader"]["QTime"])
    reportData["solrQTime"] = response.json()["responseHeader"]["QTime"]
    logging.debug(response.elapsed.total_seconds())
    reportData["realTime"] = response.elapsed.total_seconds()
    logging.debug(response.json()["response"]["numFound"])
    reportData["numFound"] = response.json()["response"]["numFound"]
    return reportData

def checkSolr():
    finalReport = {}
    finalReport["data"] = []

    finalReport["summary"] = {}
    finalReport["summary"]["test start time"] = datetime.datetime.now()

    # -- MAIN LOOP --
    logging.info("Querying Solr with %s unique queries, each repeating %s times." % (NUM_UNIQUE_CHECKS, NUM_REPEAT_CHECKS) )
    for i in range(NUM_UNIQUE_CHECKS):
        solrRequest = makeRandomeSolrQuery()
        repeatCheckReport = []
        for i in range(NUM_REPEAT_CHECKS):
            singleCheckReport = doCheck(solrRequest)
            repeatCheckReport.append(singleCheckReport)
        finalReport["data"].append(repeatCheckReport)

    finalReport["summary"]["test end time"] = datetime.datetime.now()

    # -- Generate summary report --
    # Average times of 1st hit (both Solr "Qtime" and real time)
    def getAverage(data, index, type):
        sum = 0
        for queryResponses in data:
            sum = sum + queryResponses[index][type]
        average = sum/NUM_UNIQUE_CHECKS
        return average

    def getMaxMin(data, index, type):
        myList = []
        for queryResponses in data:
            myList.append(queryResponses[index][type])
        return {'max': max(myList), 'min': min(myList)}

    finalReport["averagesRealTime"] = []
    finalReport["averagesSolrQTime"] = []

    # Get average load times for 1st and last repeat query
    for i in range(NUM_REPEAT_CHECKS):
        finalReport["averagesRealTime"].append(getAverage(finalReport["data"], i, 'realTime'))
        finalReport["averagesSolrQTime"].append(getAverage(finalReport["data"], i, 'solrQTime'))

    # Get average number of search results
    finalReport["numFound"] = getMaxMin(finalReport["data"], 0, 'numFound')
    finalReport["numFound"]["average"] = getAverage(finalReport["data"], 0, 'numFound')
    # Report out max, min, and average number of results
    finalReport["summary"]["numFound max"] = finalReport["numFound"]['max']
    finalReport["summary"]["numFound min"] = finalReport["numFound"]['min']
    finalReport["summary"]["numFound ave"] = finalReport["numFound"]['average']

    # Average times of last hit (both Solr "Qtime" and real time)
    finalReport["summary"]["first (unique) time avg"] = finalReport["averagesSolrQTime"][0]
    finalReport["summary"]["last (cached) time avg"] = finalReport["averagesSolrQTime"][-1]
    finalReport["summary"]["environment"] = CLI_ARGUMENTS.SERVERCFG
    finalReport["summary"]["environment uri"] = solr_end_point
    
    return finalReport

class SamenessObserver:
    """An object for watching a series of values to see if they stay the same.
    If a fuzy match is required maxDeviation may be set to some tolerance.
    
    >>> myobserver = SamenessObserver(10)
    >>> myobserver.check(9)
    False
    >>> myobserver.check(9)
    True
    >>> myobserver.check(9)
    True
    >>> myobserver.check(10)
    False
    >>> myobserver.check(10)
    True
    >>> myobserver.check(11)
    False
    >>> myobserver = SamenessObserver(10, 1)
    >>> myobserver.check(11)
    True
    >>> myobserver.check(11)
    True
    >>> myobserver.check(10)
    True
    >>> myobserver.check(12)
    False
    >>> myobserver.check(11)
    True
    >>> 

    """

    def __init__(self, initialValue, maxDeviation=0):
        self.current = 0
        self.previous = initialValue
        self.maxDeviation = maxDeviation

    def check(self, value):
        self.current = value
        sameness = (self.previous - self.maxDeviation) <= self.current <= (self.previous + self.maxDeviation)
        self.previous = self.current
        return sameness

if __name__ == "__main__":
    argparser = argparse.ArgumentParser(description=description)
    argparser.add_argument("--debug", action='store_true', help="Go into debug mode -- fewer unique queries, more verbosity, write to files labeled with 'DEBUG'")
    argparser.add_argument("--dry-run", action='store_true', help="Do not write out json report file")
    argparser.add_argument("SERVERCFG", default="PROD", help="Name of the server configuration section e.g. 'PROD' or 'STAGE'. Edit islandora.cfg to add a server configuration section.")
    CLI_ARGUMENTS = argparser.parse_args()

    if CLI_ARGUMENTS.debug:
        NUM_UNIQUE_CHECKS = 3
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    SECTION = CLI_ARGUMENTS.SERVERCFG
    CONFIG_DATA = configparser.ConfigParser()

    try:
        CONFIG_DATA.read_file(open(CONFIGFILE), source=CONFIGFILE)
    except FileNotFoundError:
        logging.error('No configuration file found. Configuration file required. Please make a config file called %s.' % CONFIGFILE)
        exit(1)
        
    try:
        SERVER_CONFIG = CONFIG_DATA[SECTION]
    except KeyError:
        print("'%s' section not present in configuration file %s" % (SECTION, CONFIGFILE))
        exit(1)
    
    #protocol_host_port = "http://compass-fedora-prod.fivecolleges.edu:8080"
    protocol_host_port = SERVER_CONFIG['solr_protocol'] + "://" + SERVER_CONFIG['solr_hostname'] + ":" + SERVER_CONFIG['solr_port']
    solr_core_path = SERVER_CONFIG['solr_core_path']
    solr_end_point = protocol_host_port + solr_core_path
    
    logging.info("Warming up Solr")
    
    previousQTime = 0
    coldFinalReport = checkSolr()
    firstQTime = coldFinalReport["summary"]['first (unique) time avg']
    logging.info("Solr QTime: %s" % firstQTime)
    isTheSame = SamenessObserver(firstQTime, 1)
    solrQTime = 0
    while not isTheSame.check(solrQTime):
        time.sleep(60)
        coldFinalReport = checkSolr()
        solrQTime = coldFinalReport["summary"]['first (unique) time avg']
        logging.info("Solr QTime: %s" % solrQTime)

    logging.info("Solr warmed up. Recording results.")

    finalReport = coldFinalReport
    pprint.pprint(finalReport["summary"])

    if not CLI_ARGUMENTS.dry_run:
        outputFilename = 'solr-' + finalReport["summary"]["test start time"].strftime("%Y-%m-%d_%H-%M-%S-%f") + '_' + CLI_ARGUMENTS.SERVERCFG.strip() + ".json"
        if CLI_ARGUMENTS.debug:
            outputFilename = "DEBUG-" + outputFilename
        outputFilenamePath = 'output/' + outputFilename
        with open(outputFilenamePath, 'w') as fp:
            json.dump(finalReport, fp, indent=4, sort_keys=True, default=str)

        logging.info("Data logged to %s" % outputFilenamePath)
