import logging
import os
import sys

import gcodeissues as gco
import ghissues as ghi

# >>>>>>>>>>>>>>>>>>>>>>> configuration

# The googlecode project name
google_project_name = 'los-cocos'

# Directory to store google code issues info
gcode_local_dir = 'save1'

github_user_name = 'ccanepa'
github_project = 'testmigration'

# True assigns github_user_name as the issue owner for all issues,
# False lets all issues unasigned
assign_owner = False

# Ensure that migrated issues keep the same ID
synchronize_ids = True

# Skip all closed bugs
skip_closed = False

# Range of issues to export, python style: from start up-to but not including
# end; set end to None to mean 'all issues with ID >= start'
# ID s are 1-Based 
start = 1
end = 10

# Mapping from Google Code issue labels to Github labels

LABEL_MAPPING = {
    'Type-Defect': 'bug',
    'Type-Enhancement': 'enhancement'
}

# Mapping from Google Code issue states to Github labels

STATE_MAPPING = {
    'invalid': 'invalid',
    'duplicate': 'duplicate',
    'wontfix': 'wontfix'
}

# <<<<<<<<<<<<<<<<<<<<<< configuration


def main():
    if not os.path.isdir(gcode_local_dir):
        print "Error: directory to load googlecode issues does not exists:", gcode_local_dir
        sys.exit(1)

    logging.basicConfig(level=logging.ERROR)

    gh = ghi.GithubMigrationSession(github_user_name, github_project)

    existing_issues = ghi.get_existing_github_issues(gh, google_project_name)
    gh.log_rate_info()

    gcode_issues = gco.load_local_gcode_issues(gcode_local_dir, edited=True)

    # filter by ID range
    gcode_issues = gco.issues_in_gid_range(gcode_issues, start, end)

    # apply some convenient automatic transformations
    # map(autoedit_gcode_issue, gcode_issues)
    for issue in gcode_issues:
        ghi.autoedit_gcode_issue(issue, LABEL_MAPPING, STATE_MAPPING)

    # limit the comment length for github -> este deberia ser el ultimo paso de la
    # cadena de transformacion
    for issue in gcode_issues:
        gco.split_long_comments(issue, ghi.MAX_COMMENT_LENGHT)

    # adapt to the format process_gcode_expects
    for issue in gcode_issues:
        ghi.move_comment_0_to_issue_content(issue)

    ghi.process_gcode_issues(gh, google_project_name, existing_issues, gcode_issues)


def usage():
    description = """
    Uploads to Github the specified range of googlecode issues.
    Range and other info must have been configured in this same script.
    The issues to upload must have been stored locally using the
    companion utility gcodeissues.py

    Usage:
        %prog [--help] [--really]

    Options:
        --help : displays this message
        --really : really write to Github; dry run if not provided
    """
    print description % os.path.basename(sys.argv[0])
    sys.exit()


if __name__ == "__main__":
    if len(sys.argv)>1:
        really = (sys.argv[1] == '--really')
        want_help = not really
    else:
        want_help = True
    if want_help:
        usage()
    dry_run = not really
    main(dry_run)

