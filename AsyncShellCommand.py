import threading
import subprocess
import sublime

class AsyncShellCommand(threading.Thread):
    def __init__(self, command, args=[]):
        threading.Thread.__init__(self)
        self.command = command
        self.args = args
        self.expected_return_codes = [0]
        self.on_success_callback = None
        self.on_error_callback = None
        self.remote_shell = None

    def on_success(self, on_success_callback):
        self.on_success_callback = on_success_callback
        return self

    def on_error(self, on_error_callback):
        self.on_error_callback = on_error_callback
        return self

    def set_expected_return_codes(self, expected_return_codes):
        self.expected_return_codes = expected_return_codes
        return self

    def set_remote(self, remote_shell):
        self.remote_shell = remote_shell
        return self

    def run(self):
        shell_script = self.command.format(*self.args)

        if (self.remote_shell):
            shell_script = "ssh {0} '{1}'".format(
                self.remote_shell,
                shell_script.replace("'", "\\'"))

        proc = subprocess.Popen(
            shell_script,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, shell=True)

        self.stdout, self.stderr = proc.communicate()

        if proc.returncode in self.expected_return_codes and not self.stderr:
            if self.on_success_callback:
                sublime.set_timeout(
                    lambda: self.on_success_callback(self.stdout, self.stderr),
                    1)
        else:
            if self.on_error_callback:
                sublime.set_timeout(
                    lambda: self.on_error_callback(self.stdout, self.stderr),
                    1)
            else:
                print "Shell command: {0}".format(shell_script)
                print "Error code: {0}".format(proc.returncode)
                print "StdErr output:\n{0}".format(self.stderr)
