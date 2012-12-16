import os
import xattr
import simplejson
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

METADATA_FILENAME = '.xattr.json'

# def user_attribute(k): return "user." + key

_sentinel = object

def fix(dirpath):
	DirectoryMetadata(dirpath)

def load(path):
	return FileMetadata.from_path(path)

# `xattr`-like implementations.
# Note that `set` is not used because it conflicts with the builtin `set`
def setattr(path, name, value):
	load(path)[name] = value

def get(path, name):
	return load(path)[name]

def remove(path, name):
	del load(path)[name]

def get_all(path, name):
	return load(path)[name].copy()

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

	def __getitem__(self, key):
		self._view[key]

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
		files = set(os.listdir(self.dirpath))
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
						logger.debug("File %s has xattr %r=%s, but serialized data has %s - using serialized data", filename, key, xattr_val, val)
					xattr.set(path, key, val, namespace=xattr.NS_USER)
			self._update_saved_attrs(filename, dest=attrs)

		removed_files = set(self._saved_attrs.keys()).difference(set(attrs.keys()))
		for filename in removed_files:
			logger.info("Dropping metadata for missing file %s: %r", os.path.join(self.dirpath, filename), self._saved_attrs[filename])

		if attrs != self._saved_attrs:
			self._update(attrs)
	
	def get(self, filename, default=_sentinel):
		val = self._saved_attrs.get(filename, default)
		if val is _sentinel: raise KeyError(filename)
		return val

	def _set(self, filename, key, value):
		path = os.path.join(self.dirpath, filename)
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


