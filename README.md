Scripts to migrate issues from Google Code to Github.

This is a fork of https://github.com/skirpichev/google-code-issues-migrator
which is a fork of https://github.com/arthur-debert/google-code-issues-migrator

### New in this fork ###

googlecode issues are stored locally and can be edited before upload to github.
This is handy to convert svn revision numbers to git sha s or to add markup.

## THIS SCRIPT WILL SEND A LOT OF EMAILS TO ALL WATCHERS

Github's API does not support creating issues or adding comments without
notifying everyone watching the repository. As a result, running this script
targetting an existing repository with watchers who do not want to recieve a
very large number of emails is probably not a good idea.

I do not know of any way around this other than deleting and recreating the
repository immediately before running the import.

### How it works ###

The script iterates over the issues and comments in a Google Code repository,
creating matching issues and comments in Github. This has some limitations:

 - All migrated issues and comments are authored by the user running the
   script, and lose their original creation date. We try to mitigate this by
   adding a non-obtrusive header to each issue and comment stating the original
   author and creation date.

 - Github doesn't support attachments for issues, so any attachments are simply
   listed as links to the attachment on Google Code.

 - Support for Merged-into links for duplicate issues are not implemented.
 
 - Allow to edit issues text and comments locally before upload.
   This is handy to replace references to svn revisions like 'r1234' with the
   matching git commit sha or to add some mardown markup.
   This is a feature new in this fork.

Otherwise almost everything is preserved, including labels, issue state
(open/closed), and issue status (invalid, wontfix, duplicate).

The original script allowed to be run repeatedly to migrate new issues and comments,
without mucking up what's already on Github; this fork does not support that if
you locally edit the issues, but it should not be hard to add a update_gcode_issues
to support this scenario.

### Required Python libraries ###

Run `pip install -r requirements.txt` to install all required libraries.

### Usage ###

Edit ghupload.py to configure the migration options.
It is a good idea to first export to a 'testmigration' project and when
satisfied with the results set the real github project target and make
a final upload.

Run gcodeissues.py to download and store locally  the googlecode issues information
```
	gcodeissues.py <google project name> <local storage directory>
```

Edit as desired `<google project name>/gcode_issues_text.txt` .
In particular, replace_revs.py can be run to replace svn revision numbers with the git sha.

The final result will look better if some markup is manually added at this stage, like:

	- tracebacks -> surround with literal block marks
	- python code blocks -> surround with python code block marks
	- names with double underscores not in a block -> surround with inline literal marks

Warning: if you think to put under version control `<local storage directory>` and your OS
is Windows, be sure to arrange the line endings are not messed up.
git by default will change line endings, to prevent that add a
.gitattributes file in `<local storage directory>` with
```
    *.txt -text
    *.pkl -text
```

Run `ghupload.py --really` to upload to github.

If the upload is interrupted, by example by quotas in github API or timeouts,
the script can be re-run to complete the work.

In that case, to spare some transactions it is better to set the 'start' parameter
to the last issue transmited.

Obviously if the problem was a quota exceded or a github outage you will need to wait some time before rerun. 

This workflow and code was last used at 2014 05 06
