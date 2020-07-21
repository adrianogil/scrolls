import subprocess


def run_cmd(cmd):
    subprocess_cmd = cmd
    subprocess_output = subprocess.check_output(subprocess_cmd, shell=True)
    subprocess_output = subprocess_output.decode("utf8")
    subprocess_output = subprocess_output.strip()

    return subprocess_output
