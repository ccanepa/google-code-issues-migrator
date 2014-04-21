import csv
import urllib2

from pyquery import PyQuery as pq


# The maximum number of records to retrieve from Google Code in a single request

GOOGLE_MAX_RESULTS = 25

GOOGLE_ISSUE_TEMPLATE = '_Original issue: {0}_'
GOOGLE_ISSUES_URL = 'https://code.google.com/p/{0}/issues/csv?can=1&num={1}&start={2}&colspec=ID%20Type%20Status%20Owner%20Summary%20Opened%20Closed%20Reporter&sort=id'
GOOGLE_URL = 'http://code.google.com/p/{0}/issues/detail?id={1}'
GOOGLE_URL_RE = 'http://code.google.com/p/%s/issues/detail\?id=(\d+)'
GOOGLE_ID_RE = GOOGLE_ISSUE_TEMPLATE.format(GOOGLE_URL_RE)

def gcode_issues_index():
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

        if issues and b'truncated' in issues[-1][b'ID']:
            issues.pop()
            start_index += count
        else:
            break
    return issues

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
        body += '**Attachment:** [{0}]({1})'.format(attachment('b').text().encode('utf-8'), link)
    return body

def get_gcode_issue(short_issue):
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
    if options.google_code_cookie:
        opener.addheaders = [('Cookie', options.google_code_cookie)]
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
    issue['content'] = u'_From {author} on {date:%B %d, %Y %H:%M:%S}_\n\n{content}{attachments}\n\n{footer}'.format(
            content = issue['comments'].pop(0)['body'],
            footer = GOOGLE_ISSUE_TEMPLATE.format(GOOGLE_URL.format(google_project_name, issue['gid'])),
            attachments = get_attachments(issue['link'], doc('.issuedescription .issuedescription .attachments')),
            **issue)

    issue['comments'] = []
    for comment in doc('.issuecomment'):
        comment = pq(comment)
        if not comment('.date'):
            continue # Sign in prompt line uses same class
        if comment.hasClass('delcom'):
            continue # Skip deleted comments

        date = parse_gcode_date(comment('.date').attr('title'))
        body = comment('pre').text()
        author = get_author(comment)

        updates = comment('.updates .box-inner')
        if updates:
            body += '\n\n' + updates.html().strip().replace('\n', '').replace('<b>', '**').replace('</b>', '**').replace('<br/>', '\n')

        body += get_attachments('{0}#{1}'.format(issue['link'], comment.attr('id')), comment('.attachments'))

        # Strip the placeholder text if there's any other updates
        body = body.replace('(No comment was entered for this change.)\n\n', '')

        split_comment({'date': date, 'author': author}, body)

    return issue


def main():
    usage = "usage: %prog <google project name>"
    description = "Migrate all issues from a Google Code project to a Github project."
    gcode_index = gi.gcode_issues_index()

if __name__ == "__main__":

    
