description = """Compare object page query times between STAGE and PROD.

$ curl "http://compass-fedora-stage.fivecolleges.edu:8080/solr/collection1/select?q=RELS_EXT_hasModel_uri_s%3A+%22info%3Afedora%2Fislandora%3AbookCModel%22&rows=3000&fl=PID&wt=json&indent=true" > stagebooks-`date +%s`.json

$ python3 compare_prodVstage_object_page_query_times.py stagebooks-1572891400.json --historyfile book-history.json --multiple 300 --report-file output.csv

If you use the --use-lighthouse option make sure that lighhouse is installed as a command line tool: https://developers.google.com/web/tools/lighthouse#cli
"""
from get_fresh_pid import QueryHistory, getFreshObjectUrl, loadPidList
import argparse
import configparser
import logging
from datetime import timedelta
from datetime import datetime
import requests
import csv
import json
import subprocess

logging.getLogger("requests").setLevel(logging.WARNING)

# in format timedelta(days=0, seconds=0, microseconds=0, milliseconds=0, minutes=0, hours=0, weeks=0)
# c.f. https://docs.python.org/3/library/datetime.html#timedelta-objects
MIN_OBJECT_URL_STALENESS = timedelta(hours=24)

argparser = argparse.ArgumentParser(description=description)
argparser.add_argument("--dry-run", action='store_true', help="Don't do the query, just print the URLs and mark them as used")
argparser.add_argument("PIDLISTFILE", help="List of PIDs to draw from. Standard Solr json output including PID field.")
argparser.add_argument("--historyfile", default="queryhistory.json", help="Name of file to record what queries were made when.")
argparser.add_argument("--multiple", default=1, type=int, help="Number of pairs of objects to run the test on.")
argparser.add_argument("--report-file", help="file to write report to")
argparser.add_argument("--use-lighthouse", action='store_true', help="Launch lighthouse for additional statistics. (must be installed already as a cli tool)")

cliArguments = argparser.parse_args()

configData = configparser.ConfigParser()

class Report:
    def __init__(self):
        self.data = []
    def log(self, logEntry):
        self.data.append(logEntry)
    def write(self, filename):
        with open(filename, 'w') as fp:
            reportFields = [
                'timeStamp',
                'stageUrl',
                'stageDuration',
                'prodUrl',
                'prodDuration',
                'durationRatio',
                'stageXDrupalCache',
                'stageCacheControl',
                'prodXDrupalCache',
                'prodCacheControl',
                'stageHeaders',
                'prodHeaders',
            ]
            lighthouseFields = [
                'stage-interactive',
                'stage-time_to_first_byte',
                'stage-post_TTFB_time',
                'prod-interactive',
                'prod-time_to_first_byte',
                'prod-post_TTFB_time',
                'post_TTFB_ratio',
            ]
            if cliArguments.use_lighthouse is True:
                reportFields.extend(lighthouseFields)

            csvWriter = csv.DictWriter(fp, reportFields)
            csvWriter.writeheader()
            csvWriter.writerows(self.data)

def queryTimer(url):
    queryHistory.recordQuery(url)
    requestStart = datetime.now()
    try:
        request = requests.get(url, allow_redirects=True)
        transferElapsedTime = datetime.now()-requestStart
    except Exception as e:
        logging.error(e)
        transferElapsedTime = 0

    if cliArguments.use_lighthouse is True:
        lighthouseCommand = 'lighthouse "%s" --only-categories=performance --output=json --emulated-form-factor=none --throttling-method=provided --chrome-flags="--headless"' % url
        p = subprocess.Popen(lighthouseCommand, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        buffer = p.stdout.read()
        try:
            lighthouseData = json.loads(buffer.decode('UTF-8'))
        except Exception as e:
            logging.error(e)
            # If json can't be parsed just make an empty data structure
            lighthouseData = {}

    try:
        interactive = lighthouseData['audits']['interactive']['numericValue']
    except:
        interactive = 0
    try:
        time_to_first_byte = lighthouseData['audits']['time-to-first-byte']['numericValue']
    except:
        time_to_first_byte = 0
    post_TTFB_time = interactive - time_to_first_byte

    report = {
        'transferElapsedTime': transferElapsedTime,
        'headers': request.headers,
    }

    if cliArguments.use_lighthouse is True:
        report.update({
            'post_TTFB_time': post_TTFB_time,
            'interactive': interactive,
            'time_to_first_byte': time_to_first_byte,
        })
    
    return report

def runComparativeQueries(stageUrl, prodUrl):
    logEntry = {}
    logEntry['timeStamp'] = datetime.now()
    stageQueryTimerReport = queryTimer(stageUrl)
    stageDuration = stageQueryTimerReport['transferElapsedTime']
    prodQueryTimerReport = queryTimer(prodUrl)
    prodDuration = prodQueryTimerReport['transferElapsedTime']
    logEntry['durationRatio'] = str(stageDuration / prodDuration)

    logEntry['stageUrl'] = stageUrl
    logEntry['stageDuration'] = str(stageDuration)
    try:
        logEntry['stageXDrupalCache'] = stageQueryTimerReport['headers']['X-Drupal-Cache']
    except:
        logEntry['stageXDrupalCache'] = ''
    try:
        logEntry['stageCacheControl'] = stageQueryTimerReport['headers']['Cache-Control']
    except:
        logEntry['stageCacheControl'] = ''
    logEntry['stageHeaders'] = str(stageQueryTimerReport['headers'])

    if cliArguments.use_lighthouse is True:
        logEntry['stage-interactive'] = stageQueryTimerReport['interactive']
        logEntry['stage-time_to_first_byte'] = stageQueryTimerReport['time_to_first_byte']
        logEntry['stage-post_TTFB_time'] = stageQueryTimerReport['post_TTFB_time']

    logEntry['prodUrl'] = prodUrl
    logEntry['prodDuration'] = str(prodDuration)
    try:
        logEntry['prodXDrupalCache'] = prodQueryTimerReport['headers']['X-Drupal-Cache']
    except:
        logEntry['prodXDrupalCache'] = ''
    try:
        logEntry['prodCacheControl'] = prodQueryTimerReport['headers']['Cache-Control']
    except:
        logEntry['prodCacheControl'] = ''
    logEntry['prodHeaders'] = str(prodQueryTimerReport['headers'])

    if cliArguments.use_lighthouse is True:
        logEntry['prod-interactive'] = prodQueryTimerReport['interactive']
        logEntry['prod-time_to_first_byte'] = prodQueryTimerReport['time_to_first_byte']
        logEntry['prod-post_TTFB_time'] = prodQueryTimerReport['post_TTFB_time']
        try:
            logEntry['post_TTFB_ratio'] = str(stageQueryTimerReport['post_TTFB_time'] / prodQueryTimerReport['post_TTFB_time'])
        except ZeroDivisionError:
            logEntry['post_TTFB_ratio'] = 0

    return logEntry

if __name__ == "__main__":
    report = Report()
    mylist = loadPidList(cliArguments.PIDLISTFILE)
    queryHistory = QueryHistory(cliArguments.historyfile)

    for i in range(0, cliArguments.multiple):
        path = getFreshObjectUrl(queryHistory, mylist, '/object/', MIN_OBJECT_URL_STALENESS)
        stageUrl = "https://compass-stage.fivecolleges.edu" + path
        prodUrl = "https://compass.fivecolleges.edu" + path

        if not cliArguments.dry_run:
            logEntry = runComparativeQueries(stageUrl, prodUrl)
            report.log(logEntry)
            report.write(cliArguments.report_file)
        else:
            if cliArguments.multiple > 1:
                print(stageUrl + ',' + prodUrl)
            else:
                print(stageUrl)
                print(prodUrl)
