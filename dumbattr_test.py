import os
import sys
from os import path as P
import tempfile
import logging
import shutil
import unittest

import dumbattr
import xattr

class DumbattrTests(unittest.TestCase):
	def setUp(self):
		self.base = tempfile.mkdtemp("dumbattr-test")
		self.dir = P.join(self.base, "directory")
		self.file1 = P.join(self.base, "file1")
		self.file2 = P.join(self.base, "file2")
		self.link_target = P.join(self.base, "link_target")

		os.makedirs(self.dir)
		with open(self.file1, 'w') as f: f.write("one")
		with open(self.file2, 'w') as f: f.write("two")
		with open(self.link_target, 'w') as f: f.write("symlink")
		self.link = P.join(self.base, "link")
		os.symlink(self.link_target, self.link)
		logging.info(self.base)
	
	def tearDown(self):
		shutil.rmtree(self.base)
	
	def all_xattrs(self, path, **kw):
		return dict(xattr.get_all(path, namespace=xattr.NS_USER, **kw))
	
	def serialized_metadata(self, path=None):
		import simplejson
		if path is None: path = self.base
		try:
			with open(P.join(path, dumbattr.METADATA_FILENAME)) as f:
				d = simplejson.load(f)
		except IOError:
			return None
		return d

	def test_adding_attr_to_previously_untouched_dir(self):
		dumbattr.set(self.file1, "test1", "value1")
		self.assertEqual(self.all_xattrs(self.file1), {"test1":"value1"})
		self.assertEqual(self.serialized_metadata(), {"file1": {"test1":"value1"}})

	def test_adding_multiple_attrs(self):
		dumbattr.set(self.file1, "test1", "value1")
		dumbattr.set(self.file1, "test2", "value2")
		self.assertEqual(self.all_xattrs(self.file1), {"test1":"value1", "test2": "value2"})
		self.assertEqual(self.serialized_metadata(), {"file1": {"test1":"value1", "test2": "value2"}})

	def test_adding_attr_to_second_file(self):
		dumbattr.set(self.file1, "test1", "value1")
		dumbattr.set(self.file2, "test2", "value2")
		self.assertEqual(self.all_xattrs(self.file1), {"test1":"value1"})
		self.assertEqual(self.all_xattrs(self.file2), {"test2":"value2"})
		self.assertEqual(self.serialized_metadata(), {"file1": {"test1":"value1"}, "file2": {"test2": "value2"}})

	def test_loading_attr_ensures_all_attrs_in_dir_are_serialized(self):
		xattr.set(self.file1, "file_1", "1", namespace=xattr.NS_USER)
		xattr.set(self.file1, "file_2", "2", namespace=xattr.NS_USER)
		xattr.set(self.dir, "dir_1", "1", namespace=xattr.NS_USER)
		xattr.set(self.link_target, "target", "1", namespace=xattr.NS_USER)
		# can't set any xattrs on link itself
		self.assertEqual(self.serialized_metadata(), None)

		dumbattr.fix(self.base)

		self.assertEqual(self.all_xattrs(self.file1), {"file_1":"1", "file_2": "2"})
		self.assertEqual(self.all_xattrs(self.dir), {"dir_1":"1"})
		self.assertEqual(self.all_xattrs(self.link_target), {"target":"1"})
		self.assertEqual(self.serialized_metadata(), {
			"file1": {"file_1":"1", "file_2": "2"},
			"directory": {"dir_1":"1"},
			"link_target": {"target":"1"},
		})

	def test_loading_attr_ensures_all_xattrs_are_set(self):
		dumbattr.set(self.file1, "file_1", "1")
		xattr.remove(self.file1, "file_1", namespace=xattr.NS_USER)

		self.assertEqual(self.all_xattrs(self.file1), {})
		
		self.assertEqual(dumbattr.load(self.file1).copy(), {'file_1':'1'})
		self.assertEqual(self.all_xattrs(self.file1), {'file_1':'1'})

	def test_xattrs_overriden_by_serialized_attrs(self):
		dumbattr.set(self.file1, "test1", "1")
		xattr.set(self.file1, "test1", "2", namespace=xattr.NS_USER)

		self.assertEqual(self.serialized_metadata(), {'file1': {'test1':'1'}})
		# load() has the side effect of fixing any discrepancies, just like `fix()`
		self.assertEqual(dumbattr.load(self.file1).copy(), {'test1': '1'})
		self.assertEqual(self.all_xattrs(self.file1), {'test1': '1'})

	def test_xattrs_with_no_serialized_value_are_kept(self):
		dumbattr.set(self.file1, "test1", "1")
		xattr.set(self.file1, "test2", "2", namespace=xattr.NS_USER)

		self.assertEqual(self.serialized_metadata(), {'file1': {'test1':'1'}})
		self.assertEqual(dumbattr.load(self.file1).copy(), {'test1': '1', 'test2':'2'})
		self.assertEqual(self.serialized_metadata(), {'file1': {'test1': '1', 'test2':'2'}})

	def test_metadata_file_is_removed_when_no_files_have_attrs(self):
		dumbattr.set(self.file1, "test1", "1")

		self.assertEqual(self.serialized_metadata(), {'file1': {'test1':'1'}})

		dumbattr.remove(self.file1, "test1")

		self.assertEqual(self.serialized_metadata(), None)
		assert not os.path.exists(os.path.join(self.base, dumbattr.METADATA_FILENAME))

	def test_symlink_attrs_are_saved_only_in_metadata(self):
		dumbattr.set(self.link_target, 'kind', 'target')
		dumbattr.set(self.link, 'kind', 'link')
		self.assertEqual(self.serialized_metadata(), {
			'link': {'kind': 'link'},
			'link_target': {'kind': 'target'},
		})

		self.assertEqual(self.all_xattrs(self.link_target, nofollow=True), {'kind':'target'})
		self.assertEqual(self.all_xattrs(self.link,        nofollow=True), {})

		self.assertEqual(dumbattr.load(self.link_target).copy(), {'kind':'target'})
		self.assertEqual(dumbattr.load(self.link).copy(), {'kind':'link'})

	def test_attr_removal(self):
		dumbattr.set(self.file1, 'test1', '1')
		dumbattr.set(self.file1, 'test2', '2')
		dumbattr.remove(self.file1, 'test1')

		self.assertEqual(dumbattr.load(self.file1).copy(), {'test2':'2'})
		self.assertEqual(self.serialized_metadata(), {'file1':{'test2':'2'}})

		dumbattr.remove(self.file1, 'test2')
		self.assertEqual(self.serialized_metadata(), None)

	def test_symlink_attr_removal(self):
		dumbattr.set(self.link, 'kind', 'link')
		dumbattr.set(self.link, 'test', '1')
		dumbattr.remove(self.link, 'test')

		self.assertEqual(self.serialized_metadata(), {
			'link': {'kind': 'link'},
		})

		dumbattr.remove(self.link, 'kind')
		self.assertEqual(self.serialized_metadata(), None)

	def test_deleting_unknown_key_raises_key_error(self):
		self.assertRaises(KeyError, lambda: dumbattr.remove(self.file1, 'unknown'))

	def test_deleting_unknown_key_from_symlink_raises_key_error(self):
		self.assertRaises(KeyError, lambda: dumbattr.remove(self.link, 'unknown'))

	def test_accessing_unknown_key_raises_key_error(self):
		self.assertRaises(KeyError, lambda: dumbattr.get(self.file1, 'unknown'))
		self.assertRaises(KeyError, lambda: dumbattr.get(self.link, 'unknown'))

	def test_deleting_last_attr_from_file(self):
		dumbattr.set(self.file1, 'test1', '1')
		dumbattr.set(self.file2, 'test2', '2')
		dumbattr.set(self.link, 'test3', '3')
		dumbattr.remove(self.file1, 'test1')
		dumbattr.remove(self.link, 'test3')

		self.assertEqual(self.serialized_metadata(), {'file2':{'test2':'2'}})
	
	def test_cant_load_nonexistant_file(self):
		self.assertRaises(OSError, lambda: dumbattr.load(self.file1 + "_not"))

	def test_cant_load_file_in_nonexistant_path(self):
		self.assertRaises(OSError, lambda: dumbattr.load('/foo/bar/baz'))
	
	def test_stored_view_returns_empty_dict_when_no_file(self):
		self.assertEqual(dumbattr.stored_view(self.base), {})

	def test_stored_view_returns_dict_when_data_saved(self):
		dumbattr.set(self.file1, 'test1', '1')
		dumbattr.set(self.file2, 'test2', '2')
		meta = dumbattr.stored_view(self.base)
		self.assertEqual(meta, self.serialized_metadata())

	#TODO: hard links?
