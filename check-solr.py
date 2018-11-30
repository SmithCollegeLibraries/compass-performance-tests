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

import argparse
import configparser

logging.getLogger("requests").setLevel(logging.WARNING)

import pprint

CONFIGFILE = "compass.cfg"

NUM_UNIQUE_CHECKS = 30
NUM_REPEAT_CHECKS = 4

PLACES = 5

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

FINAL_REPORT["averagesRealTime"] = []
FINAL_REPORT["averagesSolrQTime"] = []

# Get average load times for 1st and last repeat query
for i in range(NUM_REPEAT_CHECKS):
    FINAL_REPORT["averagesRealTime"].append(getAverage(FINAL_REPORT["data"], i, 'realTime'))
    FINAL_REPORT["averagesSolrQTime"].append(getAverage(FINAL_REPORT["data"], i, 'solrQTime'))

# Get average number of search results
FINAL_REPORT["numFound"] = getMaxMin(FINAL_REPORT["data"], 0, 'numFound')
FINAL_REPORT["numFound"]["average"] = getAverage(FINAL_REPORT["data"], 0, 'numFound')
# Report out max, min, and average number of results
FINAL_REPORT["summary"]["numFound max"] = FINAL_REPORT["numFound"]['max']
FINAL_REPORT["summary"]["numFound min"] = FINAL_REPORT["numFound"]['min']
FINAL_REPORT["summary"]["numFound ave"] = FINAL_REPORT["numFound"]['average']

# Average times of last hit (both Solr "Qtime" and real time)
FINAL_REPORT["summary"]["first (unique) time avg"] = FINAL_REPORT["averagesSolrQTime"][0]
FINAL_REPORT["summary"]["last (cached) time avg"] = FINAL_REPORT["averagesSolrQTime"][-1]
FINAL_REPORT["summary"]["environment"] = cliArguments.SERVERCFG
FINAL_REPORT["summary"]["environment uri"] = solr_end_point


pprint.pprint(FINAL_REPORT["summary"])

if not cliArguments.dry_run:
    outputFilename = 'solr-' + FINAL_REPORT["summary"]["test start time"].strftime("%Y-%m-%d_%H-%M-%S-%f") + '_' + cliArguments.SERVERCFG.strip() + ".json"
    if cliArguments.debug:
        outputFilename = "DEBUG-" + outputFilename
    outputFilenamePath = 'output/' + outputFilename
    with open(outputFilenamePath, 'w') as fp:
        json.dump(FINAL_REPORT, fp, indent=4, sort_keys=True, default=str)

    logging.info("Data logged to %s" % outputFilenamePath)
