0:
	mkzero-gfxmonk -v "`cat VERSION`" \
		-p dumbattr.py \
		-p dumbattr_test.py \
		python-dumbattr.xml

test: python-dumbattr-local.xml
	0install run http://gfxmonk.net/dist/0install/nosetests-runner.xml -v

test-all: python-dumbattr-local.xml
	0install run http://0install.net/2008/interfaces/0test.xml python-dumbattr-local.xml http://repo.roscidus.com/python/python 2.6,3 3,4

python-dumbattr-local.xml: python-dumbattr.xml
	0install run http://gfxmonk.net/dist/0install/0local.xml python-dumbattr.xml

.PHONY: 0 test test-all
