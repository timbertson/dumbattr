dumbattr
--------

Dumbattr is a layer on top of `xattr`. As well as saving and loading xattr-based metadata, it stores the same information in a directory-level JSON file. If for some reason you lose your xattrs (via a backup roundtrip, or a copy program that doesn't respect xattrs), the next time you use `dumbattr` to load a file's metadata (for any file in that directory), it'll repopulate all missing `xattr` data as long as you've copied whole directory.

Dumbattr only supports user-level data (i.e xattrs that start with `"user."`). You do not need to specify this in your attribute names, it is implied. That is:

	>>> import dumbattr
	>>> dumbattr.set("/path/to/file", "attr_name", "attr_value")

Will set the underlying `xattr` key `"user.attr_name"` to `"attr_value"`.

Caveats
-------

 - Persisted metadata takes precedence. If you have set the *same* key on a file using both plain xattr and `dumbattr`, `dumbattr` attributes will take priority when you read the file (and will overwrite the plain xattr accordingly. This only applies to conflicting keys for the one file - i.e it won't touch plain xattrs under a different key for that same file.

 - Obviously, the restore from lost xattrs only works on a per-directory level. If you move just one file and not its containing directory and simultaneously strip its xattr data, then dumbattr can't help you there.

