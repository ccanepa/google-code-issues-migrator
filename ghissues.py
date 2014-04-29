#!/usr/bin/env python

import getpass
import logging
import re
import sys

from github import Github
from github import GithubException, BadCredentialsException

import gcodeissues as gi


# The minimum number of remaining Github rate-limited API requests before we pre-emptively
# abort to avoid hitting the limit part-way through migrating an issue.

GITHUB_SPARE_REQUESTS = 50

# The maximum characters per comment in Github, a guess because undocumented
MAX_COMMENT_LENGHT = 7000


class GithubMigrationSession(object):

    def __init__(self, github_user_name, github_project):
        self.session = self._get_session(github_user_name)
        self.log_rate_info()
        self.user = self.session.get_user()
        self.repo = self._get_repo(github_project)
        self._label_cache = {}

    def label(self, name, color = u"FFFFFF"):
        """ Returns the Github label with the given name,
        creating it if necessary.

        name : unicode
           text for the existing / new label to create
        """

        try:
            return self._label_cache[name]
        except KeyError:
            try:
                return self._label_cache.setdefault(name, self.repo.get_label(name))
            except GithubException:
                return self._label_cache.setdefault(name, self.repo.create_label(name, color))

    def log_rate_info(self):
        logging.info('Rate limit (remaining/total) %r', self.session.rate_limiting)
        # Note: this requires extended version of PyGithub from tfmorris/PyGithub repo
        #logging.info('Rate limit (remaining/total) %s',repr(self.session.rate_limit(refresh=True)))

    def _get_session(self, github_user_name):
        while True:
            github_password = getpass.getpass("Github password: ")
            try:
                Github(github_user_name, github_password).get_user().login
                break
            except BadCredentialsException:
                print "Bad credentials, try again."
        return Github(github_user_name, github_password)

    def _get_repo(self, github_project):
        # If the project name is specified as owner/project, assume that it's
        # owned by either a different user than the one we have credentials for,
        # or an organization.
        if "/" in github_project:
            owner_name, github_project = github_project.split("/")
            try:
                github_owner = self.session.get_user(owner_name)
            except GithubException:
                try:
                    github_owner = self.session.get_organization(owner_name)
                except GithubException:
                    github_owner = self.user
        else:
            github_owner = self.user
        return github_owner.get_repo(github_project)

         
def output(string):
    sys.stdout.write(string)
    sys.stdout.flush()


def escape(s):
    """Process text to convert markup and escape things which need escaping"""
    if s:
        s = s.replace('%', '&#37;')  # Escape % signs
    return s


def add_issue_to_github(gh, issue, assign_owner, dry_run):
    """ Migrates the given Google Code issue to Github. """

    # Github rate-limits API requests to 5000 per hour, and if we hit that limit part-way
    # through adding an issue it could end up in an incomplete state.  To avoid this we'll
    # ensure that there are enough requests remaining before we start migrating an issue.

    if gh.session.rate_limiting[0] < GITHUB_SPARE_REQUESTS:
        raise Exception('Aborting to to impending Github API rate-limit cutoff.')

    body = issue['content'].replace('%', '&#37;')

    output('Adding issue %d' % issue['gid'])

    github_issue = None

    if not dry_run:
        github_labels = [gh.label(label) for label in issue['labels']]
        github_issue = gh.repo.create_issue(issue['title'],
                                            body = body.encode('utf-8'),
                                            labels = github_labels)

    # Assigns issues that originally had an owner to the current user
    if issue['owner'] and assign_owner:
        assignee = gh.session.get_user(gh.user.login)
        if not dry_run:
            github_issue.edit(assignee=assignee)

    return github_issue


def add_comments_to_issue(github_issue, gcode_issue, dry_run):
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
            if not dry_run:
                github_issue.create_comment(body.encode('utf-8'))
            output('.')


def process_gcode_issues(gh, google_project_name, existing_issues, gcode_issues,
                         assign_owner, skip_closed, synchronize_ids, dry_run):
    """ Migrates all Google Code issues in the given dictionary to Github.
            gcode_issues : list all of gcode issues in the fledged form
    """
    previous_gid = 1

    for issue in gcode_issues:
        if skip_closed and (issue['state'] == 'closed'):
            continue

        # If we're trying to do a complete migration to a fresh Github project,
        # and want to keep the issue numbers synced with Google Code's, then we
        # need to create dummy closed issues for deleted or missing Google Code
        # issues.
        if synchronize_ids:
            for gid in xrange(previous_gid + 1, issue['gid']):
                if gid in existing_issues:
                    continue

                output('Creating dummy entry for missing issue %d\n' % gid)
                title = 'Google Code skipped issue %d' % gid
                body = '_Skipping this issue number to maintain synchronization with Google Code issue IDs._'
                footer = '_Original issue: ' + gi.GOOGLE_URL.format(google_project_name, gid) + ' _'
                body += '\n\n' + footer
                github_issue = gh.repo.create_issue(title, body=body, labels=[gh.label('imported')])
                github_issue.edit(state='closed')
                existing_issues[previous_gid] = github_issue
            previous_gid = issue['gid']

        # Add the issue and its comments to Github, if we haven't already
        if issue['gid'] in existing_issues:
            github_issue = existing_issues[issue['gid']]
            output('Not adding issue %d (exists)' % issue['gid'])
        else:
            github_issue = add_issue_to_github(gh, issue, assign_owner, dry_run)

        if github_issue:
            add_comments_to_issue(github_issue, issue, dry_run)
            if github_issue.state != issue['state']:
                github_issue.edit(state=issue['state'])
        output('\n')

        gh.log_rate_info()


def get_existing_github_issues(gh, google_project_name):
    """ Returns a dictionary of Github issues previously migrated from Google Code.

    The result maps Google Code issue numbers to Github issue objects.
    """

    output("Retrieving existing Github issues...\n")
    id_re = re.compile(gi.GOOGLE_ISSUE_ID_RE % google_project_name)

    try:
        existing_issues = (list(gh.repo.get_issues(state='open')) +
                           list(gh.repo.get_issues(state='closed')))
        existing_count = len(existing_issues)
        issue_map = {}
        for issue in existing_issues:
            id_match = id_re.search(issue.body)
            if not id_match:
                continue

            google_id = int(id_match.group(1))
            issue_map[google_id] = issue
            labels = [l.name for l in issue.get_labels()]
            if not u'imported' in labels:
                # TODO we could fix up the label here instead of just warning
                logging.warn('Issue missing imported label %s- %r - %s', google_id, labels, issue.title)
        imported_count = len(issue_map)
        logging.info('Found %d Github issues, %d imported', existing_count, imported_count)
    except:
        logging.error('Failed to enumerate existing issues')
        raise
    return issue_map


def autoedit_gcode_issue(issue, label_mapping, state_mapping):
    """applies transformations for github migration compatibility / convenience"""
    # apply a custom label mapping
    labels = [label_mapping[label] for label in issue['labels']
                                                   if label in label_mapping]

    # add an 'imported' label to help multipass migration / updates
    labels.insert(0, u'imported')

    # Add additional labels based on the issue's state
    if issue['status'] in state_mapping:
        labels.append(state_mapping[issue['status']])

    issue['labels'] = labels

def move_comment_0_to_issue_content(issue):
    issue['content'] = issue['comments'].pop(0)['body']
