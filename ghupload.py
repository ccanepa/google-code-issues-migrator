import logging

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

    gh = GithubMigrationSession(github_user_name, github_password)
    
    try:
        existing_issues = get_existing_github_issues(gh, google_project_name)
        log_rate_info()

        gcode_issues = gi.load_local_gcode_issues(gcode_local_dir, edited=True)

        # filter by ID range
        gcode_issues = gi.issues_in_gid_range(gcode_issues, start, end)

        # apply some convenient automatic transformations
        # map(autoedit_gcode_issue, gcode_issues)
        for issue in gcode_issues:
            autoedit_gcode_issue(issue)

        # limit the comment length for github
        for issue in gcode_issues:
            split_long_comments(issue)

        # adapt to the format process_gcode_expects
        move_comment_0_to_
        process_gcode_issues(gh, existing_issues, gcode_issues)
    except Exception:
        parser.print_help()
        raise

