# compass-performance-tests
Tools for assessing the performance of compass, particularly as the number of objects and amount of OCR data increases as part of the YWCA ingest project.

## check-solr.py

This tool is for testing the performance of Solr.

Queries Solr with a random phrase of English words and records the response
times. Queries several times to make an average number. Also repeats query
to compare unique vs cached query times.

Note: if Solr has been dormant for a while it will be slow to respond at first.
This test should be run several times to determine "start up" performance vs
"warmed up" performance.

Assumptions: the astronomically low probably of a repeat (1 out of 5^975)
renders the random phrases virtually unique.
