exec >&2
set -eux
redo-ifchange python-dumbattr-local.xml
0install run http://0install.net/2008/interfaces/0test.xml python-dumbattr-local.xml http://repo.roscidus.com/python/python 2.6,3 3,4
