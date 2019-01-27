#! /usr/bin/env python3

#
# deduplicate muxes in tvheadend
# requires python 3
#

import os
import sys
import json
import traceback
import urllib.request as urllib
from urllib.parse import urlencode, quote
from datetime import datetime
from operator import itemgetter

def env(key, deflt):
    if key in os.environ: return os.environ[key]
    return deflt

DEBUG=False
DRYRUN=True

TVH_API=env('TVH_API_URL', 'http://localhost:9981/api')
TVH_USER=env('TVH_USER', None)
TVH_PASS=env('TVH_PASS', None)
TVH_AUTH=env('TVH_AUTH', 'digest')
PWD_MGR = urllib.HTTPPasswordMgrWithDefaultRealm()
PWD_MGR.add_password(None, TVH_API, TVH_USER, TVH_PASS)

class Response(object):
    def __init__(self, response):
        self.url = response.geturl()
        self.code = response.getcode()
        self.reason = response.msg
        self.headers = response.info()
        self.body = None
        self.ctype = None
        if 'Content-type' in self.headers:
            self.ctype = self.headers['Content-type'].split(';')[0]
            if self.ctype in ['text/x-json', 'application/json']:
                self.body = json.loads(response.read().decode('utf-8'))
        if not self.body:
          self.body = response.read()

def error(lvl, msg, *args):
    sys.stderr.write(msg % args + '\n')
    sys.exit(lvl)

class TVHeadend(object):

    def __init__(self, path, headers=None):
        self._headers = headers or {}
        self._path = path or []

    def opener(self):
        handlers = []
        if TVH_AUTH == 'digest':
            handlers.append(urllib.HTTPDigestAuthHandler(PWD_MGR))
        elif TVH_AUTH == 'basic':
            handlers.append(urllib.HTTPBasicAuthHandler(PWD_MGR))
        else:
            handlers.append(urllib.HTTPDigestAuthHandler(PWD_MGR))
            handlers.append(urllib.HTTPBasicAuthHandler(PWD_MGR))
        if DEBUG:
            handlers.append(urllib.HTTPSHandler(debuglevel=1))
        return urllib.build_opener(*handlers)

    def _push(self, data, binary=None, method='PUT'):
        content_type = None
        if binary:
          content_type = 'application/binary'
        else:
          data = data and urlencode(data).encode('utf-8') or None
        opener = self.opener()
        path = self._path
        if path[0] != '/': path = '/' + path
        request = urllib.Request(TVH_API + path, data=data)
        if content_type:
            request.add_header('Content-Type', content_type)
        request.get_method = lambda: method
        try:
            r = Response(opener.open(request))
        except urllib.HTTPError as e:
            r = Response(e)
        return r

    def get(self, binary=None):
        return self._push(None, method='GET')

    def post(self, data):
        return self._push(data, method='POST')

def do_get0(*args):
    if len(args) < 1: error(1, 'get [path] [json_query]')
    path = args[0]
    query = None
    if len(args) > 1:
        query = args[1]
        if type(query) != type({}):
            query = json.loads(query.decode('utf-8'))
    if query:
        for q in query:
            r = query[q]
            if type(r) == type({}) or type(r) == type([]):
                query[q] = json.dumps(r)
    resp = TVHeadend(path).post(query)
    if resp.code != 200 and resp.code != 201:
        error(10, 'HTTP ERROR "%s" %s %s', resp.url, resp.code, resp.reason)
    return resp.body

def format_date(ts):
    if ts == 0:
        return 'never'
    else:
        return (datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S'))

def delete_mux(uuid):
    body = do_get0('idnode/delete', {'uuid': uuid})
    if body and type(body) != type({}):
        error(11, 'Unknown data / response')

def update_mux(mux):
    body = do_get0('raw/import', {'node': mux})
    if body and type(body) != type({}):
        error(11, 'Unknown data / response')

def do_dedup(*args):

    # fields that must be exactly the same to be considered a dup
    dupkeys     = ['orbital','polarisation']
    # fields that may be missing in a mux
    missingkeys = ['cridauth','pnetwork_name','epg_module_id']
    # fields that should never be copied
    nocopykeys  = ['uuid', 'services','scan_result','epg_module_id']
    # fields that should be formatted as dates
    datekeys    = ['created','scan_first','scan_last']
    # datekeys should not be copied too
    nocopykeys.extend(datekeys)
    # list of possible scan results
    scanresults =  ['NONE', 'OK', 'FAIL', 'PARTIAL', 'IGNORE']

    # get all the services that are mapped to channels
    channels = do_get0('raw/export', {'class':'channel'})
    mappedservices = []
    for channel in channels:
        mappedservices.extend(channel['services'])

    # get the service name for every mapped services
    channelnames = []
    for service in do_get0('raw/export', {'class':'service'}):
        if service['uuid'] in mappedservices:
            channelnames.append({'uuid': service['uuid'], 'svcname': service['svcname']})

    # get a sorted list of muxes
    muxes = sorted(do_get0('raw/export', {'class':'dvb_mux_dvbs'}), key=itemgetter('orbital', 'frequency')) 
    nmuxes = len(muxes)

    # add missing fields in muxes
    for mux in muxes:
        for missingkey in missingkeys:
            if not missingkey in mux:
                mux[missingkey] = u''

    # find duplicate muxes
    modmuxes = []
    ndups = 0
    for i in range(nmuxes):
        for j in range(i+1, nmuxes):
            thismux = muxes[i]
            thatmux = muxes[j]
            isdup = True
            for key in dupkeys:
                if thismux[key] != thatmux[key]:
                    isdup = False
                    break
            if abs(thismux['frequency'] - thatmux['frequency']) >= 1000:
                    isdup = False

            if isdup:
                ndups += 1
                docopy = True
                print('dup #{}: {} {}{}'.format(ndups, thismux['orbital'], int(round(thismux['frequency'] / 1000, 0)), thismux['polarisation']))

                # find best mux of a duplicate pair, assuming newest is best
                if thismux['created'] > thatmux['created']:
                    newermux = thismux
                    oldermux = thatmux
                elif thismux['created'] < thatmux['created']:
                    newermux = thatmux
                    oldermux = thismux
                elif thismux['scan_first'] > thatmux['scan_first']:
                    newermux = thismux
                    oldermux = thatmux
                elif thismux['scan_first'] < thatmux['scan_first']:
                    newermux = thatmux
                    oldermux = thismux
                elif thismux['scan_last'] > thatmux['scan_last']:
                    newermux = thismux
                    oldermux = thatmux
                elif thismux['scan_last'] < thatmux['scan_last']:
                    newermux = thatmux
                    oldermux = thismux
                # bail out if all dates are the same
                else:
                    print('all dates identical')
                    newermux = thismux
                    oldermux = thatmux
                    docopy = False

                # bail out if best mux is not OK
                if newermux['scan_result'] != 1:
                    print('newer mux is not OK')
                    docopy = False

                # texts
                if DRYRUN:
                    mod = 'would modify'
                    notmod = 'would not modify'
                    upd = 'would update'
                    dlt = 'would delete'
                else:
                    mod = 'modifying'
                    notmod = 'not modifying'
                    upd = 'updating'
                    dlt = 'deleting'

                # show the dup muxes side by side, pretty printed
                fmt = '{:14}: {:<32} {:<32}'
                print(fmt.format('', 'newer mux', 'older mux'))
                key = 'uuid'
                print(fmt.format(key, newermux[key], oldermux[key]))
                key= 'scan_result'
                print(fmt.format(key, scanresults[newermux[key]], scanresults[oldermux[key]]))
                key = 'services'
                print(fmt.format(key, len(newermux[key]), len(oldermux[key])))
                newermappings = len(set(newermux[key]) & set(mappedservices))
                oldermappings = len(set(oldermux[key]) & set(mappedservices))
                print(fmt.format('mappings', newermappings, oldermappings))
                for key in datekeys:
                    print(fmt.format(key, format_date(newermux[key]), format_date(oldermux[key])))

                # show the differences
                nupdates = 0
                for key, newervalue in newermux.items():
                    if key in nocopykeys:
                        continue
                    oldervalue = oldermux[key]
                    if type(newervalue) == bytes:
                        newervalue = newervalue.encode('utf-8')
                        oldervalue = oldervalue.encode('utf-8')
                    if newervalue != oldervalue:
                        print(fmt.format(key, newervalue, oldervalue))
                        if docopy and key not in nocopykeys:
                            oldermux[key] = newermux[key]
                            nupdates += 1

                # show the channels mapped to the mux, by service name
                for mux in [newermux,oldermux]:
                    for service in mux['services']:
                        for channelname in channelnames:
                            if channelname['uuid'] == service:
                                svcname = channelname['svcname']
                                if mux == newermux:
                                    print(fmt.format('channel', svcname, ''))
                                else:
                                    print(fmt.format('channel', '', svcname))

                # skip a duplicate set if either mux was previously modified or deleted
                neweruuid = newermux['uuid']
                olderuuid = oldermux['uuid']
                if neweruuid in modmuxes:
                    print('mux {} is already modified or deleted'.format(neweruuid))
                elif olderuuid in modmuxes:
                    print('mux {} is already modified or deleted'.format(olderuuid))
                else:
                    if docopy and oldermappings == 0:
                        # older mux has no mappings, so just delete it
                        modmuxes.append(olderuuid)
                        print('{} mux {}'.format(dlt, olderuuid))
                        if not DRYRUN:
                            delete_mux(olderuuid)
                    elif docopy and nupdates > 0:
                        # save parameters that were copied from newer mux to older mux
                        modmuxes.append(olderuuid)
                        print('{} mux {}'.format(upd, olderuuid))
                        if not DRYRUN:
                            update_mux(oldermux)
                        # then delete the newer mux, unless it has channel mappings too
                        if newermappings == 0:
                            modmuxes.append(neweruuid)
                            print('{} mux {}'.format(dlt, neweruuid))
                            if not DRYRUN:
                                delete_mux(neweruuid)
                    elif newermappings == 0 and newermux['scan_result'] == 2:
                        # always delete the newer mux if it is bad
                        modmuxes.append(neweruuid)
                        print('{} mux {}'.format(dlt, neweruuid))
                        if not DRYRUN:
                            delete_mux(neweruuid)

                print()

def main(argv):
    global DEBUG
    global DRYRUN
    if not TVH_USER or not TVH_PASS:
        error(2, 'No credentials')
    for arg in argv:
        if arg == '--debug':
            DEBUG = True
        if arg in ['--no-dry-run','--nodryrun']:
            DRYRUN = False
    do_dedup()

if __name__ == "__main__":
    main(sys.argv)
