import subprocess


def count_lines(filename):
    # VULN: command injection (user input goes into a shell command)
    out = subprocess.check_output("wc -l < " + filename, shell=True)
    return int(out.strip())
