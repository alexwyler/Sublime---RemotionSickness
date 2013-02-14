import re
import string
import sublime, sublime_plugin
import time
import os.path
from AsyncShellCommand import AsyncShellCommand

#
# Tools to alleviate the nausea associated with developing on a remote drive
#

SETTINGS = sublime.load_settings('RemotionSickness.sublime-settings')
REMOTE_PROPOGATION_DELAY = 0

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
        remote_config.get('local_mount_path'),
        remote_config.get('remote_mount_path'),
        1))

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

class TagsSearchCommand(sublime_plugin.TextCommand):
  """Searches for a given tag in remote tagfile and opens corresponding file"""

  def __init__(self, args):
    self.cache = {}
    super(TagsSearchCommand, self).__init__(args)

  def search_tag(self, tag):
    tags_command = SETTINGS.get("remote_tags_command")
    remote_config = best_remote_config_for_view(self.view)
    if not remote_config:
      return

    print 'searching for tag'
    AsyncShellCommand(tags_command, [remote_config.get("remote_project_path"), tag]) \
    .set_remote(remote_config.get("remote_host")) \
    .on_success(self.tags_search_callback) \
    .start()

  def tags_search_callback(self, stdout, stderr):
    print 'std out', stdout
    tags = [line.split("\t")[:-1] for line in stdout.splitlines()]
    if len(tags) == 0:
      sublime.status_message("No tags information found")
    elif len(tags) == 1:
      self.open_tag(tags[0])
    else:
      self.view.window().show_quick_panel(tags, lambda idx: idx > -1 and self.open_tag(tags[idx]))

  def php_word_under_cursor(self):
    """Selects current statement under cursor. Counts special PHP symbols as parts of statement"""

    a = b = self.view.sel()[0].a
    word_chars = string.ascii_letters + string.digits + "_:$"
    while self.view.substr(a - 1) in word_chars:
      a -= 1
    while self.view.substr(b) in word_chars:
      b += 1
    reg = sublime.Region(a, b)
    return self.view.substr(reg)

  def run(self, edit):
    sel = self.view.substr(self.view.sel()[0])
    print sel
    if len(sel):
      self.search_tag(sel)
    else:
      self.view.window().show_input_panel("Search for tag", self.php_word_under_cursor(), self.search_tag, None, None)

  def tags_loaded(self, tag):
    tags_results = open(TagsSearchCommand.TAGS_RESULTS).read().splitlines()
    tags = [line.split("\t")[:-1] for line in tags_results]
    self.cache[tag] = tags
    self.process_tags(tags)

  def process_tags(self, tags):
    if len(tags) == 0:
      sublime.status_message("No tags information found")
    elif len(tags) == 1:
      self.open_tag(tags[0])
    else:
      self.view.window().show_quick_panel(tags, lambda idx: idx > -1 and self.open_tag(tags[idx]))

  def open_tag(self, tag_fields):
    remote_config = best_remote_config_for_view(self.view)
    filepath = local_path_for_remote_path(
      os.path.join(remote_config.get('remote_project_path'), tag_fields[1]))

    matching_text = tag_fields[2][1:-3].strip()
    new_view = sublime.active_window().open_file(filepath)
    self.scroll_to_text(new_view, matching_text)

  def scroll_to_text(self, view, text):
    print text
    reg = view.find(text, 0, sublime.LITERAL)
    if reg:
      view.sel().clear()
      view.sel().add(sublime.Region(reg.a))
      view.show(reg.a)
    else:
      print "Can't find text: {0}".format(text)

class OpenRemote(sublime_plugin.WindowCommand):
    """Shows a list of remote files to open"""

    def __init__(self, args):
      self.cached_files = {}
      self.cached_time = {}

    def run(self, force_reload=False):
      remote_config = default_remote_config()

      if not remote_config:
        return

      remote_host = remote_config.get("remote_host");
      cached_files = self.cached_files[remote_host] if self.cached_files.has_key(remote_host) else None
      cached_time = self.cached_time[remote_host] if self.cached_time.has_key(remote_host) else 0
      cache_timeout = SETTINGS.get('cache_timeout', 600)

      def remote_ls_callback(stdout, stderr):
        self.cached_files[remote_host] = stdout.splitlines()
        self.cached_time[remote_host] = time.time()
        self.show_open_panel(remote_config, self.cached_files[remote_host])

      if force_reload or (not cached_files) or (time.time() - cached_time > cache_timeout):
        ls_command = SETTINGS.get('remote_ls_command')

        AsyncShellCommand(ls_command, [remote_config.get("remote_project_path")]) \
        .set_remote(remote_config.get("remote_host")) \
        .on_success(remote_ls_callback) \
        .start()
      else:
        self.show_open_panel(remote_config, self.cached_files[remote_host])

    def show_open_panel(self, remote_config, files):
      def file_selected(idx):
        if idx > -1:
          filepath = locale_path_for_remote_project_filepath(
            remote_config,
            files[idx])
          print filepath
          sublime.active_window().open_file(filepath)

      sublime.active_window().show_quick_panel(files, file_selected)



#
# Utility functions
#

def best_remote_config_for_view(view):
  filepath = view.file_name();
  remote_config = None
  if filepath:
    remote_config = remote_config_for_local_filepath(filepath) or remote_config_for_remote_filepath(filepath)

  return remote_config or default_remote_config()

def default_remote_config():
 global SETTINGS
 for remote_config in SETTINGS.get('mounted_paths'):
  return remote_config

def remote_config_for_local_filepath(filepath):
  """ returns a remote mount config if one applies to the given path """

  global SETTINGS
  for mounted_path_config in SETTINGS.get('mounted_paths'):
    if filepath.startswith(mounted_path_config.get('local_mount_path')):
      return mounted_path_config

def remote_config_for_remote_filepath(filepath):
  """ returns a remote mount config if one applies to the given path """

  global SETTINGS
  for mounted_path_config in SETTINGS.get('mounted_paths'):
    if filepath.startswith(mounted_path_config.get('remote_mount_path')):
      return mounted_path_config

def local_path_for_remote_path(remote_path):
  remote_config = remote_config_for_remote_filepath(remote_path)
  if remote_config:
    return remote_path.replace(
      remote_config.get('remote_mount_path'),
      remote_config.get('local_mount_path'),
      1)

def locale_path_for_remote_project_filepath(remote_config, remote_project_file):
  remote_path = \
  os.path.join(remote_config.get('remote_project_path'), remote_project_file)

  return remote_path.replace(
    remote_config.get('remote_mount_path'),
    remote_config.get('local_mount_path'),
    1)

def escape_spaces(path):
  return re.sub(r' ', '\\ ', path)

def unescape_spaces(path):
  return re.sub(r'\\ ', ' ', path)
