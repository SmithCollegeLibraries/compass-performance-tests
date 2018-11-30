dsc="""
Generate reports about Solr performance from logged data.
"""

import json
import glob
import logging
import argparse
import pprint

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Set up command line argument parser
argparser = argparse.ArgumentParser(description=dsc)
argparser.add_argument("ENVIRONMENT", default="PROD", help="Name of the system environment e.g. 'PROD' or 'STAGE'.")
argparser.add_argument("OUTPUT", help="File to write to e.g. report.json.")
cliArguments = argparser.parse_args()
environment = cliArguments.ENVIRONMENT

reportsData_S = []

fileList = glob.glob(r'output/solr*.json')
fileList.sort() # Keep records in cronological order -- based on filenames which include date

for individualReportFilename in fileList:
    logging.debug(individualReportFilename)
    with open(individualReportFilename) as infp:
         individualReportData = json.load(infp)
         if individualReportData['summary']['environment'] == environment:
             reportsData_S.append(individualReportData)

reportOutputData = []

for individualReportData in reportsData_S:
    reportOutputDataRecord = {}
    logging.debug(individualReportData['summary']['test start time'])
    reportOutputDataRecord['datestamp'] = individualReportData['summary']['test start time']
    logging.debug(individualReportData['summary']['first (unique) time avg'])
    reportOutputDataRecord['avgqtime'] = individualReportData['summary']['first (unique) time avg']
    logging.debug(individualReportData['summary']['numFound ave'])
    reportOutputDataRecord['avgnumfound'] = individualReportData['summary']['numFound ave']
    reportOutputData.append(reportOutputDataRecord)

outfilename = cliArguments.OUTPUT.strip()
logging.debug(outfilename)
with open(outfilename, 'w') as outfp:
    json.dump(reportOutputData, outfp, indent=4, sort_keys=True, default=str)
