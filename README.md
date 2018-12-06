# compass-performance-tests
Tools for assessing the performance of compass, particularly as the number of objects and amount of OCR data increases as part of the YWCA ingest project.

These tools are intended to be run on a machine on the same network as the services (to minimize internet network delays skewing results). If not, you must at least connect via VPN for them to work at all.

## check-solr.py

This tool is for testing the performance of Solr.

Queries Solr with a random phrase of English words and records the response
times. Queries several times to make an average number. Also repeats query
to compare unique vs cached query times.

Note: if Solr has been dormant for a while it will be slow to respond at first.
This test should be run several times to determine "start up" performance vs
"warmed up" performance.

Assumptions: the astronomically low probably of a repeat (1 out of 5^975)
renders the random phrases virtually unique within a typical query cache lifetime.

### Usage

```
python3 check-solr.py PROD
```

## check-fedora.py

Measure Fedora object retreval response times. 
Keeps track of previous requests to avoid repeats. Minimum time elapsed before
accessing the same url can be set with MIN_OBJECT_URL_STALENESS in the code.

### Usage

```
python3 check-fedora.py PROD
```

## Server configurations
Server configurations are located in `compass.cfg`. Edit this file as needed. When running the commands you must specify a server config. E.g. 'PROD' or 'STAGE'.
