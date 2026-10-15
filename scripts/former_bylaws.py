"""Fetch the text of Pickering's former parent zoning by-laws from the City's Laserfiche archive.

By-law 8149/24 supersedes By-laws 2511, 2520, 3036 and 3037 but keeps them in effect for the
exception zones carried forward from them (Section 16.2.1): an exception that changes one yard
leaves the rest to its parent zone in the former by-law. The City publishes those by-laws only
as scans in its archive (corporate.pickering.ca/WebLink), which also serves each page's
recognised text; this stores that text page by page, and scripts/zone_rules.py reads it.

    python scripts/former_bylaws.py --store data/municipal/pickering
"""
import argparse
import datetime as dt
import http.cookiejar
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

WEBLINK = 'https://corporate.pickering.ca/WebLink'
REPO = 'PICKERING'
FORMER = ('2511', '2520', '3036', '3037')
USER_AGENT = 'Mozilla/5.0 EnerZen-municipal-data (zoning research)'


class Archive:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.opener.addheaders = [('User-Agent', USER_AGENT)]
        self.opener.open(f'{WEBLINK}/Browse.aspx?dbid=1&repo={REPO}', timeout=60).read()

    def call(self, service: str, method: str, **args):
        req = urllib.request.Request(f'{WEBLINK}/{service}.aspx/{method}', json.dumps(args).encode(),
                                     {'Content-Type': 'application/json', 'X-Lf-Suppress-Login-Redirect': '1'})
        for attempt in range(3):
            try:
                return json.load(self.opener.open(req, timeout=60))['data']
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(5 * (attempt + 1))

    def folder(self, folder_id: int) -> list[dict]:
        return self.call('FolderListingService', 'GetFolderListing2', repoName=REPO, folderId=folder_id,
                         getNewListing=True, start=0, end=1000, sortColumn='', sortAscending=True)['results']

    def find(self, numbers) -> dict:
        """{number: entry id}, walking By-laws > 1960 to 1969 > each year for "By-law 2511 - Zoning"."""
        child = lambda fid, pattern: next((r['entryId'] for r in self.folder(fid) if re.search(pattern, r['name'], re.I)), None)
        bylaws = child(child(1, r'by-?law') or 1, r'^by-?laws$')
        found = {}
        for decade in (r['entryId'] for r in self.folder(bylaws) if re.match(r'19[56]0 to', r['name'])):
            for year in self.folder(decade):
                for entry in self.folder(year['entryId']):
                    m = re.match(r'By-?law (\d+)\b', entry['name'])
                    if m and m.group(1) in numbers:
                        found.setdefault(m.group(1), {'id': entry['entryId'], 'title': entry['name']})
        return found


def scrape(store: Path, log=print) -> dict:
    archive = Archive()
    folder = store / 'former_bylaws'
    folder.mkdir(parents=True, exist_ok=True)
    index, errors = {}, []
    for number, entry in archive.find(FORMER).items():
        try:
            count = archive.call('DocumentService', 'GetBasicDocumentInfo', repoName=REPO, entryId=entry['id'])['pageCount']
            pages = []
            for page in range(1, count + 1):
                pages.append(archive.call('DocumentService', 'GetTextHtmlForPage', repoName=REPO, documentId=entry['id'],
                                          pageNum=page, showAnn=False, searchUuid=None)['text'])
                time.sleep(0.3)  # the archive is the City's public service; one page at a time
            file = f'former_bylaws/{number}.pages.json'
            (store / file).write_text(json.dumps(pages), encoding='utf-8')
            index[number] = {'title': entry['title'], 'document': f'By-law {number} (former parent by-law)',
                             'url': f'{WEBLINK}/DocView.aspx?id={entry["id"]}&dbid=1&repo={REPO}',
                             'text_file': file, 'pages': count, 'pages_with_text': sum(1 for t in pages if t.strip())}
            log(f'{number}: {count} pages')
        except Exception as exc:
            errors.append({'bylaw': number, 'error': repr(exc)})
    missing = sorted(set(FORMER) - set(index))
    result = {'retrieved_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'bylaws': index,
              'missing': missing, 'errors': errors}
    if index:  # a failed run keeps the last good copy
        (store / 'former_bylaws.json').write_text(json.dumps(result, indent=1), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--store', type=Path, default=Path(__file__).resolve().parent.parent / 'data' / 'municipal' / 'pickering')
    result = scrape(parser.parse_args().store)
    print(json.dumps({k: v for k, v in result.items() if k != 'bylaws'} | {'bylaws': list(result['bylaws'])}, indent=1))
    sys.exit(0 if not result['missing'] else 2)
