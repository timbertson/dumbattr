from __future__ import print_function
import os
import xattr
import simplejson
import logging
from collections import defaultdict
import __builtin__

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

METADATA_FILENAME = '.xattr.json'

_sentinel = object

Set = __builtin__.set

def fix(dirpath):
	DirectoryMetadata(dirpath)

def stored_view(dirpath):
	'''
	Returns a dictionary of stored metadata for the given directory,
	without checking (or fixing) any actual file attributes.

	Any changes made to this dictionary have no effect.
	'''
	if not os.path.isdir(dirpath):
		raise OSError("Not a directory: %s" % (dirpath,))
	meta_path = os.path.join(dirpath, METADATA_FILENAME)
	if os.path.exists(meta_path):
		logger.debug("Loading saved records for %s", dirpath)
		with open(meta_path) as f:
			return simplejson.load(f)
	return {}

def load(path):
	return FileMetadata.from_path(path)

def set(path, name, value):
	load(path)[name] = value

def get(path, name, default=_sentinel):
	f = load(path)
	if default is _sentinel:
		return f[name]
	return f.get(name, default)

def remove(path, name):
	del load(path)[name]

def get_all(path):
	return load(path).copy()

class CachingAttributeStore(object):
	'''
	Provides an object that only checks the metadata in a given directory the first
	time a file in that directory is accessed.

	Note that after a directory is first accessed, any changes to the metadata of
	any file in that directory from another process (or even instance) will be ignored.
	'''
	def __init__(self):
		self.dirs = defaultdict(lambda d: DirectoryMetadata(d))
	
	def load(path):
		dirname = os.path.abspath(os.path.dirname(path))
		dirdata = self.dirs[dirname]
		return FileMetadata(dirdata, os.path.basename(path))

class FileMetadata(object):
	def __init__(self, dirdata, filename):
		self.dir = dirdata
		self.filename = filename
		path = os.path.join(dirdata.dirpath, filename)
		if not os.path.exists(path):
			raise OSError("No such file: %s" % (path,))
	
	def __delitem__(self, key):
		try:
			self.dir.remove_attr(self.filename, key)
		except IOError as e:
			logger.debug("IOError in __delitem__: %s" % (e,))
			import errno
			if errno.errorcode[e.errno] == 'ENODATA':
				# TODO: is there a better way to detect the case of having no such xattr?
				raise KeyError(key)
			raise

	def __setitem__(self, key, value):
		self.dir.set_attr(self.filename, key, value)

	def get(self, key, default=None):
		return self._view.get(key, default)

	def __getitem__(self, key):
		return self._view[key]

	@classmethod
	def from_path(cls, path):
		dirname, filename = os.path.split(path)
		return cls(DirectoryMetadata(dirname), filename)
	
	@property
	def _view(self):
		return self.dir.get(self.filename, {})

	def keys(self):
		return self._view.keys()

	def values(self):
		return self._view.values()

	def items(self):
		return self._view.items()

	def copy(self):
		return self._view.copy()

class DirectoryMetadata(object):
	def __init__(self, dirpath):
		self.meta_path = os.path.join(dirpath, METADATA_FILENAME)
		self.dirpath = dirpath
		self._load()
		self._fix()
	
	def _load(self):
		self._saved_attrs = {}
		if os.path.exists(self.meta_path):
			logger.debug("Loading saved records for %s", self)
			with open(self.meta_path) as f:
				self._saved_attrs = simplejson.load(f)

	def __repr__(self):
		return "<DirectoryMetadata: %s>" % (self.dirpath,)
	
	def _fix(self):
		logger.debug("Fixing records for %s", self)
		files = Set(os.listdir(self.dirpath))
		attrs = {}
		for filename in files:
			path = os.path.join(self.dirpath, filename)
			if os.path.islink(path):
				# just copy symlink attrs, as they can't be placed on a symlink
				try:
					attrs[filename] = self._saved_attrs[filename]
				except KeyError: pass # no entry in self._saved_attrs
				continue

			try:
				recovered_attrs = self._saved_attrs[filename]
			except KeyError: pass
			else:
				file_attrs = self._get_xattrs(filename)
				logger.debug("xattrs for %s: %r", filename, file_attrs)
				for key, val in recovered_attrs.items():
					xattr_val = file_attrs.get(key, None)
					if xattr_val != val:
						logger.info("File %s has xattr %r=%s, but serialized data has %s - using serialized data", filename, key, xattr_val, val)
					xattr.set(path, key, val, namespace=xattr.NS_USER)
			self._update_saved_attrs(filename, dest=attrs)

		removed_files = Set(self._saved_attrs.keys()).difference(Set(attrs.keys()))
		for filename in removed_files:
			logger.debug("Dropping metadata for missing file %s: %r", os.path.join(self.dirpath, filename), self._saved_attrs[filename])

		if attrs != self._saved_attrs:
			self._update(attrs)
	
	def get(self, filename, default=_sentinel):
		val = self._saved_attrs.get(filename, default)
		if val is _sentinel: raise KeyError(filename)
		return val

	def _set(self, filename, key, value):
		path = os.path.join(self.dirpath, filename)
		logger.info("Setting %s=%s (%s)", key, value, path)
		if os.path.islink(path):
			if value is None:
				h = self._saved_attrs[filename]
				del h[key]
				if not h:
					del self._saved_attrs[filename]
			else:
				if not filename in self._saved_attrs:
					self._saved_attrs[filename] = {}
				self._saved_attrs[filename][key] = value
		else:
			logger.debug("Setting xattr %s=%s (%s)", key, value, path)
			if value is None:
				xattr.remove(path, key, namespace=xattr.NS_USER)
			else:
				xattr.set(path, key, value, namespace=xattr.NS_USER)
			self._update_saved_attrs(filename)

	def _get_xattrs(self, filename):
		return dict(xattr.get_all(os.path.join(self.dirpath, filename), namespace=xattr.NS_USER))

	def _update_saved_attrs(self, filename, dest=None):
		if dest is None:
			dest = self._saved_attrs
		xattrs = self._get_xattrs(filename)
		if xattrs:
			dest[filename] = xattrs
		else:
			try:
				del dest[filename]
			except KeyError: pass

	def set_attr(self, filename, key, value):
		self._set(filename, key, value)
		self.save()
	
	def remove_attr(self, filename, key):
		self._set(filename, key, None)
		self.save()
	
	def save(self):
		attrs = self._saved_attrs
		if len(attrs) == 0:
			if os.path.exists(self.meta_path):
				os.remove(self.meta_path)
		else:
			with open(self.meta_path, 'w') as f:
				simplejson.dump(attrs, f, indent='  ')
		logger.debug("Saved serialized xattrs for %s", self.dirpath)

	def _update(self, attrs):
		logger.debug("Saving new metadata to %s: %r", self.meta_path, attrs)
		self._saved_attrs = attrs
		self.save()


def main():
	import argparse
	parser = argparse.ArgumentParser()
	parser.add_argument('-v','--verbose', action='store_true')
	parser.add_argument('-q','--quiet', action='store_true')

	# create the top-level parser
	subparsers = parser.add_subparsers()

	def ls_action(args):
		end = '' if args.oneline else '\n'

		paths = []
		for p in args.paths:
			if os.path.isdir(p) and not args.dir:
				paths.extend([os.path.join(p, f) for f in os.listdir(p)])
			else:
				paths.append(p)

		for p in paths:
			print(p,end=end)
			for pair in get_all(p).items():
				if args.oneline:
					print('|%s=%s' % pair, end=end)
				else:
					print('  %10s: %s' % pair, end)
			if args.oneline:
				print()
	
	def set_action(args):
		for p in args.paths:
			set(p, args.key, args.value)

	def get_action(args):
		print_path = len(args.paths) > 1
		for p in args.paths:
			val = get(p, args.key)
			if print_path:
				print("%s: %s" % (p, val))
			else:
				print(val)

	def _do_fix(p):
		logger.debug("Fixing: %s", p)
		fix(p)

	def fix_action(args):
		for p in args.paths:
			logger.info("%s path: %s", "Recursively fixing" if args.recurse else "Fixing", p)
			if not args.recurse:
				_do_fix(p)
			else:
				for root, dirs, files in os.walk(p):
					_do_fix(root)
	
	# create the parser for the "ls" command
	parser_ls = subparsers.add_parser('ls', help="print all attributes of one or more files")
	parser_ls.add_argument('-1', action='store_true',dest='oneline', help='print results on a single line')
	parser_ls.add_argument('-d', action='store_true',dest='dir', help='list directories, not their contents')
	parser_ls.add_argument('paths', nargs='+')
	parser_ls.set_defaults(func=ls_action)

	# create the parser for the "set" command
	parser_set = subparsers.add_parser('set', help="set an attribute value on one or more files")
	parser_set.add_argument('key')
	parser_set.add_argument('value')
	parser_set.add_argument('paths', nargs='+')
	parser_set.set_defaults(func=set_action)

	# create the parser for the "get" command
	parser_get = subparsers.add_parser('get', help="print the value of a specific attribute for one or more files")
	parser_get.add_argument('key')
	parser_get.add_argument('paths', nargs='+')
	parser_get.set_defaults(func=get_action)

	# create the parser for the "fix" command
	parser_fix = subparsers.add_parser('fix', help="ensure xattrs match stored attribute data for one or more paths")
	parser_fix.add_argument('-r', '--recurse', action='store_true')
	parser_fix.add_argument('paths', nargs='+')
	parser_fix.set_defaults(func=fix_action)

	# parse the args and call whatever function was selected
	args = parser.parse_args()

	logger.setLevel(logging.ERROR if args.quiet else (logging.DEBUG if args.verbose else logging.INFO))

	args.func(args)

if __name__ == '__main__':
	# just dump logging messages to stderr, with no additional formatting
	logging.getLogger().handlers[0].setFormatter(logging.Formatter("%(message)s"))
	main()
