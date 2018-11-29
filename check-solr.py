"""Assumption: the astronomically low probably of a repeat (1 out of 5^975)
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
import argparse
import configparser
logging.basicConfig(level=logging.INFO)
logging.getLogger("requests").setLevel(logging.WARNING)

import pprint



CONFIGFILE = "compass.cfg"

NUM_UNIQUE_CHECKS = 30
NUM_REPEAT_CHECKS = 4

PLACES = 5

argparser = argparse.ArgumentParser()
argparser.add_argument("SERVERCFG", default="PROD", help="Name of the server configuration section e.g. 'PROD' or 'STAGE'. Edit compass.cfg to add a server configuration section.")
cliArguments = argparser.parse_args()

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

FINAL_REPORT = {}

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
    solrRequest["requestUrl"] = protocol_host_port + "/solr/collection1/select?%s&wt=json&indent=true&defType=dismax" % urlParameters
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
    return reportData

FINAL_REPORT["data"] = []

FINAL_REPORT["summary"] = {}
FINAL_REPORT["summary"]["test start time"] = datetime.datetime.now()

# -- MAIN LOOP --
logging.info("Querying Solr with %s unique queries, each repeating %s times." % (NUM_UNIQUE_CHECKS, NUM_REPEAT_CHECKS) )
for i in range(NUM_UNIQUE_CHECKS):
    solrRequest = makeRandomeSolrQuery()
    repeatCheckReport = []
    for i in range(NUM_REPEAT_CHECKS):
        singleCheckReport = doCheck(solrRequest)
        repeatCheckReport.append(singleCheckReport)
    FINAL_REPORT["data"].append(repeatCheckReport)

FINAL_REPORT["summary"]["test end time"] = datetime.datetime.now()

# -- Generate summary report --
# Average times of 1st hit (both Solr "Qtime" and real time)
def getAverageTime(data, index, type):
    sum = 0
    for queryResponses in data:
        sum = sum + queryResponses[index][type]
    average = sum/NUM_UNIQUE_CHECKS
    return average

FINAL_REPORT["averagesRealTime"] = []
FINAL_REPORT["averagesSolrQTime"] = []

for i in range(NUM_REPEAT_CHECKS):
    FINAL_REPORT["averagesRealTime"].append(getAverageTime(FINAL_REPORT["data"], i, 'realTime'))
    FINAL_REPORT["averagesSolrQTime"].append(getAverageTime(FINAL_REPORT["data"], i, 'solrQTime'))

# Average times of last hit (both Solr "Qtime" and real time)

FINAL_REPORT["summary"]["1st time avg"] = FINAL_REPORT["averagesSolrQTime"][0]
FINAL_REPORT["summary"]["last time avg"] = FINAL_REPORT["averagesSolrQTime"][-1]

pprint.pprint(FINAL_REPORT["summary"])
