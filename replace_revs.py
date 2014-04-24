import re 


def dict_of_rev_to_sha(filename):
    """returns a dict to convert svn revision number to git sha

    filename: points to a file with the format
        1st line: column headers or whatever (discarded inconditionally)
        intermediate lines: begins with <4chars: revnum> + '  ' + <40chars: full sha>
        lastline: empty or whatever (discarded inconditionally)

    Returns a dict with kv pairs <revnum_string>: <full sha> where
        revnum_string: unpaded svn revision number, like '1'
        sha: always the complete (40 chars) sha for the git commit
    """
    with open(filename, 'r') as f:
        text = f.read()
    all_lines = text.split('\n')[1:-1]
    d = {}
    for line in all_lines:
        revnum = unicode(line[:4].strip())
        assert line[4:6] == '  '
        sha = unicode(line[6:40+6])
        assert len(line)==(40+6) or line[40+6]==' '
        d[revnum] = sha
    return d


def replace_rev_with_sha(text, rev_to_sha, num_sha_digits_to_use):
    """ replaces 'r<revnum>' with 'commit <sha>

    text assumed to be unicode
    <sha> is choped to the first num_sha_digits_to_use
    """
    conv = {}
    for rev in rev_to_sha:
        conv[u'r' + rev] = u'commit ' + rev_to_sha[rev][:num_sha_digits_to_use]
    
    regex = re.compile(r"\b(?P<rev>r\d+)\b", re.UNICODE)
    return regex.sub(lambda matcho: conv.get(matcho.group('rev'), rev), text) 


if __name__ == "__main__":
    filename = 'svn_revision_to_git_sha.txt'
    rev_to_sha = dict_of_rev_to_sha(filename)

    filename = 'save1/gcode_issues_text.txt'
    with open(filename, 'rb') as f:
        in_bytes = f.read()
    issues_text = in_bytes.decode('utf-8')
    num_sha_digits_to_use = 7
    issues_text = replace_rev_with_sha(issues_text, rev_to_sha, num_sha_digits_to_use)

    out_bytes = issues_text.encode('utf-8')
    with open(filename, 'wb') as f:
        f.write(out_bytes)
