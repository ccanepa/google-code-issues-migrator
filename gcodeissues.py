import csv
from datetime import datetime
import os
import sys
import urllib2

from pyquery import PyQuery as pq


# The maximum number of records to retrieve from Google Code in a single request
GOOGLE_MAX_RESULTS = 25

GOOGLE_ISSUES_URL = 'https://code.google.com/p/{0}/issues/csv?can=1&num={1}&start={2}&colspec=ID%20Type%20Status%20Owner%20Summary%20Opened%20Closed%20Reporter&sort=id'
GOOGLE_URL = 'http://code.google.com/p/{0}/issues/detail?id={1}'

EXPORTED_OP_FORMAT_TEMPLATE = u"""
_From {author} on {date:%B %d, %Y %H:%M:%S}_

{content}{attachments}

_Original issue: {footer}_
"""

EXPORTED_COMMENT_FORMAT_TEMPLATE = u"""
"""

def gcode_issues_index(google_project_name):
    """
    Returns a list with all the issues (in short form) found in googlecode 
    This gets only a short version of each issue, like seen in the index pages
    for googlecode issues

    Each short_issue is a dict.
    Key and values are utf-8 encoded.
    Which fields are retrieved ts programable by GOOGLE_ISSUES_URL
    A visual inspection of the web page shows that some of the available fields
    are
        ID
        Type
        Priority
        Milestone
        Owner
        Summary
        Component        
        Status
        Attachments (number of attachments)
        Stars
        Opened
        Closed
        Modified
        BlockedOn
        Blocking
        Blocked
        MergedInto
        Reporter
        Cc
        Project
        Opsys

    An example for los-cocos project is
        {'Status': 'Invalid',
         'AllLabels': 'Priority-Medium, Type-Defect', # string with list of labels
         'OpenedTimestamp': '1206123873',
         'Opened': 'Mar 21, 2008 18:24:33',
         'Reporter': 'facundob...@gmail.com',
         'Summary': 'director is not pythonically imported',
         'Closed': 'Mar 21, 2008 21:45:15',
         'Owner': '',
         'Type': 'Defect',
         'ID': '9',
         'ClosedTimestamp': '1206135915'
         }

    """
    count = 100
    start_index = 0
    short_issues = []
    while True:
        url = GOOGLE_ISSUES_URL.format(google_project_name, count, start_index)
        short_issues.extend(row for row in csv.DictReader(urllib2.urlopen(url),
                                                          dialect=csv.excel))

        if 0:  ## DEBUG short_issues and b'truncated' in short_issues[-1][b'ID']:
            short_issues.pop()
            start_index += count
        else:
            break
    return short_issues


def get_attachments(link, attachments):
    if not attachments:
        return ''

    body = u'\n\n'
    for attachment in (pq(a) for a in attachments):
        if not attachment('a'): # Skip deleted attachments
            continue

        # Linking to the comment with the attachment rather than the
        # attachment itself since Google Code uses download tokens for
        # attachments
        body += u'**Attachment:** [{}]({})'.format(attachment('b').text(), link)
    return body


def parse_gcode_date(date_text):
    """ Transforms a Google Code date into a more human readable string. """

    try:
        parsed = datetime.strptime(date_text, '%a %b %d %H:%M:%S %Y')
    except ValueError:
        return date_text

    return parsed.strftime("%B %d, %Y %H:%M:%S")


def get_gcode_issue_new(google_project_name, short_issue):
    def get_author(doc):
        userlink = doc('.userlink')
        return '[{0}](https://code.google.com{1})'.format(userlink.text(), userlink.attr('href'))

    # Populate properties available from the summary CSV
    issue = {
        'gid': int(short_issue[b'ID']),
        'title': short_issue['Summary'].replace('%', '&#37;'),
        'link': GOOGLE_URL.format(google_project_name, short_issue[b'ID']),
        'owner': short_issue[b'Owner'],
        'state': 'closed' if short_issue[b'Closed'] else 'open',
        'date': datetime.fromtimestamp(float(short_issue[b'OpenedTimestamp'])),
        'status': short_issue[b'Status'].lower()
    }

    # Scrape the issue details page for the issue body and comments
    opener = urllib2.build_opener()
    doc = pq(opener.open(issue['link']).read())
    description = doc('.issuedescription .issuedescription')
    issue['author'] = get_author(description)
    issue['content'] = description('pre').text()  # -> explorando en drampie esto es unicode

    for comment in doc('.issuecomment'):
        comment = pq(comment)
        if not comment('.date'):
            continue  # Sign in prompt line uses same class
        if comment.hasClass('delcom'):
            continue  # Skip deleted comments

        date = parse_gcode_date(comment('.date').attr('title'))
        body = comment('pre').text()
        author = get_author(comment)

        updates = comment('.updates .box-inner')
        if updates:
            body += '\n\n' + updates.html().strip().replace('\n', '').replace('<b>', '**').replace('</b>', '**').replace('<br/>', '\n')

        body += get_attachments('{0}#{1}'.format(issue['link'], comment.attr('id')), comment('.attachments'))

        # Strip the placeholder text if there's any other updates
        body = body.replace('(No comment was entered for this change.)\n\n', '')

def get_doc(short_issue):
    google_project_name = 'los-cocos'
    def get_author(doc):
        userlink = doc('.userlink')
        return '[{0}](https://code.google.com{1})'.format(userlink.text(), userlink.attr('href'))

    # Populate properties available from the summary CSV
    issue = {
        'gid': int(short_issue[b'ID']),
        'title': short_issue['Summary'].replace('%', '&#37;'),
        'link': GOOGLE_URL.format(google_project_name, short_issue[b'ID']),
        'owner': short_issue[b'Owner'],
        'state': 'closed' if short_issue[b'Closed'] else 'open',
        'date': datetime.fromtimestamp(float(short_issue[b'OpenedTimestamp'])),
        'status': short_issue[b'Status'].lower()
    }

    # Scrape the issue details page for the issue body and comments
    opener = urllib2.build_opener()
    # this no loner works, now there's a captcha to access email of posters
    ##if options.google_code_cookie:
    ##    opener.addheaders = [('Cookie', options.google_code_cookie)]

    doc = pq(opener.open(issue['link']).read())
    return issue, doc

def get_gcode_issue(google_project_name, short_issue):
    def get_author(doc):
        userlink = doc('.userlink')
        return '[{0}](https://code.google.com{1})'.format(userlink.text(), userlink.attr('href'))

    # Populate properties available from the summary CSV
    issue = {
        'gid': int(short_issue[b'ID']),
        'title': short_issue['Summary'].replace('%', '&#37;'),
        'link': GOOGLE_URL.format(google_project_name, short_issue[b'ID']),
        'owner': short_issue[b'Owner'],
        'state': 'closed' if short_issue[b'Closed'] else 'open',
        'date': datetime.fromtimestamp(float(short_issue[b'OpenedTimestamp'])),
        'status': short_issue[b'Status'].lower()
    }

    # Scrape the issue details page for the issue body and comments
    opener = urllib2.build_opener()
    doc = pq(opener.open(issue['link']).read())
    description = doc('.issuedescription .issuedescription')
    issue['author'] = get_author(description)

    issue['comments'] = []

    def split_comment(comment, text):
        # Github has an undocumented maximum comment size (unless I just failed
        # to find where it was documented), so split comments up into multiple
        # posts as needed.
        while text:
            comment['body'] = text[:7000]
            text = text[7000:]
            if text:
                comment['body'] += '...'
                text = '...' + text
            issue['comments'].append(comment.copy())

    split_comment(issue, description('pre').text())
    content = issue['comments'].pop(0)['body']
    footer = GOOGLE_URL.format(google_project_name, issue['gid'])
    attachments = get_attachments(issue['link'], doc('.issuedescription .issuedescription .attachments'))
    issue['content'] = EXPORTED_OP_FORMAT_TEMPLATE.format(
            content=content,
            footer=footer,
            attachments=attachments,
            **issue)

EXPORTED_COMMENT_FORMAT_TEMPLATE = u"""{body}{updates}{attachments}"""

    # comments have fields date, author, body
    issue['comments'] = []
    for comment in doc('.issuecomment'):
        comment = pq(comment)
        if not comment('.date'):
            continue  # Sign in prompt line uses same class
        if comment.hasClass('delcom'):
            continue  # Skip deleted comments

        date = parse_gcode_date(comment('.date').attr('title'))
        body = comment('pre').text()
        author = get_author(comment)

        updates = comment('.updates .box-inner')
        if updates:
            raw = updates.html().strip().replace('\n', '').replace('<b>', '**').replace('</b>', '**').replace('<br/>', '\n')
            updates_text = u'\n\n' + raw.decode('utf-8')
        else:
            updates_text = u''

        attachments_text = get_attachments('{0}#{1}'.format(issue['link'], comment.attr('id')), comment('.attachments'))

        body = EXPORTED_COMMENT_FORMAT_TEMPLATE.format(body=body, updates=updates_text, attachments=attachments_text)
        # Strip the placeholder text if there's any other updates
        body = body.replace(u'(No comment was entered for this change.)\n\n', u'')

        split_comment({'date': date, 'author': author}, body)

    return issue


def main():
    if len(sys.argv) < 2 or sys.argv[1] == '-h' or sys.argv[1] == '--help':
        script = os.path.basename(sys.argv[0])
        usage = "Read all issues from a Google Code project." \
                "\t usage: %s <google project name>" % script
        print usage
        sys.exit()
    google_project_name = sys.argv[1]
    gcode_index = gcode_issues_index(google_project_name)
    gcode_issues = []
    for short_issue in gcode_index:
        issue = get_gcode_issue_new(google_project_name, short_issue)
        gcode_issues.append(issue)

if __name__ == "__main__":
    main()
