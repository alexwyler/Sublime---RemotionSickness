import sublime, sublime_plugin
import time
import re
from AsyncShellCommand import AsyncShellCommand

#
# Tools to alleviate the nausea associated with developing on a remote drive
#

SETTINGS = sublime.load_settings('RemotionSickness.sublime-settings')
REMOTE_PROPOGATION_DELAY = 3

class RemotionSicknessListener(sublime_plugin.EventListener):
  """ Registers all event listeners used """

  def on_activated(self, view):
    global SETTINGS, REMOTE_PROPOGATION_DELAY
    if not SETTINGS.get("reload_on_remote_change", False):
      return

    filepath = view.file_name();
    if not filepath:
      return

    remote_config = remote_config_for_local_filepath(filepath)
    if not remote_config:
      return

    def remote_last_touched_callback(stdout, stderr):
      remote_time = int(stdout)
      last_touched = view.get_status('last_touched')
      if (not last_touched) or (remote_time > float(last_touched)):
        # weird hack needed to actually revert the buffer
        # see http://sublimetext.userecho.com/topic/90145-more-control-over-file-reload-after-external-changes/
        sublime.set_timeout(
          lambda: view.run_command('revert'), REMOTE_PROPOGATION_DELAY * 1000)

    self.get_last_touched(filepath, remote_last_touched_callback)

  def get_last_touched(self, filepath, callback):
    global SETTINGS
    remote_config = remote_config_for_local_filepath(filepath)
    if not remote_config:
      return

    filepath = escape_spaces(
      filepath.replace(
        remote_config.get('local_prefix'),
        remote_config.get('remote_prefix')))

    AsyncShellCommand(
      SETTINGS.get('remote_last_touched_command'),
      [filepath]) \
    .on_success(callback) \
    .set_remote(remote_config.get('remote_host')) \
    .start()

  def on_load(self, view):
    self.update_touch_time(view)

  def on_new(self, view):
    self.update_touch_time(view)

  def on_post_save(self, view):
    global REMOTE_PROPOGATION_DELAY
    self.update_touch_time(view, time.time() + REMOTE_PROPOGATION_DELAY)

  def update_touch_time(self, view, last_touched=None):
    last_touched = last_touched if last_touched else time.time()
    view.set_status('last_touched', str(last_touched))
#
# Utility functions
#

def remote_config_for_local_filepath(filepath):
  """ returns a remote mount config if one applies to the given path """

  global SETTINGS
  for mounted_path_config in SETTINGS.get('mounted_paths'):
    if filepath.startswith(mounted_path_config.get('local_prefix')):
      return mounted_path_config

def escape_spaces(path):
  return re.sub(r' ', '\\ ', path)

def unescape_spaces(path):
  return re.sub(r'\\ ', ' ', path)
