#!/usr/bin/env python2

#
# TODO:
# * Metadata?  e.g. comments with "**Labels:** EasyToFix" only?
# * add attachments for issue body?
#

from __future__ import print_function

import json
import csv
import optparse
import re
import os
import sys
import urllib2

from datetime import datetime
from time import time
from pyquery import PyQuery as pq

# The maximum number of records to retrieve from Google Code in a single request

GOOGLE_MAX_RESULTS = 25

GOOGLE_ISSUE_TEMPLATE = '_Original issue: {}_'
GOOGLE_ISSUES_URL = 'https://code.google.com/p/{}/issues/csv?can=1&num={}&start={}&colspec=ID%20Type%20Status%20Owner%20Summary%20Opened%20Closed%20Reporter&sort=id'
GOOGLE_URL = 'http://code.google.com/p/{}/issues/detail?id={}'
GOOGLE_URL_RE = 'http://code.google.com/p/%s/issues/detail\?id=(\d+)'
GOOGLE_ID_RE = GOOGLE_ISSUE_TEMPLATE.format(GOOGLE_URL_RE)

# Mapping from Google Code issue labels to Github labels

LABEL_MAPPING = {
    'Type-Defect' : 'bug',
    'Type-Enhancement' : 'enhancement'
}

# Mapping from Google Code issue states to Github labels

STATE_MAPPING = {
    'invalid': 'invalid',
    'duplicate': 'duplicate',
    'wontfix': 'wontfix'
}

def output(string):
    sys.stdout.write(string)
    sys.stdout.flush()


def parse_gcode_date(date_text):
    """ Transforms a Google Code date into a more human readable string. """

    try:
        parsed = datetime.strptime(date_text, '%a %b %d %H:%M:%S %Y').isoformat()
        return parsed + "Z"
    except ValueError:
        return date_text


def gt(dt_str):
    return datetime.strptime(dt_str.rstrip("Z"), "%Y-%m-%dT%H:%M:%S")


def valid_email(s):
    email = re.sub(r'^https:\/\/code\.google\.com\/u\/([^/]+)\/$', r'\1', s)
    try:
        int(email)
    except ValueError:
        if re.match(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4}$', email):
            return email
    return ''


def get_gc_issue(s):
    reg = [ r'^.*\*\*Blockedon:\*\* ([0-9]{1,4}) .*$',
            r'^.*\*\*Blocking:\*\* ([0-9]{1,4}) .*$',
            r'^.*\*\*Blocking:\*\* ' + google_project_name + r':([0-9]{1,4}) .*$',
            r'^.*\*\*Blockedon:\*\* ' + google_project_name + r':([0-9]{1,4}) .*$', ]
    n = set()
    for r in reg:
        s1 = re.sub(r, r'\1', s, flags=re.DOTALL)
        try:
            i = int(s1)
            n.add(i)
        except ValueError:
            pass
    for i in set(re.findall(r'issue [0-9]+', s, re.DOTALL)):
        s1 = re.sub(r'issue ([0-9]+)', r'\1', i)
        n.add(int(s1))
    return n


def add_issue_to_github(issue):
    """ Migrates the given Google Code issue to Github. """

    # Github rate-limits API requests to 5000 per hour, and if we hit that limit part-way
    # through adding an issue it could end up in an incomplete state.  To avoid this we'll
    # ensure that there are enough requests remaining before we start migrating an issue.

    gid = issue['gid']
    gid += (options.issues_start_from - 1)

    output('Adding issue %d' % gid)

    issue['number'] = gid
    del issue['gid']
    try:
        issue['milestone'] += (options.milestones_start_from - 1)
    except KeyError:
        pass
    issue['title'] = issue['title'].strip()
    if not issue['title']:
        issue['title'] = "FIXME: empty title"
    comments = issue['comments']
    del issue['comments']
    issue['created_at'] = issue['date']
    del issue['date']
    del issue['status']
    try:
        del issue['Cc']
    except KeyError:
        pass
    try:
        if issue['owner']:
            issue['assignee'] = issue['owner']
        del issue['owner']
    except KeyError:
        pass
    updated_at = datetime.fromtimestamp(int(time())).isoformat() + "Z"
    issue['updated_at'] = updated_at

    markdown_date = gt('2009-04-20T19:00:00Z')
    # markdown:
    #    http://daringfireball.net/projects/markdown/syntax
    #    http://github.github.com/github-flavored-markdown/
    # vs textile:
    #    http://txstyle.org/article/44/an-overview-of-the-textile-syntax

    idx = get_gc_issue(issue['body'])

    if len(issue['body']) >= 65534:
        issue['body'] = "FIXME: too long issue body"
        output("FIXME: issue %d - too long body" % gid)

    body = ""
    for i in issue['body']:
        if i >= u"\uffff":
            body += "FIXME: unicode %s" % hex(ord(i))
        else:
            body += i
    issue['body'] = body

    try:
        oid = issue['orig_owner']
        del issue['orig_owner']
    except KeyError:
        oid = None

    if gt(issue['created_at']) >= markdown_date:
        issue['body'] = ("```\r\n" + issue['body'] +
                         "\r\n```\r\n" +
                         "_Original issue for #" + str(gid) + ": " +
                         issue['link'] + "_\r\n" +
                         "_Original author: " + issue['orig_user'] + "_\r\n")
        if idx:
            issue['body'] += ("_Referenced issues: " +
                              ", ".join("#" + str(i) for i in idx) + "._\r\n")
        if oid:
            issue['body'] += ("_Original owner: " + oid + "_\r\n")
    else:
        issue['body'] = ("bc.. " + issue['body'] + "\r\n\r\n" +
                         "p. _Original issue for #" + str(gid) + ":_ " +
                         '"_' + issue['link'] + '_":' +
                         issue['link'] + "\r\n\r\n" +
                         "p. _Original author:_ " + '"_' + issue['orig_user'] +
                         '_":' + issue['orig_user'] + "\r\n")
        if idx:
            issue['body'] += ("\r\np. _Referenced issues: " +
                              ", ".join("#" + str(i) for i in idx) + "._\r\n")
        if oid:
            issue['body'] += ("\r\np. _Original owner:_ " +
                              '"_' + oid + '_":' + oid + "\r\n")
    del issue['orig_user']
    del issue['link']

    with open("issues/" + str(issue['number']) + ".json", "w") as f:
        f.write(json.dumps(issue, indent=4, separators=(',', ': '), sort_keys=True))
        f.write('\n')

    with open("issues/" + str(issue['number']) + ".comments.json", "w") as f:
        comments_fixed = list(comments)
        for i, c in enumerate(comments):
            c['created_at'] = c['date']
            del c['date']
            c['updated_at'] = updated_at
            idx = get_gc_issue(c['body'])

            body = ""
            for i in c['body']:
                if i >= u"\uffff":
                    body += "FIXME: unicode %s" % hex(ord(i))
                else:
                    body += i
            c['body'] = body

            if len(c['body']) >= 65534:
                c['body'] = "FIXME: too long comment body"
                output("FIXME: issue %d, comment %d - too long body" % (gid, i + 1))

            if gt(c['created_at']) >= markdown_date:
                c['body'] = "```\r\n" + c['body'] + "\r\n```\r\n"
                if idx:
                    c['body'] += ("_Referenced issues: " +
                                  ", ".join("#" + str(i) for i in idx) + "._\r\n")
                c['body'] += ("_Original comment: " + c['link'] + "_\r\n")
                c['body'] += ("_Original author: " + c['orig_user'] + "_\r\n")
            else:
                c['body'] = "bc.. " + c['body'] + "\r\n"
                if idx:
                    c['body'] += ("\r\np. _Referenced issues: " +
                                  ", ".join("#" + str(i) for i in idx) + "._\r\n")
                c['body'] += ("\r\np. _Original comment:_ " + '"_' + c['link'] +
                              '_":' + c['link'] + "\r\n")
                c['body'] += ("\r\np. _Original author:_ " + '"_' + c['orig_user'] +
                              '_":' + c['orig_user'] + "\r\n")
            del c['link']
            del c['orig_user']

        comments = comments_fixed

        f.write(json.dumps(comments, indent=4, separators=(',', ': '), sort_keys=True))
        f.write('\n')


def get_attachments(link, attachments):
    if not attachments:
        return ''

    body = '\n\n'
    for attachment in (pq(a) for a in attachments):
        if not attachment('a'): # Skip deleted attachments
            continue

        # Linking to the comment with the attachment rather than the
        # attachment itself since Google Code uses download tokens for
        # attachments
        body += '**Attachment:** [{}]({})'.format(attachment('b').text().encode('utf-8'), link)
    return body


def get_gcode_issue(issue_summary):
    # Populate properties available from the summary CSV
    issue = {
        'gid': int(issue_summary['ID']),
        'title': issue_summary['Summary'].replace('%', '&#37;'),
        'link': GOOGLE_URL.format(google_project_name, issue_summary['ID']),
        'owner': issue_summary['Owner'],
        'state': 'closed' if issue_summary['Closed'] else 'open',
        'date': datetime.fromtimestamp(float(issue_summary['OpenedTimestamp'])).isoformat() + "Z",
        'status': issue_summary['Status'].lower()
    }

    global mnum
    global milestones

    ms = ''

    # Build a list of labels to apply to the new issue, including an 'imported' tag that
    # we can use to identify this issue as one that's passed through migration.
    labels = ['imported']
    for label in issue_summary['AllLabels'].split(', '):
        if label.startswith('Priority-') and options.omit_priority:
            continue
        if label.startswith('Milestone-'):
            ms = label[10:]
            continue
        if not label:
            continue
        labels.append(LABEL_MAPPING.get(label, label))

        if ms:
            try:
                milestones[ms]
            except KeyError:
                milestones[ms] = {'number': mnum,
                                  'state': 'open',
                                  'title': ms,
                                  'created_at': issue['date']
                                  }
                mnum+=1
            issue['milestone'] = milestones[ms]['number']

    # Add additional labels based on the issue's state
    if issue['status'] in STATE_MAPPING:
        labels.append(STATE_MAPPING[issue['status']])

    issue['labels'] = labels

    # Scrape the issue details page for the issue body and comments
    opener = urllib2.build_opener()
    doc = pq(opener.open(issue['link']).read())

    description = doc('.issuedescription .issuedescription')
    tmp = description('.userlink').attr('href')
    if tmp:
        uid = 'https://code.google.com{}'.format(tmp)
    else:
        uid = description('.userlink').contents()[0]
    try:
        authors[uid]
    except KeyError:
        authors[uid] = valid_email(uid)
    user = authors[uid]
    if user:
        issue['user'] = {'email': user}
    issue['orig_user'] = uid

    # Handle Owner and Cc fields...

    for tr in doc('div[id="meta-float"]')('tr'):
        if pq(tr)('th').filter(lambda i, this: pq(this).text() == 'Owner:'):
            tmp = pq(tr)('.userlink')
            for owner in tmp:
                tmp = pq(owner).attr('href')
                if tmp:
                    oid = 'https://code.google.com{}'.format(tmp)
                else:
                    oid = pq(owner).contents()[0]
                if oid:
                    try:
                        authors[oid]
                    except KeyError:
                        authors[oid] = valid_email(oid)
                    owner = authors[oid]
                    if owner:
                        issue['owner'] = {'email': owner}
                    issue['orig_owner'] = oid
                    break # only one owner
            break

    for tr in doc('div[id="meta-float"]')('tr'):
        if pq(tr)('th').filter(lambda i, this: pq(this).text() == 'Cc:'):
            tmp = pq(tr)('.userlink')
            if tmp:
                issue['Cc'] = []
            for cc in tmp:
                tmp = pq(cc).attr('href')
                if tmp:
                    cid = 'https://code.google.com{}'.format(tmp)
                else:
                    cid = pq(cc).contents()[0]
                if cid:
                    try:
                        authors[cid]
                    except KeyError:
                        authors[cid] = valid_email(cid)
                    cc = authors[cid]
                    if cc:
                        issue['Cc'].append({'email': cc})
            break

    issue['body'] = description('pre').text()

    issue['comments'] = []
    for comment in doc('.issuecomment'):
        comment = pq(comment)
        if not comment('.date'):
            continue # Sign in prompt line uses same class
        if comment.hasClass('delcom'):
            continue # Skip deleted comments

        date = parse_gcode_date(comment('.date').attr('title'))
        try:
            body = comment('pre').text()
        except UnicodeDecodeError:
            body = u'FIXME: UnicodeDecodeError'

        tmp = comment('.userlink').attr('href')
        if tmp:
            uid = 'https://code.google.com{}'.format(tmp)
        else:
            uid = comment('.userlink').contents()[0]
        try:
            authors[uid]
        except KeyError:
            authors[uid] = valid_email(uid)
        if user:
            user = authors[uid]

        updates = comment('.updates .box-inner')
        if updates:
            body += '\n\n' + updates.html().strip().replace('\n', '').replace('<b>', '**').replace('</b>', '**').replace('<br/>', '\n')

#       # TODO: support attachments
#       try:
#           body += get_attachments('{}#{}'.format(issue['link'], comment.attr('id')), comment('.attachments'))
#       except UnicodeDecodeError:
#           body += u'FIXME: UnicodeDecodeError in updates'

        # Strip the placeholder text if there's any other updates
        body = body.replace('(No comment was entered for this change.)\n\n', '')

        if body.find('**Status:** Fixed') >= 0:
            issue['closed_at'] = date

        c = { 'date': date,
              'user': {'email': user},
              'body': body,
              'link': issue['link'] + '#c' + str(len(issue['comments']) + 1),
              'orig_user': uid
            }
        issue['comments'].append(c)

    return issue

def get_gcode_issues():
    count = 100
    start_index = 0
    issues = []
    while True:
        url = GOOGLE_ISSUES_URL.format(google_project_name, count, start_index)
        issues.extend(row for row in csv.DictReader(urllib2.urlopen(url), dialect=csv.excel))

        if issues and 'truncated' in issues[-1]['ID']:
            issues.pop()
            start_index += count
        else:
            return issues


def process_gcode_issues():
    """ Migrates all Google Code issues in the given dictionary to Github. """

    issues = get_gcode_issues()
    previous_gid = 1

    if options.start_at is not None:
        issues = [x for x in issues if int(x['ID']) >= options.start_at]
        previous_gid = options.start_at - 1
        output('Starting at issue %d\n' % options.start_at)

    if options.end_at is not None:
        issues = [x for x in issues if int(x['ID']) <= options.end_at]
        output('End at issue %d\n' % options.end_at)

    for issue in issues:
        issue = get_gcode_issue(issue)

        if options.skip_closed and (issue['state'] == 'closed'):
            continue

        add_issue_to_github(issue)

        output('\n')

    if milestones:
        for m in milestones.values():
            m['number'] += (options.milestones_start_from - 1)
            with open('milestones/' + str(m['number']) + '.json', 'w') as f:
                f.write(json.dumps(m, indent=4, separators=(',', ': '), sort_keys=True))
                f.write('\n')


if __name__ == "__main__":
    usage = "usage: %prog [options] <google project name>"
    description = "Export all issues from a Google Code project for a Github project."
    parser = optparse.OptionParser(usage = usage, description = description)

    parser.add_option("-p", "--omit-priority", action = "store_true", dest = "omit_priority",
                      help = "Don't migrate priority labels", default = False)
    parser.add_option('--skip-closed', action = 'store_true', dest = 'skip_closed', help = 'Skip all closed bugs', default = False)
    parser.add_option('--start-at', dest = 'start_at', help = 'Start at the given Google Code issue number', default = None, type = int)
    parser.add_option('--end-at', dest = 'end_at', help = 'End at the given Google Code issue number', default = None, type = int)
    parser.add_option('--issues-start-from', dest = 'issues_start_from', help = 'First issue number', default = 1, type = int)
    parser.add_option('--milestones-start-from', dest = 'milestones_start_from', help = 'First milestone number', default = 1, type = int)

    options, args = parser.parse_args()

    if len(args) != 1:
        parser.print_help()
        sys.exit()

    google_project_name = args[0]

    try:
        with open("authors.json", "r") as f:
            authors = json.load(f)
    except IOError:
        authors = {}

    authors_orig = authors.copy()
    milestones = {}
    mnum = 1

    if not os.path.exists('issues'):
        os.mkdir('issues')

    if not os.path.exists('milestones'):
        os.mkdir('milestones')

    try:
        process_gcode_issues()
    except Exception:
        parser.print_help()
        raise

    for k, v in authors.items():
        if k not in authors_orig.keys():
            output('NEW AUTHOR %s: %s\n' % (k, v))

    if authors != authors_orig:
        with open("authors.json-new", "w") as f:
            f.write(json.dumps(authors, indent=4,
                               separators=(',', ': '), sort_keys=True))
            f.write('\n')
