import subprocess


def count_lines(filename):
    # Count lines without invoking a shell, so the filename can never be
    # interpreted as shell metacharacters (command injection).
    out = subprocess.check_output(["wc", "-l", filename])
    return int(out.strip().split()[0])
