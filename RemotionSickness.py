import sublime, sublime_plugin
import time
from AsyncShell import AsyncShellCommand

#
# Tools to alleviate the nausea associated with developing on a remote drive
#

SETTINGS = sublime.load_settings('RemotionSickness.sublime-settings')
class RemotionSicknessListener(sublime_plugin.EventListener):
  """ Registers all event listeners used """

  def on_activated(self, view):
    global SETTINGS
    if not SETTINGS.get("reload_on_remote_change", False):
      return

    filepath = view.file_name();
    if not filepath:
      return

    filepath = filepath.replace(' ', '\\ ')
    remote_config = remote_config_for_local_filepath(filepath)
    if not remote_config:
      return

    def remote_last_touched_callback(stdout, stderr):
      remote_time = int(stdout)
      last_touched = view.get_status('last_touched')
      if not last_touched or (remote_time > last_touched):
        view.run_command('revert')
        self.update_touch_time(view)

    AsyncShellCommand(SETTINGS.get('remote_last_touched_command'), [filepath]) \
      .on_success(remote_last_touched_callback) \
      .start()

  def on_load(self, view):
    self.update_touch_time(view)

  def on_new(self, view):
    self.update_touch_time(view)

  def on_post_save(self, view):
    self.update_touch_time(view)

  def update_touch_time(self, view):
    global SETTINGS
    filepath = view.file_name().replace(' ', '\\ ')
    remote_config = remote_config_for_local_filepath(filepath)
    if not remote_config:
      return

    view.set_status('last_touched', time.time())

#
# Utility functions
#

def remote_config_for_local_filepath(filepath):
  """ returns a remote mount config if one applies to the given path """

  global SETTINGS
  for mounted_path_config in SETTINGS.get('mounted_paths'):
    if filepath.startswith(mounted_path_config.get('local_prefix')):
      return mounted_path_config
