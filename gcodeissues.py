import csv
from datetime import datetime
import os
import cPickle as pickle
import sys
import urllib2

from pyquery import PyQuery as pq


# The maximum number of records to retrieve from Google Code in a single request
GOOGLE_MAX_RESULTS = 25

EXPORTED_OP_FORMAT_TEMPLATE = u"""
_From {author} on {date:%B %d, %Y %H:%M:%S}_

{content}{attachments}

_Original issue: {footer}_
"""

GOOGLE_ISSUES_URL = 'https://code.google.com/p/{0}/issues/csv?can=1&num={1}&start={2}&colspec=ID%20Type%20Status%20Owner%20Summary%20Opened%20Closed%20Reporter&sort=id'
# Used to write a link to googlecode issue, also see next comment
GOOGLE_URL = 'http://code.google.com/p/{0}/issues/detail?id={1}'
# this used to capture the googlecode issue ID as writen by GOOGLE_URL
GOOGLE_ISSUE_ID_RE = r'http://code.google.com/p/%s/issues/detail\?id=(\d+)'

# separators used to produce an editable view of all issues text
issue_separator = u"\n\n?-?-?-?-?-?-?-issue\n"
field_separator = u"#-#-#-#-#-#-#-field\n"


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

        if short_issues and b'truncated' in short_issues[-1][b'ID']:
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
        if not attachment('a'):  # Skip deleted attachments
            continue

        # Linking to the comment with the attachment rather than the
        # attachment itself since Google Code uses download tokens for
        # attachments
        body += u'**Attachment:** [{0}]({1})'.format(attachment('b').text(), link)
    return body


def parse_gcode_date(date_text):
    """ Transforms a Google Code date into a more human readable string. """

    try:
        parsed = datetime.strptime(date_text, '%a %b %d %H:%M:%S %Y')
    except ValueError:
        return date_text

    return parsed.strftime("%B %d, %Y %H:%M:%S")


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

    comments = []

    # comments[0] ~ the Original Post in the issue
    date = issue['date']
    author = issue['author']
    
    description = doc('.issuedescription .issuedescription')
    OP_text = description('pre').text()
    footer = GOOGLE_URL.format(google_project_name, issue['gid'])
    attachments = get_attachments(issue['link'], doc('.issuedescription .issuedescription .attachments'))
    # body was issue['content'] minus the division if too longer
    body = EXPORTED_OP_FORMAT_TEMPLATE.format(content=OP_text,
                                              footer=footer,
                                              attachments=attachments,
                                              **issue)
    comment = {'date': date, 'author': author, 'body': body}
    comments.append(comment)

    # add the comments
    for google_comment in doc('.issuecomment'):
        pq_comment = pq(google_comment)
        if not pq_comment('.date'):
            continue  # Sign in prompt line uses same class
        if pq_comment.hasClass('delcom'):
            continue  # Skip deleted comments

        date = parse_gcode_date(pq_comment('.date').attr('title'))
        author = get_author(pq_comment)

        comment_text = pq_comment('pre').text()

        updates = pq_comment('.updates .box-inner')
        if updates:
            raw = updates.html().strip().replace('\n', '').replace('<b>', '**').replace('</b>', '**').replace('<br/>', '\n')
            updates_text = u'\n\n' + raw.decode('utf-8')
        else:
            updates_text = u''

        attachments_text = get_attachments('{0}#{1}'.format(issue['link'], pq_comment.attr('id')), pq_comment('.attachments'))

        body = comment_text + updates_text + attachments_text

        # Strip the placeholder text if there's any other updates
        body = body.replace(u'(No comment was entered for this change.)\n\n', u'')
        comment = {'date': date, 'author': author, 'body': body}
        comments.append(comment)

    issue['comments'] = comments
    return issue


# code in this function must be in sync with code in partial_issues_from_editable_text
def as_editable_text(issues):
    """returns the concatenation of all comments in all issues, with distinct separators"""
    issues_parts = []
    for an_issue in issues:
        issue_text_parts = [ comment['body'] for comment in an_issue['comments'] ]
        all_comments_text = field_separator.join(issue_text_parts)
        gid_text = u'%d' % an_issue['gid']
        issue_text = field_separator.join([gid_text, all_comments_text ])
        issues_parts.append(issue_text)
    issues_txt = issue_separator.join(issues_parts)
    return issues_txt


def partial_issues_from_editable_text(text):
    """parses the text into a gid: comments dictionary

    text : has the format that 'as_editable_text' used for output
    """
    partial_issues = {}
    issues_parts = text.split(issue_separator)
    for part in issues_parts:
        comments_body = part.split(field_separator)
        gid = int(comments_body.pop(0))
        partial_issues[gid] = comments_body
    return partial_issues


def update_issues_comments(issues, partial_issues):
    """
    issues:
       each one must be in the format returned by get_gcode_issue, will be modified inplace
    partial_issues:
       each one must be in the format returned by partial_issues_from_editable_text
    """
    for an_issue in issues:
        for comment, new_body in zip(an_issue['comments'], partial_issues[an_issue['gid']]):
            comment['body'] = new_body


def issues_in_gid_range(issues, start=None, end=None):
    if start is None:
        start = 0
    if end is None:
        end = len(issues)
    filtered_issues = [issue for issue in issues if start <= issue['gid'] < end]
    return filtered_issues


def load_local_gcode_issues(store_dir, edited=True):
    """loads the locally stored googlecode issues

    store_dir:
       directory where the original google issues info was saved
       It is expected to have at least
          a file 'gcode_issues_detailed.pkl' where the original issues were saved
          if edited==True a file 'gcode_issues_text.txt
          Typically the .pkl was produced by running this script with issues_local=True
          The .txt initially created by running this script with any flags; it may have been
          edited in a text editor but the field / issues separators must have been preserved.
    edited:
       True: replace the comments body with the text parsed from store_dir/from gcode_issues_text.txt
       False: returns the issues as they were saved

    The paths used have hardcoded short names
    """

     # load full fledged issues from local storage
    fname = os.path.join(store_dir, 'gcode_issues_detailed.pkl')
    with open(fname, 'rb') as f:
        gcode_issues = pickle.load(f)

    if edited:
        # load edited text and update the issues with it
        fname = os.path.join(store_dir, 'gcode_issues_text.txt')
        with open(fname, 'rb') as f:
            in_bytes = f.read(f)
        edited_issues_text = in_bytes.decode('utf-8')

        partial_issues = partial_issues_from_editable_text(edited_issues_text)
        update_issues_comments(gcode_issues, partial_issues)

    return gcode_issues


def main(index_local, issues_local):
    """
    index_local : True loads the index from local storage, False from googlecode
    issues_local : True loads the full fledged issues from local storage, False from googlecode
    """
    if len(sys.argv) < 3 or sys.argv[1] == '-h' or sys.argv[1] == '--help':
        script = os.path.basename(sys.argv[0])
        usage = "Reads all issues from a Google Code project and stores them locally." \
                "\n\t usage: %s <google project name> <outdir>" % script
        print usage
        sys.exit()
    google_project_name = sys.argv[1]
    outdir = sys.argv[2]
    if (index_local or issues_local) and not os.path.exists(outdir):
        print "Error: asking for local sources but outdir does not exist. outdir:", outdir
        sys.exit(1)
    if  (not index_local and not issues_local) and os.path.exists(outdir):
        print 'Error: asking for all external sources but outdir exist, refusing to overwrite.' \
              ' Nothing done. outdir:', outdir
        sys.exit(1)
    if not index_local and not issues_local:
        os.mkdir(outdir)

    fname = os.path.join(outdir, 'gcode_issues_index.pkl')
    if index_local:
        # load index from local storage
        with open(fname, 'rb') as f:
            gcode_index = pickle.load(f)
        print "*** issues index loaded from local storage"
    else:
        # build and store locally the index
        gcode_index = gcode_issues_index(google_project_name)
        with open(fname, "wb") as f:
            pickle.dump(gcode_index, f)
        print "*** issues index pickled"

    fname = os.path.join(outdir, 'gcode_issues_detailed.pkl')
    if issues_local:
        # load full fledged issues from local storage
        with open(fname, 'rb') as f:
            gcode_issues = pickle.load(f)
        print "*** full fledged issues loaded from local storage"
    else:
        # build and store locally the detailed issues
        gcode_issues = []
        for short_issue in gcode_index:
            if len(gcode_issues) % 10 == 0:
                print '.',
            issue = get_gcode_issue(google_project_name, short_issue)
            gcode_issues.append(issue)
        with open(fname, "wb") as f:
            pickle.dump(gcode_issues, f)
        print "\n*** detailed issues  pickled"

    # store locally an editable view of issues text
    text = as_editable_text(gcode_issues)
    out_bytes = text.encode('utf-8')
    fname = os.path.join(outdir, 'gcode_issues_text.txt')
    with open(fname, 'wb') as f:
        f.write(out_bytes)
    print "*** editable issues text saved in local storage"

if __name__ == "__main__":
    # When developing changes you can use the flags to avoid hammering googlecode.
    # Initially both should be False, after a local save is satisfactory the related
    #  flag(s) can be toggled to True
    index_local = True
    issues_local = True
    main(index_local, issues_local)
