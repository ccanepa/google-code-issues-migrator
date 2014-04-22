#!/usr/bin/env python

import getpass
import logging
import optparse
import re
import sys

from github import Github
from github import GithubException, BadCredentialsException

import gcodeissues as gi

logging.basicConfig(level=logging.ERROR)

# used to mark a github issue as an imported from googlecode
GOOGLE_URL_RE = 'http://code.google.com/p/%s/issues/detail\?id=(\d+)'
GOOGLE_ID_RE = gi.GOOGLE_ISSUE_TEMPLATE.format(GOOGLE_URL_RE)


# The minimum number of remaining Github rate-limited API requests before we pre-emptively
# abort to avoid hitting the limit part-way through migrating an issue.

GITHUB_SPARE_REQUESTS = 50

# Mapping from Google Code issue labels to Github labels

LABEL_MAPPING = {
    'Type-Defect' : 'bug',
    'Type-Enhancement': 'enhancement'
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


def escape(s):
    """Process text to convert markup and escape things which need escaping"""
    if s:
        s = s.replace('%', '&#37;')  # Escape % signs
    return s


def github_label(name, color = "FFFFFF"):
    """ Returns the Github label with the given name, creating it if necessary. """

    try:
        return label_cache[name]
    except KeyError:
        try:
            return label_cache.setdefault(name, github_repo.get_label(name))
        except GithubException:
            return label_cache.setdefault(name, github_repo.create_label(name, color))


def add_issue_to_github(issue):
    """ Migrates the given Google Code issue to Github. """

    # Github rate-limits API requests to 5000 per hour, and if we hit that limit part-way
    # through adding an issue it could end up in an incomplete state.  To avoid this we'll
    # ensure that there are enough requests remaining before we start migrating an issue.

    if github.rate_limiting[0] < GITHUB_SPARE_REQUESTS:
        raise Exception('Aborting to to impending Github API rate-limit cutoff.')

    body = issue['content'].replace('%', '&#37;')

    output('Adding issue %d' % issue['gid'])

    github_issue = None

    if not options.dry_run:
        github_labels = [github_label(label) for label in issue['labels']]
        github_issue = github_repo.create_issue(issue['title'], body = body.encode('utf-8'), labels = github_labels)

    # Assigns issues that originally had an owner to the current user
    if issue['owner'] and options.assign_owner:
        assignee = github.get_user(github_user.login)
        if not options.dry_run:
            github_issue.edit(assignee=assignee)

    return github_issue


def add_comments_to_issue(github_issue, gcode_issue):
    """ Migrates all comments from a Google Code issue to its Github copy. """

    # Retrieve existing Github comments, to figure out which Google Code comments are new
    existing_comments = [comment.body for comment in github_issue.get_comments()]

    # Add any remaining comments to the Github issue
    output(", adding comments")
    for i, comment in enumerate(gcode_issue['comments']):
        body = u'_From {author} on {date}_\n\n{body}'.format(**comment)
        if body in existing_comments:
            logging.info('Skipping comment %d: already present', i + 1)
        else:
            logging.info('Adding comment %d', i + 1)
            if not options.dry_run:
                github_issue.create_comment(body.encode('utf-8'))
            output('.')


def process_gcode_issues(existing_issues, gcode_issues):
    """ Migrates all Google Code issues in the given dictionary to Github.
            gcode_issues : list all of gcode issues in the fledged form
    """
    previous_gid = 1

    for issue in gcode_issues:
        if options.skip_closed and (issue['state'] == 'closed'):
            continue

        # If we're trying to do a complete migration to a fresh Github project,
        # and want to keep the issue numbers synced with Google Code's, then we
        # need to create dummy closed issues for deleted or missing Google Code
        # issues.
        if options.synchronize_ids:
            for gid in xrange(previous_gid + 1, issue['gid']):
                if gid in existing_issues:
                    continue

                output('Creating dummy entry for missing issue %d\n' % gid)
                title = 'Google Code skipped issue %d' % gid
                body = '_Skipping this issue number to maintain synchronization with Google Code issue IDs._'
                footer = gi.GOOGLE_ISSUE_TEMPLATE.format(gi.GOOGLE_URL.format(google_project_name, gid))
                body += '\n\n' + footer
                github_issue = github_repo.create_issue(title, body=body, labels=[github_label('imported')])
                github_issue.edit(state='closed')
                existing_issues[previous_gid] = github_issue
            previous_gid = issue['gid']

        # Add the issue and its comments to Github, if we haven't already
        if issue['gid'] in existing_issues:
            github_issue = existing_issues[issue['gid']]
            output('Not adding issue %d (exists)' % issue['gid'])
        else:
            github_issue = add_issue_to_github(issue)

        if github_issue:
            add_comments_to_issue(github_issue, issue)
            if github_issue.state != issue['state']:
                github_issue.edit(state=issue['state'])
        output('\n')

        log_rate_info()


def get_existing_github_issues():
    """ Returns a dictionary of Github issues previously migrated from Google Code.

    The result maps Google Code issue numbers to Github issue objects.
    """

    output("Retrieving existing Github issues...\n")
    id_re = re.compile(GOOGLE_ID_RE % google_project_name)

    try:
        existing_issues = list(github_repo.get_issues(state='open')) + list(github_repo.get_issues(state='closed'))
        existing_count = len(existing_issues)
        issue_map = {}
        for issue in existing_issues:
            id_match = id_re.search(issue.body)
            if not id_match:
                continue

            google_id = int(id_match.group(1))
            issue_map[google_id] = issue
            labels = [l.name for l in issue.get_labels()]
            if not 'imported' in labels:
                # TODO we could fix up the label here instead of just warning
                logging.warn('Issue missing imported label %s- %r - %s', google_id, labels, issue.title)
        imported_count = len(issue_map)
        logging.info('Found %d Github issues, %d imported', existing_count, imported_count)
    except:
        logging.error('Failed to enumerate existing issues')
        raise
    return issue_map


def autoedit_gcode_issue(issue):
    """applies transformations for github migration compatibility"""
    # add an 'imported' label to help multipass migration / updates
    issue.labels.insert(0, 'imported')

    # filter out uninteresting labels (-> estaria implicito en el que sigue)
    if options.omit_priority:
        issue.labels = [label for label in issue.labels
                                        if not label.startswith('Priority-')]

    # apply a custom label mapping
    issue.labels = [LABEL_MAPPING[label] for label in issue.labels
                                                   if label in LABEL_MAPPING]
    # Add additional labels based on the issue's state
    if issue['status'] in STATE_MAPPING:
        issue.labels.append(STATE_MAPPING[issue['status']])


def log_rate_info():
    logging.info('Rate limit (remaining/total) %r', github.rate_limiting)
    # Note: this requires extended version of PyGithub from tfmorris/PyGithub repo
    #logging.info('Rate limit (remaining/total) %s',repr(github.rate_limit(refresh=True)))


if __name__ == "__main__":
    usage = "usage: %prog [options] <google project name> <github username> <github project>"
    description = "Migrate all issues from a Google Code project to a Github project."
    parser = optparse.OptionParser(usage=usage, description=description)

    parser.add_option("-a", "--assign-owner", action="store_true", dest="assign_owner",
                      help="Assign owned issues to the Github user", default=False)
    parser.add_option("-d", "--dry-run", action="store_true", dest="dry_run",
                      help="Don't modify anything on Github", default=False)
    parser.add_option("-p", "--omit-priority", action="store_true", dest="omit_priority",
                      help="Don't migrate priority labels", default=False)
    parser.add_option("-s", "--synchronize-ids", action="store_true", dest="synchronize_ids",
                      help="Ensure that migrated issues keep the same ID", default=False)
    parser.add_option("-c", "--google-code-cookie", dest="google_code_cookie",
                      help="Cookie to use for Google Code requests. Required to get unmangled names",
                      default='')
    parser.add_option('--skip-closed', action='store_true', dest='skip_closed',
                      help='Skip all closed bugs', default=False)

    options, args = parser.parse_args()

    if len(args) != 3:
        parser.print_help()
        sys.exit()

    label_cache = {}  # Cache Github tags, to avoid unnecessary API requests

    google_project_name, github_user_name, github_project = args

    while True:
        github_password = getpass.getpass("Github password: ")
        try:
            Github(github_user_name, github_password).get_user().login
            break
        except BadCredentialsException:
            print "Bad credentials, try again."

    github = Github(github_user_name, github_password)
    log_rate_info()
    github_user = github.get_user()

    # If the project name is specified as owner/project, assume that it's owned by either
    # a different user than the one we have credentials for, or an organization.

    if "/" in github_project:
        owner_name, github_project = github_project.split("/")
        try:
            github_owner = github.get_user(owner_name)
        except GithubException:
            try:
                github_owner = github.get_organization(owner_name)
            except GithubException:
                github_owner = github_user
    else:
        github_owner = github_user

    github_repo = github_owner.get_repo(github_project)

    try:
        existing_issues = get_existing_github_issues()
        log_rate_info()

        gcode_index = gi.gcode_issues_index(google_project_name)
        #gcode_issues = [ get_gcode_issue(google_project_name, short_issue) for short_issue in gcode_index]
        gcode_issues = []
        for short_issue in gcode_index:
            issue = gi.get_gcode_issue(google_project_name, short_issue)
            gcode_issues.append(issue)

        # map(autoedit_gcode_issue, gcode_issues)
        for issue in gcode_issues:
            autoedit_gcode_issue(issue)
        
        process_gcode_issues(existing_issues, gcode_issues)
    except Exception:
        parser.print_help()
        raise
